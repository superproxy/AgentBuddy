#!/usr/bin/env python3
"""CrawlerAgent — 搜索智能体。

职责：tasks.intent → LLM 生成查询词 → 多源聚合搜索（Tavily 网页 + GitHub API 仓库）
      → 抓正文 → 文章评级 → LLM 抽 skills → 写 spec.yaml。
不构建、不发布。BuildAgent 读 spec.yaml 完成构建与发布。

独立应用，不依赖客户端配置（config/llm/llm.yaml、config/mcp/mcp.yaml）。
所有外部凭据通过环境变量注入：

    OPENAI_API_KEY     必填（OpenAI 兼容 LLM，用于生成查询词 / skill 抽取）
    OPENAI_BASE_URL    默认 https://api.openai.com/v1
    OPENAI_MODEL       默认 gpt-4o-mini
    TAVILY_API_KEY     必填（Tavily 网页搜索，独立 MCP 凭据）
    GITHUB_TOKEN       可选（GitHub API 搜索，无 token 60 次/小时，有 5000 次/小时）

启动检查：调用 require_env() 在程序入口检查环境变量；缺失时直接退出。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml

SERVER_DIR = Path(__file__).resolve().parent
SPECS_DIR = SERVER_DIR / "data" / "specs"          # spec.yaml 输出目录
SEEN_URLS_FILE = SERVER_DIR / "data" / "crawler-agent-seen-urls.json"


# ============================================================
# 启动检查 — 环境变量完整性
# ============================================================

_REQUIRED_ENV: dict[str, str] = {
    "OPENAI_API_KEY": "OpenAI 兼容 LLM 的 API Key（用于生成查询词 / skill 抽取）",
    "TAVILY_API_KEY": "Tavily 网页搜索 API Key（独立 MCP 凭据）",
}

_OPTIONAL_ENV: dict[str, str] = {
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "OPENAI_MODEL": "gpt-4o-mini",
}


def check_env() -> list[str]:
    """启动检查：返回缺失的必填环境变量名列表。空列表表示环境就绪。"""
    return [k for k in _REQUIRED_ENV if not os.environ.get(k, "").strip()]


def require_env() -> None:
    """启动检查：缺失必填环境变量时打印提示并退出进程。"""
    missing = check_env()
    if not missing:
        return
    print("[crawler_agent] 环境变量缺失，无法启动搜索：", file=sys.stderr)
    for k in missing:
        print(f"  - {k}: {_REQUIRED_ENV[k]}", file=sys.stderr)
    print("\n请通过环境变量注入（独立应用，不读 config/llm/llm.yaml 与 config/mcp/mcp.yaml）：",
          file=sys.stderr)
    print("  export OPENAI_API_KEY=sk-xxxx", file=sys.stderr)
    print("  export TAVILY_API_KEY=tvly-xxxx", file=sys.stderr)
    print("  export OPENAI_BASE_URL=https://api.openai.com/v1   # 可选", file=sys.stderr)
    print("  export OPENAI_MODEL=gpt-4o-mini                    # 可选", file=sys.stderr)
    print("  export GITHUB_TOKEN=ghp-xxxx                       # 可选（GitHub 搜索）", file=sys.stderr)
    sys.exit(2)


# ============================================================
# LLM 配置（OpenAI 兼容，纯环境变量）
# ============================================================


def _get_llm_config() -> dict[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {}
    return {
        "api_key": api_key,
        "base_url": os.environ.get("OPENAI_BASE_URL", _OPTIONAL_ENV["OPENAI_BASE_URL"]).strip().rstrip("/"),
        "model": os.environ.get("OPENAI_MODEL", _OPTIONAL_ENV["OPENAI_MODEL"]).strip(),
    }


def _get_tavily_key() -> str:
    return os.environ.get("TAVILY_API_KEY", "").strip()


def _get_github_token() -> str:
    return os.environ.get("GITHUB_TOKEN", "").strip()


def llm_chat(messages: list[dict], *, json_mode: bool = False, timeout: int = 60,
             retries: int = 2) -> str:
    """OpenAI 兼容 chat completions 调用，返回文本内容。

    对 5xx / 网络错误重试 retries 次（间隔 2/4 秒），提高对不稳定网关的容错。
    """
    cfg = _get_llm_config()
    if not cfg:
        raise RuntimeError("OPENAI_API_KEY 未设置；crawler_agent 需通过环境变量注入 LLM 配置")

    payload: dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.3,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                f"{cfg['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            # 仅对 5xx / 网络错误重试；4xx 直接抛
            if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code < 500:
                raise
            if attempt < retries:
                import time
                time.sleep(2 * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError("llm_chat: unreachable")


# ============================================================
# 搜索智能体 — 查询词生成（LLM 按 intent 生成）
# ============================================================


# intent → 搜索意图说明，指导 LLM 生成查询词
_INTENT_DESC: dict[str, str] = {
    "latest": "最新发布（近期出现的、版本更新、新功能）",
    "trending": "热门推荐（TOP 10、best、最受欢迎、本周热门）",
    "recommend": "综合推荐（实战、教程、最佳实践、避坑指南）",
}


def generate_queries(intent: str, *, count: int = 5) -> list[str]:
    """让 LLM 按 intent 生成搜索查询词。

    intent 取值：
    - latest   最新（新功能、版本更新、近期发布）
    - trending 热门（TOP 10、best、最受欢迎、本周热门）
    - recommend 综合（实战、教程、最佳实践）

    返回：[query1, query2, ...]（去重，最多 count 个）
    """
    intent = (intent or "").strip().lower() or "trending"
    desc = _INTENT_DESC.get(intent, _INTENT_DESC["trending"])

    prompt = (
        "你是技术内容策划专家。AgentBuddy 是 Claude Code / Cursor / Codex 等 AI 编码助手的"
        " skills 聚合市场。"
        f"现在需要抓取「{desc}」类的 skills 推荐文章，从中抽取可安装的 skill。\n\n"
        "请生成适合在中文技术社区（公众号/知乎/掘金/CSDN）和 GitHub/YouTube 搜索的查询词，"
        f"覆盖 Claude Code skills、MCP servers、AI agent、Cursor rules 等方向。\n\n"
        "要求：\n"
        "1. 每个查询词 5-20 字，自然语言\n"
        "2. 中英文混合，符合博主写作习惯\n"
        f"3. 兼顾盘点、实战、对比、教程等不同形态\n"
        "4. 与 intent 强相关（避免泛搜）\n\n"
        f'返回 JSON：{{"queries": ["query1", "query2", ...]}}（最多 {count} 个）'
    )
    try:
        text = llm_chat([{"role": "user", "content": prompt}], json_mode=True)
        data = json.loads(text)
        queries = [str(q).strip() for q in data.get("queries", []) if str(q).strip()]
    except Exception:
        queries = []

    # 去重
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        ql = q.lower()
        if ql and ql not in seen:
            seen.add(ql)
            out.append(q)
    return out[:count]


# ============================================================
# 搜索智能体 — GitHub API 仓库搜索
# ============================================================


def github_search(query: str, *, max_results: int = 10) -> list[dict]:
    """GitHub API 搜索仓库，返回 [{title, url, content}]。

    用 GITHUB_SEARCH_TOPIC 前缀拼接 query，定位 SKILL.md / skills 集合类仓库。
    无 token 时走匿名（60 次/小时），有 token 时 5000 次/小时。
    """
    token = _get_github_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AgentBuddy-CrawlerAgent",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # 搜含 SKILL.md 的仓库，或 README 提及 skills 的仓库
    full_query = f"{query} skills in:name,description,readme"
    try:
        resp = requests.get(
            "https://api.github.com/search/repositories",
            params={
                "q": full_query,
                "sort": "stars",
                "order": "desc",
                "per_page": min(max_results, 30),
            },
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [github-search-error] {e}")
        return []

    results: list[dict] = []
    for item in data.get("items", [])[:max_results]:
        url = str(item.get("html_url", "")).strip()
        if not url:
            continue
        title = str(item.get("full_name", "")).strip()
        desc = str(item.get("description", "") or "").strip()
        stars = int(item.get("stargazers_count", 0) or 0)
        # content 字段供评级用：包含描述 + star 数（让评级维度有内容可打分）
        content = f"{desc}\n\nStars: {stars}\nLanguage: {item.get('language', '')}"
        results.append({"title": title, "url": url, "content": content})
    return results


# ============================================================
# 搜索智能体 — 多源聚合搜索（Tavily 网页 + GitHub 仓库）
# ============================================================


def aggregate_search(
    query: str,
    *,
    sites: list[str] | None = None,
    max_results: int = 10,
) -> list[dict]:
    """聚合多搜索源：Tavily 网页搜索 + GitHub 仓库搜索。

    sites 中的 github.com 域名会触发 GitHub API 搜索（更精准）；
    其余域名走 Tavily site: 过滤。

    Returns: [{title, url, content, source}]，source 标记来源（tavily/github）
    """
    all_hits: list[dict] = []
    seen_urls: set[str] = set()

    # 1. GitHub API 搜索（如果 github.com 在 sites 中或 sites 为空）
    use_github = (not sites) or ("github.com" in [s.lower() for s in sites])
    if use_github:
        try:
            gh_hits = github_search(query, max_results=max_results)
            for h in gh_hits:
                if h["url"] not in seen_urls:
                    seen_urls.add(h["url"])
                    h["source"] = "github"
                    all_hits.append(h)
        except Exception as e:
            print(f"  [github-search-error] {e}")

    # 2. Tavily 网页搜索（排除 github.com，避免与 GitHub API 重复）
    tavily_sites = [s for s in (sites or []) if s.lower() != "github.com"]
    if tavily_sites or not sites:
        try:
            tv_hits = tavily_search(query, sites=tavily_sites or None, max_results=max_results)
            for h in tv_hits:
                if h["url"] not in seen_urls:
                    seen_urls.add(h["url"])
                    h["source"] = "tavily"
                    all_hits.append(h)
        except Exception as e:
            print(f"  [tavily-search-error] {e}")

    return all_hits


# ============================================================
# 搜索智能体 — Tavily 搜索
# ============================================================


def tavily_search(query: str, sites: list[str] | None = None, max_results: int = 10) -> list[dict]:
    """Tavily 搜索，可选渠道域名白名单。

    Returns: [{title, url, content}, ...]
    """
    key = _get_tavily_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY 未设置")

    full_query = query
    if sites:
        site_clause = " OR ".join(f"site:{s}" for s in sites)
        full_query = f"({site_clause}) {query}"

    resp = requests.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "query": full_query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("results", [])[:max_results]:
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        results.append({
            "title": str(item.get("title", "")).strip(),
            "url": url,
            "content": str(item.get("content", "")).strip(),
        })
    return results


# ============================================================
# 文章抓取
# ============================================================

_BLOCKED_MARKERS = (
    "环境异常",
    "完成验证后即可继续访问",
    "微信扫一扫可打开此内容",
    "Scan with Weixin",
    "WeChat verification page",
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_article(url: str, *, timeout: int = 20) -> dict:
    """抓取文章正文，返回 {title, content, html, blocked}。"""
    if "youtube.com/watch" in url or "youtu.be/" in url:
        return _fetch_youtube(url)

    headers = {"User-Agent": _UA, "Accept": "text/html,application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        return {"title": "", "content": "", "html": "", "blocked": False, "error": str(e)}

    text = resp.text or ""
    if any(m in text for m in _BLOCKED_MARKERS):
        return {"title": "", "content": "", "html": text, "blocked": True}

    return {
        "title": _extract_title(text),
        "content": _extract_main_text(text),
        "html": text,
        "blocked": False,
    }


def _fetch_youtube(url: str) -> dict:
    video_id = ""
    if "watch?v=" in url:
        video_id = url.split("watch?v=", 1)[1].split("&", 1)[0]
    elif "youtu.be/" in url:
        video_id = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not video_id:
        return {"title": "", "content": "", "html": "", "blocked": False}

    try:
        r = requests.get(
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
            headers={"User-Agent": _UA},
            timeout=15,
        )
        if r.ok:
            data = r.json()
            title = str(data.get("title", "")).strip()
            author = str(data.get("author_name", "")).strip()
            content = f"作者：{author}\n标题：{title}"
            return {"title": title, "content": content, "html": "", "blocked": False}
    except Exception:
        pass
    return {"title": "", "content": "", "html": "", "blocked": False}


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    for sep in (" - ", " | ", " _ ", "——"):
        if sep in title:
            title = title.split(sep, 1)[0].strip()
            break
    return title[:200]


def _extract_main_text(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.IGNORECASE | re.DOTALL)
    code_blocks: list[str] = []

    def _save_code(m: re.Match) -> str:
        code_blocks.append(re.sub(r"<[^>]+>", "", m.group(1)))
        return f"\n```\n{len(code_blocks) - 1}\n```\n"

    html = re.sub(r"<pre[^>]*>(.*?)</pre>", _save_code, html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<code[^>]*>(.*?)</code>", _save_code, html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", html)
    for i, code in enumerate(code_blocks):
        text = text.replace(f"\n```\n{i}\n```\n", f"\n```\n{code}\n```\n")
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ============================================================
# 搜索智能体 — 文章评级（0-100）
# ============================================================

# 渠道权重缓存（首次用时从 plugin-sources.yaml 加载）
_channel_weight_cache: dict[str, int] = {}


def _load_channel_weights() -> dict[str, int]:
    """从 plugin-sources.yaml 加载渠道权重 {domain_lower: weight}。"""
    global _channel_weight_cache
    if _channel_weight_cache:
        return _channel_weight_cache
    try:
        sources_file = SERVER_DIR / "config" / "plugin-sources.yaml"
        with open(sources_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for c in data.get("channels", []) or []:
            domain = str(c.get("domain", "")).strip().lower()
            weight = int(c.get("weight", 10) or 10)
            if domain:
                _channel_weight_cache[domain] = max(0, min(20, weight))
    except Exception:
        pass
    return _channel_weight_cache


def _channel_weight(url: str) -> int:
    """根据文章 URL 匹配渠道域名，返回该渠道权重（0-20，未匹配返回 10）。"""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return 10
        weights = _load_channel_weights()
        # 精确匹配
        if host in weights:
            return weights[host]
        # 后缀匹配（如 blog.csdn.net → csdn.net）
        for domain, w in weights.items():
            if host == domain or host.endswith("." + domain):
                return w
    except Exception:
        pass
    return 10


def _intent_relevance(title: str, content: str, intent: str) -> float:
    """判断文章是否与 intent 强相关（推荐/盘点/教程类内容得分高）。

    intent: latest / trending / recommend
    返回 0-1：
    - 标题含盘点/推荐类关键词（TOP 10、best、推荐、热门、2026、new、latest 等）→ 1.0
    - 内容含 skills / mcp / agent / claude code 等领域关键词 → 0.6
    - 单篇技术博客但无推荐信号 → 0.3
    - 完全无关 → 0.0
    """
    if not title and not content:
        return 0.0
    title_l = (title or "").lower()
    content_l = (content or "").lower()
    intent_l = (intent or "").strip().lower() or "trending"

    # 1. intent 特定信号
    trending_signals = ("top 10", "top10", "best", "trending", "热门", "推荐",
                        "最受欢迎", "盘点", "汇总", "合集", "must-have", "favorite")
    latest_signals = ("new", "latest", "最新", "新发布", "version", "release",
                      "刚刚", "近期", "2024", "2025", "2026")
    recommend_signals = ("实战", "教程", "best practice", "最佳实践", "避坑",
                         "tutorial", "guide", "指南", "how to", "如何")

    intent_signals = {
        "trending": trending_signals,
        "latest": latest_signals,
        "recommend": recommend_signals,
    }.get(intent_l, trending_signals)

    if any(sig in title_l for sig in intent_signals):
        return 1.0
    if any(sig in content_l for sig in intent_signals):
        return 0.8

    # 2. 领域关键词（skills / mcp / agent / claude code 等）
    domain_signals = ("skill", "mcp", "agent", "claude code", "cursor",
                      "codex", "copilot", "rules", "hook")
    if any(sig in title_l for sig in domain_signals):
        return 0.6
    if any(sig in content_l for sig in domain_signals):
        return 0.4

    # 3. 有技术内容（代码块）但无推荐信号
    if "```" in content_l:
        return 0.3

    return 0.0


def rate_article(
    *,
    title: str,
    content: str,
    url: str,
    intent: str = "trending",
    blocked: bool = False,
    has_snippet_fallback: bool = False,
) -> dict:
    """对一篇文章打分（0-100），返回 {score, breakdown}。

    评分维度：
    - content_length     20 分：正文长度（>2000 满分，500-2000 线性，<500 得 0）
    - code_blocks        25 分：代码块数量（每个 5 分，上限 25）
    - intent_relevance   25 分：与 intent 的相关性（0/0.3/0.4/0.6/0.8/1.0）* 25
    - channel            20 分：渠道权重（直接取 channel.weight，0-20）
    - penalty            风控惩罚：blocked 但有摘要 -15，blocked 且无摘要直接 0 分

    Returns: {"score": int, "breakdown": {dim: score, ...}}
    """
    # 风控无摘要：直接 0 分
    if blocked and not has_snippet_fallback:
        return {
            "score": 0,
            "breakdown": {
                "content_length": 0, "code_blocks": 0, "intent_relevance": 0,
                "channel": 0, "penalty": -100,
            },
            "reason": "blocked_no_snippet",
        }

    text = content or ""
    text_len = len(text)

    # 1. 内容长度（20 分）
    if text_len >= 2000:
        cl_score = 20
    elif text_len >= 500:
        cl_score = int(20 * (text_len - 500) / 1500)
    else:
        cl_score = 0

    # 2. 代码块数量（25 分，每个 5 分）
    code_count = len(re.findall(r"```", text)) // 2
    cb_score = min(code_count * 5, 25)

    # 3. intent 相关性（25 分）
    rel = _intent_relevance(title, text, intent)
    ir_score = int(rel * 25)

    # 4. 渠道权重（20 分）
    ch_score = _channel_weight(url)

    # 5. 风控惩罚
    penalty = 0
    reason = ""
    if blocked and has_snippet_fallback:
        penalty = -15
        reason = "blocked_with_snippet"

    total = max(0, cl_score + cb_score + ir_score + ch_score + penalty)
    breakdown = {
        "content_length": cl_score,
        "code_blocks": cb_score,
        "intent_relevance": ir_score,
        "channel": ch_score,
        "penalty": penalty,
    }
    return {"score": total, "breakdown": breakdown, "reason": reason}


# ============================================================
# 搜索智能体 — LLM 从文章抽取 skills
# ============================================================


@dataclass
class DiscoveredSkill:
    name: str
    description: str = ""
    version: str = "1.0.0"
    source: str = ""


def extract_skills_from_article(title: str, content: str, source_url: str) -> list[DiscoveredSkill]:
    if not content or len(content) < 100:
        return []

    snippet = content[:8000]
    prompt = (
        "你是 skill 抽取专家。从下面的技术文章中识别出可以沉淀为可安装 skill 的知识点。\n\n"
        "skill 定义：一段可复用的能力描述，包含 name（短小、kebab-case、唯一）、"
        "description（一句话说明这个 skill 能做什么）、version（默认 1.0.0）。\n\n"
        "抽取规则：\n"
        "1. 只抽取作者明确讲解过、有实操价值的能力（不要凭空推测）\n"
        "2. name 用英文 kebab-case，简洁唯一\n"
        "3. description 用中文，<=120 字\n"
        "4. 一篇文章通常产出 1-5 个 skills，没有就返回空数组\n"
        "5. 不要把整篇文章当成一个 skill，要拆细\n\n"
        f"文章标题：{title}\n"
        f"文章来源：{source_url}\n"
        f"文章正文：\n{snippet}\n\n"
        '返回 JSON：{"skills": [{"name": "...", "description": "...", "version": "1.0.0"}, ...]}'
    )
    try:
        text = llm_chat([{"role": "user", "content": prompt}], json_mode=True)
        data = json.loads(text)
        raw_skills = data.get("skills", [])
    except Exception:
        return []

    skills: list[DiscoveredSkill] = []
    seen: set[str] = set()
    for s in raw_skills:
        if not isinstance(s, dict):
            continue
        nm = str(s.get("name", "")).strip().lower()
        nm = re.sub(r"[^a-z0-9-]", "-", nm).strip("-")
        if not nm or nm in seen:
            continue
        seen.add(nm)
        skills.append(DiscoveredSkill(
            name=nm,
            description=str(s.get("description", "")).strip()[:500],
            version=str(s.get("version", "1.0.0")).strip() or "1.0.0",
            source=source_url,
        ))
    return skills


# ============================================================
# 去重状态（跨运行的 URL 去重）
# ============================================================


def load_seen_urls() -> dict[str, Any]:
    try:
        return json.loads(SEEN_URLS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_seen_urls(state: dict[str, Any]) -> None:
    try:
        SEEN_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SEEN_URLS_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def mark_seen(state: dict[str, Any], url: str, *, title: str = "", status: str = "ok") -> None:
    state[url] = {"ts": int(time.time()), "title": title, "status": status}


# ============================================================
# spec.yaml 生成
# ============================================================


def _slugify(text: str) -> str:
    text = re.sub(r"[\s_+/\\]+", "-", text.lower())
    text = re.sub(r"[^\w\u4e00-\u9fff-]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "article"


def write_spec(
    *,
    task_name: str,
    article_url: str,
    article_title: str,
    article_content: str,
    skills: list[DiscoveredSkill],
    tags: list[str],
    rating: dict | None = None,
) -> Path:
    """写一个 spec.yaml 文件，返回路径。

    路径：data/specs/<task_name>/<slug>.yaml
    BuildAgent 扫描此目录读 spec 构建。

    spec.yaml 顶层包含 build_plugin 兼容字段（name/version/description/skills/...），
    BuildAgent 直接将整个 spec 内容作为 config_yaml 传给 build_plugin 即可。
    额外的元信息（spec_version / source_article / build_status / rating）build_plugin 会忽略。

    rating 为 rate_article() 的返回值，写入 source_article.rating 与顶层 rating 字段，
    BuildAgent 按顶层 rating 降序构建（高分优先）。
    """
    slug = _slugify(article_title) or "article"
    if len(slug) > 60:
        slug = slug[:60].rstrip("-")

    spec_dir = SPECS_DIR / task_name
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / f"{slug}.yaml"

    # plugin 名：task_slug + article_slug
    plugin_name = f"{_slugify(task_name)}-{slug}"
    if len(plugin_name) > 60:
        plugin_name = plugin_name[:60].rstrip("-")

    spec = {
        # 元信息（BuildAgent 维护，build_plugin 忽略）
        "spec_version": "1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generated_by": "crawler_agent",
        "task": task_name,
        "build_status": "pending",  # pending / built / published / error
        # 顶层 rating：BuildAgent 按此降序构建（高分优先）
        "rating": int(rating.get("score", 0)) if rating else 0,
        "source_article": {
            "url": article_url,
            "title": article_title,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "content_excerpt": article_content[:500],
            "rating": rating or {},
        },
        # build_plugin 兼容字段（meta_from_config 读取）
        "name": plugin_name,
        "version": "1.0.0",
        "description": f"从「{article_title}」抽取的 skills（来源 {article_url}）"[:500],
        "author": "crawler-agent",
        "license": "",
        "homepage": article_url,
        "repository": "",
        "keywords": list(tags),
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                **({"source": s.source} if s.source else {}),
            }
            for s in skills
        ],
        "mcpServers": {},
        "envVars": {},
    }

    with open(spec_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return spec_path


# ============================================================
# 主流程 — CrawlerAgent 执行（搜索 → 抓取 → 抽 skills → 写 spec）
# ============================================================


@dataclass
class CrawlResult:
    """单篇文章的搜索产物。

    status 取值：
    - spec: 已写出 spec.yaml（待 BuildAgent 构建）
    - skip: 跳过（已 seen / 评级过低 / 无 skills / 风控且无摘要）
    - error: 抓取/抽取失败
    """
    url: str
    title: str
    status: str
    spec_path: str = ""
    skills: list[str] = field(default_factory=list)
    reason: str = ""
    rating: int = 0  # 文章评级分数（0-100）


def run_task(
    task_cfg: dict,
    channels: list[dict],
) -> list[CrawlResult]:
    """执行一个 CrawlerAgent 任务：生成查询词 → 多源聚合搜索 → 抓取 → 抽 skills → 写 spec.yaml。

    Args:
        task_cfg: plugin-sources.yaml 中 tasks 列表的一个元素
        channels: 顶层 channels 池
    """
    name = str(task_cfg.get("name", "")).strip()
    intent = str(task_cfg.get("intent") or "trending").strip().lower()
    if not name:
        return [CrawlResult(url="", title="", status="error", reason="no name")]

    # 1. 解析本任务可用渠道域名
    task_channel_ids = task_cfg.get("channels") or []
    if task_channel_ids:
        id_set = {str(c).lower() for c in task_channel_ids}
        task_sites = [c["domain"] for c in channels if str(c.get("id", "")).lower() in id_set]
    else:
        task_sites = [c["domain"] for c in channels]
    if not task_sites:
        return [CrawlResult(url="", title="", status="error", reason="no channels resolved")]

    print(f"  [intent] {intent}")
    print(f"  [channels] {task_sites}")

    # 2. LLM 按 intent 生成查询词（替代旧的 topic + auto_discover_topics）
    try:
        queries = generate_queries(intent, count=5)
    except Exception as e:
        print(f"  [generate-queries-error] {e}")
        queries = []
    if not queries:
        # 兜底：intent 直接当查询词
        queries = [intent]
    print(f"  [queries] {queries}")

    # 3. 多源聚合搜索（每个查询词：Tavily 网页 + GitHub API 仓库）
    max_results = int(task_cfg.get("max_results", 10))
    all_hits: list[dict] = []
    seen_urls_in_run: set[str] = set()
    for q in queries:
        try:
            hits = aggregate_search(q, sites=task_sites, max_results=max_results)
        except Exception as e:
            print(f"  [search-error] {q}: {e}")
            continue
        for h in hits:
            if h["url"] in seen_urls_in_run:
                continue
            seen_urls_in_run.add(h["url"])
            all_hits.append(h)
        time.sleep(1)

    if not all_hits:
        return [CrawlResult(url="", title="", status="skip", reason="no search results")]

    # 4. 跨运行去重
    seen_state = load_seen_urls()
    results: list[CrawlResult] = []

    for hit in all_hits:
        url = hit["url"]
        title = hit.get("title", "")

        if url in seen_state:
            results.append(CrawlResult(url=url, title=title, status="skip", reason="seen"))
            continue

        # 5. 抓正文（GitHub 仓库已有 content，跳过抓取）
        source = hit.get("source", "")
        snippet = hit.get("content", "") or ""
        if source == "github":
            article = {
                "title": title,
                "content": snippet,
                "html": "",
                "blocked": False,
            }
        else:
            # Tavily 来源：snippet 已是清洁正文摘要，优先使用。
            # 仅当 snippet 异常短（< 200 字符）时才 fetch 补充（可能抓到更好的正文）。
            # 注意：juejin/zhihu 等是 SPA，fetch 往往只拿到空壳，snippet 质量更高。
            if len(snippet) >= 200:
                article = {"title": title, "content": snippet, "html": "", "blocked": False}
            else:
                try:
                    article = fetch_article(url)
                except Exception as e:
                    mark_seen(seen_state, url, title=title, status="fetch_error")
                    results.append(CrawlResult(url=url, title=title, status="error", reason=f"fetch: {e}"))
                    continue
                # fetch 失败但有 snippet → 用 snippet 兜底
                if not article.get("content"):
                    article["content"] = snippet

        blocked = bool(article.get("blocked"))
        # 风控且无摘要 → 评级 0 分，跳过
        if blocked and not snippet:
            mark_seen(seen_state, url, title=title, status="blocked_no_snippet")
            results.append(CrawlResult(url=url, title=title, status="skip",
                                       reason="blocked & no snippet", rating=0))
            continue
        # 风控但有摘要 → 用摘要兜底
        if blocked and snippet:
            article["title"] = article.get("title") or title
            article["content"] = snippet

        article_title = article.get("title") or title
        article_content = article.get("content", "")

        # 6. 文章评级（0-100）：低于阈值的跳过，不调用 LLM 抽 skills（省钱）
        rating = rate_article(
            title=article_title,
            content=article_content,
            url=url,
            intent=intent,
            blocked=blocked,
            has_snippet_fallback=bool(snippet) if blocked else False,
        )
        rating_score = int(rating.get("score", 0))
        min_rating = int(task_cfg.get("min_rating", 40))
        if rating_score < min_rating:
            mark_seen(seen_state, url, title=article_title,
                      status=f"low_rating_{rating_score}")
            results.append(CrawlResult(
                url=url, title=article_title, status="skip",
                reason=f"low rating {rating_score} < {min_rating}",
                rating=rating_score,
            ))
            continue
        print(f"  [rating] {rating_score}/100 "
              f"(len={rating['breakdown']['content_length']} "
              f"code={rating['breakdown']['code_blocks']} "
              f"rel={rating['breakdown']['intent_relevance']} "
              f"ch={rating['breakdown']['channel']} "
              f"pen={rating['breakdown']['penalty']})")

        # 7. LLM 抽 skills
        try:
            skills = extract_skills_from_article(article_title, article_content, url)
        except Exception as e:
            mark_seen(seen_state, url, title=article_title, status="extract_error")
            results.append(CrawlResult(url=url, title=article_title, status="error",
                                       reason=f"extract: {e}", rating=rating_score))
            continue

        if not skills:
            mark_seen(seen_state, url, title=article_title, status="no_skills")
            results.append(CrawlResult(url=url, title=article_title, status="skip",
                                       reason="no skills", rating=rating_score))
            continue

        # 8. 写 spec.yaml（带 rating，不构建）
        try:
            spec_path = write_spec(
                task_name=name,
                article_url=url,
                article_title=article_title,
                article_content=article_content,
                skills=skills,
                tags=tags,
                rating=rating,
            )
        except Exception as e:
            mark_seen(seen_state, url, title=article_title, status="spec_error")
            results.append(CrawlResult(url=url, title=article_title, status="error",
                                       reason=f"spec: {e}", rating=rating_score))
            continue

        mark_seen(seen_state, url, title=article_title, status="spec_written")
        results.append(CrawlResult(
            url=url,
            title=article_title,
            status="spec",
            spec_path=str(spec_path),
            skills=[s.name for s in skills],
            rating=rating_score,
        ))

    save_seen_urls(seen_state)
    return results
