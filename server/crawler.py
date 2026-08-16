#!/usr/bin/env python3
"""AgentBuddy 插件市场 — 定时抓取 Worker。

独立运行，不依赖 Flask 进程。用系统 crontab 调度：

    # 每天凌晨 3 点执行
    0 3 * * * cd /path/to/AgentBuddy/server && python crawler.py >> /var/log/agentbuddy-crawler.log 2>&1

    # 手动触发
    python crawler.py                       # 执行所有启用的源
    python crawler.py --source qwen-mm       # 只执行指定源
    python crawler.py --dry-run              # 只分析+构建，不发布
    python crawler.py --list                 # 列出所有源及状态
    python crawler.py --add <url>            # 添加新源
    python crawler.py --remove <name>        # 移除源

读取 config/plugin-sources.yaml 中的源列表，逐个：
  1. 去重检查（已发布的同名同版本跳过）
  2. analyze_source → 提取 skills / MCP / envVars
  3. 质量评分（star 数、文档完整度、skill 数量）
  4. 服务端自包含打包（inline 模式）
  5. 服务端直连发布到市场
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# ── 路径设置 ──
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent
SOURCES_FILE = SERVER_DIR / "config" / "plugin-sources.yaml"

# server 目录用于导入 auth / plugin_build 等服务端模块。
sys.path.insert(0, str(SERVER_DIR))

import yaml

# ── 颜色日志 ──
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_CYAN = "\033[96m"
COLOR_DARKGRAY = "\033[90m"
COLOR_RESET = "\033[0m"


def log(msg: str = ""):
    print(msg)


def info(msg: str):
    print(f"{COLOR_GREEN}{msg}{COLOR_RESET}")


def warn(msg: str):
    print(f"{COLOR_YELLOW}{msg}{COLOR_RESET}", file=sys.stderr)


def error(msg: str):
    print(f"{COLOR_RED}{msg}{COLOR_RESET}", file=sys.stderr)


def header(msg: str):
    print(f"\n{COLOR_CYAN}{'=' * 50}{COLOR_RESET}")
    print(f"{COLOR_CYAN}  {msg}{COLOR_RESET}")
    print(f"{COLOR_CYAN}{'=' * 50}{COLOR_RESET}")


# ── 配置 ──
SERVER_URL = os.environ.get("AGENTBUDDY_SERVER_URL", "http://127.0.0.1:5001")

# ============================================================
# 服务端直连模式 — crawler 与数据库/市场同机部署时免登录直写
# （不走 HTTP + JWT：直接读写 SQLite 与 packages/ 目录）
# ============================================================

DB_FILE = SERVER_DIR / "data" / "agentbuddy.db"
MARKET_DIR = SERVER_DIR / "data" / "marketplace"

_auth_models = None  # 惰性加载（避免 CLI 模式强依赖 server 侧模块）


def server_mode() -> bool:
    """服务端直连模式判定：本地存在市场数据库（与 app.py 同机）。"""
    return DB_FILE.exists()


def _init_db_access():
    global _auth_models
    if _auth_models is not None:
        return _auth_models
    sys.path.insert(0, str(SERVER_DIR))
    from auth import models as auth_models
    auth_models.set_db_path(DB_FILE)
    auth_models.init_db()
    _auth_models = auth_models
    return _auth_models


def ensure_crawler_user() -> int:
    """确保 crawler 服务账号存在（首跑自动创建），返回用户 id。

    密码为随机串——该账号仅供直连发布归属用，不可（也无需）登录。
    """
    m = _init_db_access()
    conn = m.get_db()
    row = conn.execute("SELECT id FROM users WHERE username = 'crawler'").fetchone()
    if row:
        uid = row["id"]
        conn.close()
        return uid
    import bcrypt as _bcrypt
    import secrets as _secrets
    hashed = _bcrypt.hashpw(_secrets.token_hex(16).encode(), _bcrypt.gensalt()).decode()
    cur = conn.execute(
        "INSERT INTO users (username, password, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
        ("crawler", hashed, "", "member", m.now_iso()),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    info("[OK] 已自动创建 crawler 服务账号（仅供直连发布归属，不可登录）")
    return uid


def already_published_local(name: str, version: str) -> bool:
    """直连去重：查库同 id（name-version）是否已发布。"""
    m = _init_db_access()
    return m.plugin_get(f"{name}-{version}") is not None


def publish_local(zip_path: Path, tags: list | None = None, scope: str = "public") -> dict:
    """直连发布：复用服务端核心发布能力。"""
    _init_db_access()
    from plugin_build import publish_local as _publish_local
    return _publish_local(
        zip_path,
        MARKET_DIR,
        tags=tags,
        scope=scope,
        user={"id": ensure_crawler_user(), "username": "crawler"},
        service_username="crawler",
    )
MIN_QUALITY_SCORE = 30  # 最低质量分（满分 100）


# ============================================================
# 源配置管理
# ============================================================

def load_sources() -> list[dict]:
    """从 config/plugin-sources.yaml 加载源列表。"""
    if not SOURCES_FILE.exists():
        return []
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", [])


def save_sources(sources: list[dict]) -> None:
    SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        yaml.dump(
            {"sources": sources}, f,
            allow_unicode=True, default_flow_style=False, sort_keys=False,
        )


# ============================================================
# 去重检查
# ============================================================

def already_published(name: str, version: str, token: str = "") -> bool:
    """查询市场是否已发布同名同版本的插件。

    服务端直连模式：直接查库（免登录）；远程模式：走 HTTP 搜索接口。
    """
    if server_mode():
        return already_published_local(name, version)
    import requests
    try:
        resp = requests.get(
            f"{SERVER_URL}/api/marketplace/search",
            params={"q": name},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if not resp.ok:
            return False
        result = resp.json()
        packages = result.get("data", {}).get("packages", [])
        return any(p.get("name") == name and p.get("version") == version for p in packages)
    except Exception:
        return False


# ============================================================
# 质量评分
# ============================================================

def evaluate_quality(meta) -> int:
    """对分析结果打分（0-100）。

    评分维度：
    - skill 数量（30 分）：每个 skill 10 分，上限 30
    - MCP servers（20 分）：每个 10 分，上限 20
    - 有描述（15 分）
    - 有 README/homepage（15 分）
    - 有 license（10 分）
    - 有环境变量声明（10 分）
    """
    score = 0
    score += min(len(meta.skills) * 10, 30)
    score += min(len(meta.mcp_servers) * 10, 20)
    if meta.description and len(meta.description) > 20:
        score += 15
    if meta.homepage:
        score += 15
    if meta.license:
        score += 10
    if meta.env_vars:
        score += 10
    return score


# ============================================================
# 发布模式
# ============================================================

def require_server_direct_mode() -> None:
    """后台捞取只允许服务端直连模式运行。"""
    if server_mode():
        return
    raise RuntimeError("crawler 需要在服务端数据目录运行；未找到市场数据库，不能发布")


# ============================================================
# 核心：抓取 + 构建 + 发布
# ============================================================

def crawl_and_publish(source: dict, dry_run: bool = False, remaining_quota: int | None = None) -> dict:
    """处理单个源：动态发现 skills → 聚合成一个可安装插件 → 发布。"""
    from plugin_build import analyze_source

    name = source.get("name", "")
    url = source.get("url", "")
    tags = source.get("tags", [])

    if not url:
        warn(f"  [SKIP] 源无 URL: {name}")
        return {"status": "skip", "reason": "no url", "published": 0, "skipped": 1, "error": 0, "items": []}

    if remaining_quota is not None and remaining_quota <= 0:
        return {"status": "skip", "reason": "quota reached", "published": 0, "skipped": 0, "error": 0, "items": [], "stopped_reason": "quota_reached"}

    header(f"Crawling: {name} {'[server-direct]' if server_mode() else '[http]'}")
    info(f"  URL: {url}")

    try:
        llm_cfg = source.get("llm") if isinstance(source.get("llm"), dict) else None
        source_meta = analyze_source(
            PROJECT_ROOT,
            url,
            ai=bool(source.get("ai", False)),
            llm_config=llm_cfg,
        )
    except Exception as e:
        error(f"  分析失败: {e}")
        return {"status": "error", "reason": str(e), "published": 0, "skipped": 0, "error": 1, "items": []}

    skills = _skills_for_source(source, source_meta)
    if not skills:
        warn("  [SKIP] 未发现 SKILL.md 或有效 skill 配置")
        return {"status": "skip", "reason": "no skills", "published": 0, "skipped": 1, "error": 0, "items": []}

    plugin_meta = _aggregate_meta_for_source(source, source_meta, skills, tags)
    info(f"  Plugin: {plugin_meta.name}")
    info(f"  Aggregated Skills: {len(plugin_meta.skills)}")
    info(f"  MCP Servers: {len(plugin_meta.mcp_servers)}")
    info(f"  Description: {plugin_meta.description[:80]}")

    if not dry_run:
        try:
            require_server_direct_mode()
        except Exception as e:
            error(f"  发布模式错误: {e}")
            return {"status": "error", "reason": str(e), "published": 0, "skipped": 0, "error": 1, "items": []}

    item = _process_aggregate_plugin(plugin_meta, dry_run=dry_run, tags=tags or source_meta.tags)
    result = {"status": item["status"], "published": 0, "skipped": 0, "error": 0, "items": [item]}
    if item["status"] == "published":
        result["published"] = 1
    elif item["status"] == "dry_run":
        result["status"] = "dry_run"
    elif item["status"] == "error":
        result["error"] = 1
    else:
        result["skipped"] = 1
    return result


def _skills_for_source(source: dict, source_meta) -> list:
    from plugin_build import SkillInfo, analyze_github

    discovered = list(source_meta.skills)
    repos = source.get("repos") or source.get("github_repos") or source.get("repositories") or []
    if isinstance(repos, str):
        repos = [repos]
    for repo in repos if isinstance(repos, list) else []:
        try:
            repo_meta = analyze_github(str(repo))
        except Exception as e:
            warn(f"  仓库扫描失败: {repo}: {e}")
            continue
        discovered.extend(repo_meta.skills)

    selected = source.get("skills")
    if selected and isinstance(selected, list):
        known = {s.name: s for s in discovered}
        return [known.get(str(name)) or SkillInfo(name=str(name), source=f"{source_meta.repository or source_meta.source_url}@{name}") for name in selected if name]

    seen = set()
    deduped = []
    for skill in discovered:
        if skill.name in seen:
            continue
        seen.add(skill.name)
        deduped.append(skill)
    return deduped


def _aggregate_meta_for_source(source: dict, source_meta, skills: list, tags: list | None = None):
    from plugin_build import PluginMeta, sanitize_name

    plugin_name = sanitize_name(str(source.get("plugin_name") or source.get("pluginName") or source.get("name") or source_meta.name))
    if not plugin_name.endswith("-skills") and len(skills) > 1:
        plugin_name = sanitize_name(f"{plugin_name}-skills")
    description = source_meta.description if _is_useful_source_description(source_meta.description) else ""
    if not description:
        origin = source_meta.repository or source_meta.source_url or source.get("url") or plugin_name
        description = f"Aggregated skills from {origin}"
    return PluginMeta(
        name=plugin_name,
        version=str(source.get("version") or source_meta.version or "1.0.0"),
        description=description,
        author=source_meta.author,
        license=source_meta.license,
        homepage=source_meta.homepage,
        repository=source_meta.repository,
        skills=skills,
        mcp_servers=source_meta.mcp_servers,
        env_vars=source_meta.env_vars,
        tags=tags or source_meta.tags,
        source_type=source_meta.source_type,
        source_url=source_meta.source_url,
    )


def _is_useful_source_description(description: str) -> bool:
    text = str(description or "").strip()
    if not text:
        return False
    blocked_markers = (
        "环境异常",
        "完成验证后即可继续访问",
        "微信扫一扫可打开此内容",
        "Scan with Weixin",
        "WeChat verification page",
    )
    return not any(marker in text for marker in blocked_markers)


def _process_aggregate_plugin(meta, dry_run: bool, tags: list | None = None) -> dict:
    from plugin_build import build_plugin

    score = evaluate_quality(meta)
    print(f"  {COLOR_DARKGRAY}{meta.name}: 质量评分 {score}/100{COLOR_RESET}")
    if score < MIN_QUALITY_SCORE:
        warn(f"  [SKIP] {meta.name} 质量分低于阈值 ({score} < {MIN_QUALITY_SCORE})")
        return {"status": "skip", "name": meta.name, "reason": f"low quality score: {score}"}

    if not dry_run and already_published(meta.name, meta.version):
        info(f"  [SKIP] 已发布同版本: {meta.name} v{meta.version}")
        return {"status": "skip", "name": meta.name, "reason": "already published"}

    try:
        cfg = _plugin_config_for_meta(meta)
        zip_path, _ = build_plugin(SERVER_DIR, {"config_yaml": yaml.dump(cfg, allow_unicode=True, sort_keys=False), "mode": "inline"})
        info(f"  [OK] 构建完成: {meta.name} -> {zip_path}")
    except Exception as e:
        error(f"  构建失败: {meta.name}: {e}")
        return {"status": "error", "name": meta.name, "reason": str(e)}

    if dry_run:
        info(f"  [DRY-RUN] 跳过发布: {meta.name}")
        return {"status": "dry_run", "name": meta.name, "zip_path": str(zip_path), "skills": [s.name for s in meta.skills]}

    try:
        result = publish_local(zip_path, tags=tags or meta.tags, scope="public")
        info(f"  [OK] 直连发布成功: {result.get('name', meta.name)}")
        return {"status": "published", "name": meta.name, "data": result, "skills": [s.name for s in meta.skills]}
    except Exception as e:
        error(f"  发布失败: {meta.name}: {e}")
        return {"status": "error", "name": meta.name, "reason": str(e)}


def _plugin_config_for_meta(meta) -> dict:
    return {
        "name": meta.name,
        "version": meta.version,
        "description": meta.description,
        "author": meta.author,
        "license": meta.license,
        "homepage": meta.homepage,
        "repository": {"type": "git", "url": meta.repository} if meta.repository else "",
        "keywords": meta.tags,
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                **({"source": s.source} if s.source else {}),
            }
            for s in meta.skills
        ],
        "mcpServers": meta.mcp_servers,
        "envVars": meta.env_vars,
    }


# ============================================================
# 每日配额调度（服务端内置定时捞取）
# ============================================================

# 默认每日发布配额（env AGENTBUDDY_CRAWL_QUOTA 可覆盖）
DEFAULT_DAILY_QUOTA = 10
STATE_FILE = SERVER_DIR / "data" / "crawler-state.json"


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def load_state() -> dict:
    """读取调度状态：{date, published, last_run, last_result}。"""
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        warn(f"写入调度状态失败: {e}")


def get_daily_progress() -> dict:
    """今日进度：{date, published, quota, remaining}。"""
    state = load_state()
    quota = int(os.environ.get("AGENTBUDDY_CRAWL_QUOTA", str(DEFAULT_DAILY_QUOTA)))
    if state.get("date") != _today():
        return {"date": _today(), "published": 0, "quota": quota, "remaining": quota}
    published = int(state.get("published", 0))
    return {"date": _today(), "published": published, "quota": quota,
            "remaining": max(0, quota - published)}


def run_daily(quota: int | None = None, force: bool = False) -> dict:
    """每日定时的定量捞取：遍历启用源，发布满 quota 个即停。

    状态持久化到 data/crawler-state.json，服务重启不会重复发布当天额度。
    force=True 时忽略已发布计数（用于手动补跑，仍受 quota 限制）。
    """
    if quota is None:
        quota = int(os.environ.get("AGENTBUDDY_CRAWL_QUOTA", str(DEFAULT_DAILY_QUOTA)))
    quota = max(0, quota)

    state = load_state()
    if state.get("date") != _today():
        state = {"date": _today(), "published": 0}
    if force:
        state["published"] = 0

    already = int(state.get("published", 0))
    remaining = max(0, quota - already)
    header(f"Crawler Daily Run (quota={quota}, published={already}, remaining={remaining})")

    results = {"published": 0, "skipped": 0, "error": 0, "quota": quota,
               "already_today": already, "stopped_reason": "sources_exhausted"}
    if remaining <= 0:
        info("今日配额已满，跳过")
        results["stopped_reason"] = "quota_reached"
        state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state["last_result"] = results
        save_state(state)
        return results

    sources = [s for s in load_sources() if s.get("enabled", True)]
    if not sources:
        warn("无启用的源配置")
        results["stopped_reason"] = "no_sources"
        return results

    for source in sources:
        current = int(state.get("published", 0))
        if current >= quota:
            results["stopped_reason"] = "quota_reached"
            break
        try:
            r = crawl_and_publish(source, dry_run=False, remaining_quota=quota - current)
            _accumulate_crawl_result(results, r)
            published_delta = int(r.get("published", 0)) if "published" in r else (1 if r.get("status") == "published" else 0)
            state["published"] = int(state.get("published", 0)) + published_delta
            if r.get("stopped_reason") == "quota_reached" or int(state.get("published", 0)) >= quota:
                results["stopped_reason"] = "quota_reached"
                break
        except Exception as e:
            error(f"处理异常: {source.get('name')}: {e}")
            results["error"] += 1
        time.sleep(2)

    state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["last_result"] = results
    save_state(state)
    info(f"今日已发布 {state['published']}/{quota}，剩余源耗尽或配额已满")
    return results


# ============================================================
# CLI
# ============================================================

def _accumulate_crawl_result(results: dict, result: dict) -> None:
    has_counts = any(k in result for k in ("published", "skipped", "error", "items"))
    if has_counts:
        results["published"] = int(results.get("published", 0)) + int(result.get("published", 0))
        results["skipped"] = int(results.get("skipped", 0)) + int(result.get("skipped", 0))
        results["error"] = int(results.get("error", 0)) + int(result.get("error", 0))
    else:
        status = result.get("status")
        if status == "published":
            results["published"] = int(results.get("published", 0)) + 1
        elif status == "skip":
            results["skipped"] = int(results.get("skipped", 0)) + 1
        elif status == "error":
            results["error"] = int(results.get("error", 0)) + 1

    if result.get("status") == "dry_run":
        dry_run_items = [i for i in result.get("items", []) if i.get("status") == "dry_run"]
        results["dry_run"] = int(results.get("dry_run", 0)) + (len(dry_run_items) or 1)


def cmd_list():
    sources = load_sources()
    if not sources:
        warn("无源配置。使用 --add <url> 添加源。")
        return
    header("插件抓取源列表")
    for i, s in enumerate(sources):
        status = f"{COLOR_GREEN}[enabled]{COLOR_RESET}" if s.get("enabled", True) else f"{COLOR_DARKGRAY}[disabled]{COLOR_RESET}"
        schedule = s.get("schedule", "daily")
        print(f"  {i+1}. {status} {s.get('name', '?')} ({schedule})")
        print(f"     URL: {s.get('url', '-')}")
        print(f"     Tags: {', '.join(s.get('tags', [])) or '-'}")
        print()


def cmd_add(url: str, name: str = None, tags: str = None):
    sources = load_sources()
    if not name:
        name = url.rstrip("/").split("/")[-1]
    new_source = {
        "name": name,
        "url": url,
        "tags": [t.strip() for t in (tags or "").split(",") if t.strip()],
        "enabled": True,
        "schedule": "daily",
    }
    sources.append(new_source)
    save_sources(sources)
    info(f"[OK] 已添加源: {name}")
    hint(f"配置文件: {SOURCES_FILE}")


def cmd_remove(name: str):
    sources = load_sources()
    before = len(sources)
    sources = [s for s in sources if s.get("name") != name]
    if len(sources) == before:
        warn(f"未找到源: {name}")
        return
    save_sources(sources)
    info(f"[OK] 已移除源: {name}")


def cmd_run(source_name: str | None = None, dry_run: bool = False):
    sources = load_sources()
    if not sources:
        warn("无源配置。使用 --add <url> 添加源。")
        return

    if source_name:
        sources = [s for s in sources if source_name.lower() in s.get("name", "").lower()]
        if not sources:
            warn(f"未匹配到源: {source_name}")
            return

    header(f"Crawler Run ({'dry-run' if dry_run else 'live'})")
    print(f"  Server: {SERVER_URL}")
    print(f"  Sources: {len(sources)} (filtered by enabled)")

    results = {"published": 0, "skipped": 0, "error": 0, "dry_run": 0}
    for source in sources:
        if not source.get("enabled", True):
            continue
        try:
            r = crawl_and_publish(source, dry_run=dry_run)
            _accumulate_crawl_result(results, r)
        except Exception as e:
            error(f"处理异常: {source.get('name')}: {e}")
            results["error"] += 1
        time.sleep(2)  # 避免请求过快

    header("Crawler Summary")
    info(f"  Published: {results['published']}")
    print(f"  {COLOR_DARKGRAY}Skipped: {results['skipped']}{COLOR_RESET}")
    print(f"  {COLOR_DARKGRAY}Dry-run: {results['dry_run']}{COLOR_RESET}")
    if results["error"]:
        error(f"  Errors: {results['error']}")


def main():
    parser = argparse.ArgumentParser(
        prog="crawler",
        description="AgentBuddy 插件市场 — 定时抓取 Worker",
    )
    parser.add_argument("--source", "-s", default=None,
                        help="只执行指定源（名称模糊匹配）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只分析+构建，不发布")
    parser.add_argument("--list", action="store_true",
                        help="列出所有源及状态")
    parser.add_argument("--add", metavar="URL",
                        help="添加新源")
    parser.add_argument("--add-name", default=None,
                        help="添加源时的名称")
    parser.add_argument("--add-tags", default=None,
                        help="添加源时的标签（逗号分隔）")
    parser.add_argument("--remove", metavar="NAME",
                        help="移除源")
    parser.add_argument("--daily", action="store_true",
                        help="每日定时模式：按配额发布（env AGENTBUDDY_CRAWL_QUOTA，默认 10）")
    parser.add_argument("--quota", type=int, default=None,
                        help="本次配额（--daily 时生效）")
    parser.add_argument("--force", action="store_true",
                        help="忽略今日已发布计数（--daily 时生效）")
    args = parser.parse_args()

    if args.list:
        cmd_list()
        return
    if args.add:
        cmd_add(args.add, args.add_name, args.add_tags)
        return
    if args.remove:
        cmd_remove(args.remove)
        return
    if args.daily:
        run_daily(quota=args.quota, force=args.force)
        return
    cmd_run(source_name=args.source, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
