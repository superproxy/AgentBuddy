#!/usr/bin/env python3
"""CrawlerAgent — 搜索智能体。

职责：topic + 固定 channels → Tavily 搜索 → 抓正文 → LLM 抽 skills → 写 spec.yaml。
不构建、不发布。BuildAgent 读 spec.yaml 完成构建与发布。

独立应用，不依赖客户端配置（config/llm/llm.yaml、config/mcp/mcp.yaml）。
所有外部凭据通过环境变量注入：

    OPENAI_API_KEY     必填（OpenAI 兼容 LLM，用于 topic 扩展 / skill 抽取）
    OPENAI_BASE_URL    默认 https://api.openai.com/v1
    OPENAI_MODEL       默认 gpt-4o-mini
    TAVILY_API_KEY     必填（Google 搜索发现，独立 MCP 凭据）

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
    "OPENAI_API_KEY": "OpenAI 兼容 LLM 的 API Key（用于 topic 扩展 / skill 抽取）",
    "TAVILY_API_KEY": "Tavily 搜索 API Key（Google 搜索发现，独立 MCP 凭据）",
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


def llm_chat(messages: list[dict], *, json_mode: bool = False, timeout: int = 60) -> str:
    """OpenAI 兼容 chat completions 调用，返回文本内容。"""
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


# ============================================================
# 搜索智能体 — topic 扩展（基于 Google 高质量结果）
# ============================================================


def discover_topics(seed_topic: str, max_topics: int = 5) -> list[str]:
    """通过 Tavily（Google）搜索种子主题，让 LLM 从结果中归纳出更聚焦的子 topic。

    流程：
    1. Tavily 搜 seed_topic（不限渠道，拿最相关的 Google 结果）
    2. LLM 读搜索结果摘要，归纳出 max_topics 个高质量子 topic
    返回：[topic1, topic2, ...]（不含 seed_topic 本身，去重）
    """
    key = _get_tavily_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY 未设置")

    # 1. Tavily 搜种子主题（不限渠道，拿 Google 高质量结果）
    resp = requests.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "query": seed_topic,
            "search_depth": "advanced",
            "max_results": 10,
            "include_answer": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    answer = str(data.get("answer", "")).strip()
    snippets = []
    for item in data.get("results", [])[:10]:
        snippets.append(f"- {item.get('title', '')}: {item.get('content', '')[:200]}")
    snippet_text = "\n".join(snippets)[:4000]

    # 2. LLM 归纳高质量子 topic
    prompt = (
        f"你是技术内容策划专家。种子主题「{seed_topic}」。\n"
        f"Google 搜索摘要：\n{snippet_text}\n\n"
        f"AI 概述：{answer}\n\n"
        "基于以上 Google 高质量搜索结果，归纳出 "
        f"{max_topics} 个更聚焦、更适合在中文技术社区（公众号/知乎/掘金）"
        "和 YouTube 搜索的子 topic。\n\n"
        "要求：\n"
        "1. 每个 topic 5-15 字，自然语言\n"
        "2. 兼顾教程、实战、对比、避坑等不同形态\n"
        "3. 不与种子主题重复\n"
        "4. 中英文混合，符合博主写作习惯\n\n"
        '返回 JSON：{"topics": ["topic1", "topic2", ...]}'
    )
    try:
        text = llm_chat([{"role": "user", "content": prompt}], json_mode=True)
        data2 = json.loads(text)
        topics = [str(t).strip() for t in data2.get("topics", []) if str(t).strip()]
    except Exception:
        topics = []

    # 去重 + 去种子
    seed_lower = seed_topic.lower()
    seen = {seed_lower}
    out: list[str] = []
    for t in topics:
        tl = t.lower()
        if tl and tl not in seen:
            seen.add(tl)
            out.append(t)
    return out[:max_topics]


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
) -> Path:
    """写一个 spec.yaml 文件，返回路径。

    路径：data/specs/<task_name>/<slug>.yaml
    BuildAgent 扫描此目录读 spec 构建。

    spec.yaml 顶层包含 build_plugin 兼容字段（name/version/description/skills/...），
    BuildAgent 直接将整个 spec 内容作为 config_yaml 传给 build_plugin 即可。
    额外的元信息（spec_version / source_article / build_status）build_plugin 会忽略。
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
        "source_article": {
            "url": article_url,
            "title": article_title,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "content_excerpt": article_content[:500],
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
    - skip: 跳过（已 seen / 无 skills / 风控且无摘要）
    - error: 抓取/抽取失败
    """
    url: str
    title: str
    status: str
    spec_path: str = ""
    skills: list[str] = field(default_factory=list)
    reason: str = ""


def run_task(
    task_cfg: dict,
    channels: list[dict],
) -> list[CrawlResult]:
    """执行一个 CrawlerAgent 任务：搜索 → 抓取 → 抽 skills → 写 spec.yaml。

    Args:
        task_cfg: plugin-sources.yaml 中 discovery 列表的一个元素
        channels: 顶层 channels 池
    """
    name = str(task_cfg.get("name", "")).strip()
    topic = str(task_cfg.get("topic") or name).strip()
    if not topic:
        return [CrawlResult(url="", title="", status="error", reason="no topic")]

    # 1. 解析本任务可用渠道域名
    task_channel_ids = task_cfg.get("channels") or []
    if task_channel_ids:
        id_set = {str(c).lower() for c in task_channel_ids}
        task_sites = [c["domain"] for c in channels if str(c.get("id", "")).lower() in id_set]
    else:
        task_sites = [c["domain"] for c in channels]
    if not task_sites:
        return [CrawlResult(url="", title="", status="error", reason="no channels resolved")]

    print(f"  [topic] {topic}")
    print(f"  [channels] {task_sites}")

    # 2. topic 扩展（可选，通过 Google 高质量结果归纳）
    topics = [topic]
    if task_cfg.get("auto_discover_topics", False):
        max_topics = int(task_cfg.get("max_topics", 5))
        try:
            extra = discover_topics(topic, max_topics=max_topics)
            if extra:
                print(f"  [topics-extended] +{extra}")
                topics.extend(extra)
        except Exception as e:
            print(f"  [topics-extend-error] {e}")

    # 3. Tavily 搜索（每个 topic）
    max_results = int(task_cfg.get("max_results", 10))
    all_hits: list[dict] = []
    seen_urls_in_run: set[str] = set()
    for t in topics:
        try:
            hits = tavily_search(t, sites=task_sites, max_results=max_results)
        except Exception as e:
            print(f"  [search-error] {t}: {e}")
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
    tags = list(task_cfg.get("tags", []) or [])
    results: list[CrawlResult] = []

    for hit in all_hits:
        url = hit["url"]
        title = hit.get("title", "")

        if url in seen_state:
            results.append(CrawlResult(url=url, title=title, status="skip", reason="seen"))
            continue

        # 5. 抓正文
        try:
            article = fetch_article(url)
        except Exception as e:
            mark_seen(seen_state, url, title=title, status="fetch_error")
            results.append(CrawlResult(url=url, title=title, status="error", reason=f"fetch: {e}"))
            continue

        if article.get("blocked"):
            content = hit.get("content", "")
            if not content:
                mark_seen(seen_state, url, title=title, status="blocked_no_snippet")
                results.append(CrawlResult(url=url, title=title, status="skip",
                                           reason="blocked & no snippet"))
                continue
            article["title"] = article.get("title") or title
            article["content"] = content

        article_title = article.get("title") or title
        article_content = article.get("content", "")

        # 6. LLM 抽 skills
        try:
            skills = extract_skills_from_article(article_title, article_content, url)
        except Exception as e:
            mark_seen(seen_state, url, title=article_title, status="extract_error")
            results.append(CrawlResult(url=url, title=article_title, status="error",
                                       reason=f"extract: {e}"))
            continue

        if not skills:
            mark_seen(seen_state, url, title=article_title, status="no_skills")
            results.append(CrawlResult(url=url, title=article_title, status="skip",
                                       reason="no skills"))
            continue

        # 7. 写 spec.yaml（不构建）
        try:
            spec_path = write_spec(
                task_name=name,
                article_url=url,
                article_title=article_title,
                article_content=article_content,
                skills=skills,
                tags=tags,
            )
        except Exception as e:
            mark_seen(seen_state, url, title=article_title, status="spec_error")
            results.append(CrawlResult(url=url, title=article_title, status="error",
                                       reason=f"spec: {e}"))
            continue

        mark_seen(seen_state, url, title=article_title, status="spec_written")
        results.append(CrawlResult(
            url=url,
            title=article_title,
            status="spec",
            spec_path=str(spec_path),
            skills=[s.name for s in skills],
        ))

    save_seen_urls(seen_state)
    return results
