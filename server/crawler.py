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
  4. download_skills + package（inline 模式）
  5. publish 到市场（用服务账号 token）
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

# ── 路径设置 ──
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent
CLI_DIR = PROJECT_ROOT / "cli"
SOURCES_FILE = SERVER_DIR / "config" / "plugin-sources.yaml"

# server 目录 + cli 目录加入 sys.path
sys.path.insert(0, str(SERVER_DIR))
sys.path.insert(0, str(CLI_DIR))

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
CRAWLER_USERNAME = os.environ.get("AGENTBUDDY_CRAWLER_USER", "crawler")
CRAWLER_PASSWORD = os.environ.get("AGENTBUDDY_CRAWLER_PASS", "")
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

def already_published(name: str, version: str, token: str) -> bool:
    """查询市场是否已发布同名同版本的插件。"""
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
# 认证
# ============================================================

def get_crawler_token() -> str:
    """用服务账号登录获取 token。"""
    from agentctl.lib import auth as market_auth
    token = market_auth.get_token()
    if token:
        return token

    if not CRAWLER_PASSWORD:
        error("未设置 CRAWLER_PASSWORD 环境变量，且本地无 token")
        error("请先执行: agentctl plugin auth login -u crawler -p <password>")
        sys.exit(1)

    try:
        data = market_auth.login(CRAWLER_USERNAME, CRAWLER_PASSWORD, SERVER_URL)
        return data["token"]
    except Exception as e:
        error(f"crawler 账号登录失败: {e}")
        sys.exit(1)


# ============================================================
# 核心：抓取 + 构建 + 发布
# ============================================================

def crawl_and_publish(source: dict, dry_run: bool = False) -> dict:
    """处理单个源：分析 → 评分 → 下载 → 构建 → 发布。"""
    from agentctl.lib.plugin_builder import PluginBuilder
    from agentctl.lib import auth as market_auth

    name = source.get("name", "")
    url = source.get("url", "")
    tags = source.get("tags", [])

    if not url:
        warn(f"  [SKIP] 源无 URL: {name}")
        return {"status": "skip", "reason": "no url"}

    header(f"Crawling: {name}")
    info(f"  URL: {url}")

    # 1. 分析来源
    try:
        builder = PluginBuilder(PROJECT_ROOT)
        meta = builder.analyze_source(url)
    except Exception as e:
        error(f"  分析失败: {e}")
        return {"status": "error", "reason": str(e)}

    info(f"  Name: {meta.name}")
    info(f"  Skills: {len(meta.skills)}")
    info(f"  MCP Servers: {len(meta.mcp_servers)}")
    info(f"  Description: {meta.description[:80]}")

    # 2. 质量评分
    score = evaluate_quality(meta)
    print(f"  {COLOR_DARKGRAY}质量评分: {score}/100{COLOR_RESET}")
    if score < MIN_QUALITY_SCORE:
        warn(f"  [SKIP] 质量分低于阈值 ({score} < {MIN_QUALITY_SCORE})")
        return {"status": "skip", "reason": f"low quality score: {score}"}

    # 3. 去重检查
    if not dry_run:
        token = get_crawler_token()
        if already_published(meta.name, meta.version, token):
            info(f"  [SKIP] 已发布同版本: {meta.name} v{meta.version}")
            return {"status": "skip", "reason": "already published"}

    # 4. 下载 skills
    try:
        selected = source.get("skills")
        skill_dirs = builder.download_skills(meta, selected=selected)
    except Exception as e:
        warn(f"  skill 下载失败（继续构建）: {e}")
        skill_dirs = []

    # 5. 构建 zip
    if source.get("tags"):
        meta.tags = source["tags"]
    try:
        cfg = builder.generate_yaml(meta)
        output_dir = SERVER_DIR / "data" / "crawler-output"
        zip_path = builder.package(cfg, skill_dirs, mode="inline", output_dir=output_dir)
        info(f"  [OK] 构建完成: {zip_path}")
    except Exception as e:
        error(f"  构建失败: {e}")
        return {"status": "error", "reason": str(e)}

    # 6. 发布
    if dry_run:
        info(f"  [DRY-RUN] 跳过发布")
        return {"status": "dry_run", "zip_path": str(zip_path)}

    try:
        token = get_crawler_token()
        result = builder.publish(
            zip_path, SERVER_URL, token,
            tags=tags or meta.tags, scope="public",
        )
        info(f"  [OK] 发布成功: {result.get('name', meta.name)}")
        return {"status": "published", "data": result}
    except Exception as e:
        error(f"  发布失败: {e}")
        return {"status": "error", "reason": str(e)}


# ============================================================
# CLI
# ============================================================

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
            status = r.get("status", "error")
            if status == "published":
                results["published"] += 1
            elif status == "skip":
                results["skipped"] += 1
            elif status == "dry_run":
                results["dry_run"] += 1
            else:
                results["error"] += 1
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
    cmd_run(source_name=args.source, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
