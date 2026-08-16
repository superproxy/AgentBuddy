#!/usr/bin/env python3
"""AgentBuddy 插件市场 — 定时抓取 Worker（CrawlerAgent + BuildAgent 双智能体架构）。

独立运行，不依赖 Flask 进程。两种调度方式：

1. crontab（备用）:
    # 凌晨 3 点跑 CrawlerAgent（产出 spec.yaml）
    0 3 * * * cd /path/to/AgentBuddy/server && python PluginMarketWorker.py --crawler-agent >> /var/log/agentbuddy-crawler-agent.log 2>&1
    # 凌晨 4 点跑 BuildAgent（读 spec 构建 + 发布）
    0 4 * * * cd /path/to/AgentBuddy/server && python PluginMarketWorker.py --build-agent >> /var/log/agentbuddy-build-agent.log 2>&1

2. 内置调度（推荐）：server/app.py 启动时自动开每日调度线程（默认凌晨 3 点，
   串联 CrawlerAgent + BuildAgent，发布满 quota 个即停）。

CLI:
    python PluginMarketWorker.py --crawler-agent            # 跑全部 CrawlerAgent 任务（产出 spec.yaml）
    python PluginMarketWorker.py --crawler-agent <name>     # 跑指定任务
    python PluginMarketWorker.py --build-agent              # 读 spec 构建 + 发布
    python PluginMarketWorker.py --build-agent --dry-run    # 读 spec 只构建不发布
    python PluginMarketWorker.py --list                     # 列出 CrawlerAgent 任务及状态

架构：
  CrawlerAgent（搜索智能体）：固定 channels + intent → 多源聚合搜索 → 抓正文
                             → 文章评级 → LLM 抽 skills → 写 spec.yaml
  BuildAgent（构建智能体）：读 spec.yaml（按 rating 降序）→ build_plugin 打 zip → 发布
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ── 路径设置 ──
SERVER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVER_DIR.parent
SOURCES_FILE = SERVER_DIR / "config" / "plugin-sources.yaml"

# server 目录用于导入 auth / plugin_build 等服务端模块。
sys.path.insert(0, str(SERVER_DIR))

import yaml  # noqa: E402

# 自动加载 server/.env（shell/system 环境变量优先，不被覆盖）
from _env_loader import load_env_file  # noqa: E402
load_env_file()

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

def _resolve_data_dir() -> Path:
    """解析数据目录：环境变量优先，相对路径相对 SERVER_DIR 解析（与 app.py 一致）。"""
    raw = os.environ.get("AGENTBUDDY_DATA_DIR")
    if not raw or not raw.strip():
        return SERVER_DIR / "data"
    p = Path(raw.strip())
    return p if p.is_absolute() else (SERVER_DIR / p).resolve()


DATA_DIR = _resolve_data_dir()
DB_FILE = DATA_DIR / "agentbuddy.db"
MARKET_DIR = DATA_DIR / "marketplace"

_auth_models = None  # 惰性加载（避免 CLI 模式强依赖 server 侧模块）


def server_mode() -> bool:
    """服务端直连模式判定：

    - SQLite backend：本地存在市场数据库文件（与 app.py 同机）
    - MySQL backend：已配置 AGENTBUDDY_DB_URL 即视为直连模式
    """
    try:
        import db as _db
        if _db.backend() == "mysql":
            return bool(os.environ.get("AGENTBUDDY_DB_URL"))
    except Exception:
        pass
    return DB_FILE.exists()


def _init_db_access():
    """惰性加载 auth.models，并按 backend 初始化数据库连接。

    - SQLite：用 DB_FILE（兼容旧行为）
    - MySQL：用环境变量 AGENTBUDDY_DB_URL（与 app.py 一致）
    """
    global _auth_models
    if _auth_models is not None:
        return _auth_models
    sys.path.insert(0, str(SERVER_DIR))
    from auth import models as auth_models
    # 按 backend 切换初始化路径
    try:
        import db as _db
        if _db.backend() == "mysql":
            url = os.environ.get("AGENTBUDDY_DB_URL", "").strip()
            if not url:
                raise RuntimeError("MySQL backend 需要配置 AGENTBUDDY_DB_URL")
            auth_models.set_mysql_url(url)
        else:
            auth_models.set_db_path(DB_FILE)
    except ImportError:
        # db 模块缺失时回退到 SQLite（兼容最小依赖场景）
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


def require_server_direct_mode() -> None:
    """后台捞取只允许服务端直连模式运行。"""
    if server_mode():
        return
    raise RuntimeError("crawler 需要在服务端数据目录运行；未找到市场数据库，不能发布")


# ============================================================
# 配置加载
# ============================================================

def load_channels() -> list[dict]:
    """从 plugin-sources.yaml 加载固定渠道池。"""
    if not SOURCES_FILE.exists():
        return []
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get("channels", []) or [])


def load_tasks() -> list[dict]:
    """从 plugin-sources.yaml 加载 CrawlerAgent 任务列表（tasks 段）。

    兼容旧的 discovery 段（已废弃，读取时自动识别）。
    """
    if not SOURCES_FILE.exists():
        return []
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tasks = data.get("tasks") or data.get("discovery") or []
    return list(tasks)


# ============================================================
# CrawlerAgent 命令
# ============================================================

def cmd_run_crawler_agent(task_name: str | None = None):
    """执行 CrawlerAgent 任务：搜索 → 抓取 → 评级 → 抽 skills → 写 spec.yaml（不构建不发布）。"""
    from crawler_agent import run_task, require_env

    # 启动检查：缺失环境变量直接退出
    require_env()

    tasks = load_tasks()
    if not tasks:
        warn("无 CrawlerAgent 任务配置。在 plugin-sources.yaml 增加 tasks 段。")
        return

    if task_name:
        tasks = [t for t in tasks if task_name.lower() in t.get("name", "").lower()]
        if not tasks:
            warn(f"未匹配到 CrawlerAgent 任务: {task_name}")
            return

    channels = load_channels()
    if not channels:
        warn("plugin-sources.yaml 未配置 channels 池，CrawlerAgent 无法运行。")
        return

    header(f"CrawlerAgent Run (tasks={sum(1 for t in tasks if t.get('enabled', True))})")
    spec_count = 0
    skip_count = 0
    err_count = 0
    for task in tasks:
        if not task.get("enabled", True):
            continue
        name = str(task.get("name", "")).strip()
        header(f"CrawlerAgent: {name}")
        info(f"  Intent: {task.get('intent', 'trending')}")
        try:
            results = run_task(task, channels)
        except Exception as e:
            error(f"  CrawlerAgent 异常: {name}: {e}")
            err_count += 1
            time.sleep(5)
            continue

        for r in results:
            if r.status == "spec":
                info(f"  [SPEC] {r.title[:60]} skills={r.skills} rating={r.rating}")
                spec_count += 1
            elif r.status == "skip":
                print(f"  {COLOR_DARKGRAY}[SKIP] {r.title[:60]}: {r.reason}{COLOR_RESET}")
                skip_count += 1
            elif r.status == "error":
                error(f"  [ERR]  {r.title[:60]}: {r.reason}")
                err_count += 1

        time.sleep(5)

    header("CrawlerAgent Summary")
    info(f"  Specs written: {spec_count}")
    print(f"  {COLOR_DARKGRAY}Skipped: {skip_count}{COLOR_RESET}")
    if err_count:
        error(f"  Errors: {err_count}")
    if spec_count:
        hint(f"  下一步：python PluginMarketWorker.py --build-agent  （读 spec 构建并发布）")


def hint(msg: str):
    print(f"{COLOR_CYAN}{msg}{COLOR_RESET}")


# ============================================================
# BuildAgent 命令
# ============================================================

def cmd_run_build_agent(dry_run: bool = False, max_publish: int = 0):
    """执行 BuildAgent：读 spec.yaml → build_plugin → 发布。

    Args:
        dry_run: True 则只构建不发布
        max_publish: 本次最多发布几个（0 表示不限）
    """
    from build_agent import run as build_run

    header(f"BuildAgent Run ({'dry-run' if dry_run else 'live'}"
           f"{f', max_publish={max_publish}' if max_publish > 0 else ''})")

    publish_fn = None
    already_published_fn = None
    if not dry_run:
        try:
            require_server_direct_mode()
        except Exception as e:
            error(f"  服务端直连模式不可用，仅构建不发布: {e}")
            dry_run = True
        else:
            publish_fn = publish_local
            already_published_fn = already_published_local

    results = build_run(
        dry_run=dry_run,
        publish_fn=publish_fn,
        already_published_fn=already_published_fn,
        max_publish=max_publish,
    )

    built = sum(1 for r in results if r.status == "built")
    published = sum(1 for r in results if r.status == "published")
    skipped = sum(1 for r in results if r.status == "skipped")
    errors = sum(1 for r in results if r.status == "error")
    header("BuildAgent Summary")
    info(f"  Published: {published}")
    print(f"  {COLOR_DARKGRAY}Built (not published): {built}{COLOR_RESET}")
    print(f"  {COLOR_DARKGRAY}Skipped: {skipped}{COLOR_RESET}")
    if errors:
        error(f"  Errors: {errors}")


# ============================================================
# 每日配额调度（服务端内置定时捞取）
# ============================================================

# 默认每日发布配额（env AGENTBUDDY_CRAWL_QUOTA 可覆盖）
DEFAULT_DAILY_QUOTA = 50
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
    """每日定时的定量捞取：串联 CrawlerAgent + BuildAgent，发布满 quota 个即停。

    流程：
      1. CrawlerAgent 跑所有启用任务 → 产出 spec.yaml
      2. BuildAgent 读 spec（按 rating 降序）→ 构建 → 发布，max_publish=今日剩余配额

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

    results = {"spec_written": 0, "published": 0, "skipped": 0, "error": 0,
               "quota": quota, "already_today": already,
               "stopped_reason": "completed"}
    # 注意：配额已满时仍跑 CrawlerAgent 生成 spec（每日沉淀知识），
    # 仅跳过 BuildAgent 发布阶段。

    # ── 1. CrawlerAgent：搜索 → 抓取 → 评级 → 抽 skills → 写 spec.yaml ──
    try:
        info("[1/2] 启动 CrawlerAgent（搜索 + 抓取 + 评级 + 抽 skills）...")
        from crawler_agent import run_task, require_env
        require_env()
        tasks = [t for t in load_tasks() if t.get("enabled", True)]
        channels = load_channels()
        if not tasks or not channels:
            warn("无启用的 CrawlerAgent 任务或 channels 池，跳过抓取")
            results["stopped_reason"] = "no_tasks"
        else:
            for task in tasks:
                name = str(task.get("name", "")).strip()
                try:
                    crawl_results = run_task(task, channels)
                    for r in crawl_results:
                        if r.status == "spec":
                            results["spec_written"] += 1
                        elif r.status == "skip":
                            results["skipped"] += 1
                        elif r.status == "error":
                            results["error"] += 1
                except Exception as e:
                    error(f"CrawlerAgent 任务 {name} 异常: {e}")
                    results["error"] += 1
                time.sleep(3)
            info(f"[1/2] CrawlerAgent 完成：产出 {results['spec_written']} 个 spec")
    except Exception as e:
        error(f"CrawlerAgent 阶段失败: {e}")
        results["stopped_reason"] = "crawler_error"
        results["error"] += 1
        state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state["last_result"] = results
        save_state(state)
        return results

    # 无 spec 产出，直接结束
    if results["spec_written"] == 0:
        warn("CrawlerAgent 未产出任何 spec，跳过 BuildAgent")
        results["stopped_reason"] = "no_specs"
        state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state["last_result"] = results
        save_state(state)
        return results

    # ── 2. BuildAgent：读 spec（按 rating 降序）→ 构建 → 发布（max_publish 限流）──
    if remaining <= 0:
        info("今日发布配额已满，跳过 BuildAgent（spec 已照常生成）")
        results["stopped_reason"] = "quota_reached"
        state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state["last_result"] = results
        save_state(state)
        return results
    try:
        info(f"[2/2] 启动 BuildAgent（构建 + 发布，max_publish={remaining}）...")
        publish_fn = None
        already_published_fn = None
        try:
            require_server_direct_mode()
            publish_fn = publish_local
            already_published_fn = already_published_local
        except Exception as e:
            warn(f"服务端直连模式不可用，仅构建不发布: {e}")

        from build_agent import run as build_run
        build_results = build_run(
            dry_run=False,
            publish_fn=publish_fn,
            already_published_fn=already_published_fn,
            max_publish=remaining,
        )
        published_delta = sum(1 for r in build_results if r.status == "published")
        results["published"] = published_delta
        if published_delta < remaining:
            results["stopped_reason"] = "specs_exhausted"
        else:
            results["stopped_reason"] = "quota_reached"
        info(f"[2/2] BuildAgent 完成：发布 {published_delta} 个")
    except Exception as e:
        error(f"BuildAgent 阶段失败: {e}")
        results["stopped_reason"] = "build_error"
        results["error"] += 1

    # 更新今日已发布计数
    state["published"] = int(state.get("published", 0)) + results["published"]
    state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["last_result"] = results
    save_state(state)
    info(f"今日已发布 {state['published']}/{quota}（本次 +{results['published']}）")
    return results


# ============================================================
# CLI
# ============================================================

def cmd_list_discovery():
    """列出 CrawlerAgent 任务（基于固定 channels 池 + intent 配置）。"""
    channels = load_channels()
    tasks = load_tasks()
    if not channels and not tasks:
        warn("无 channels/tasks 配置。在 plugin-sources.yaml 增加 channels 池与 tasks 段。")
        return

    if channels:
        header("固定渠道池（channels）")
        for c in channels:
            print(f"  - {c.get('id', '?'):12s} {c.get('domain', '-'):24s} "
                  f"{c.get('name', '')}  (weight={c.get('weight', 10)})")

    if tasks:
        header("CrawlerAgent 任务列表（tasks）")
        # 构造 id → domain 映射，用于解析每个任务的 channels 引用
        ch_map = {str(c.get("id", "")).lower(): c for c in channels}
        for i, d in enumerate(tasks):
            status = (f"{COLOR_GREEN}[enabled]{COLOR_RESET}"
                      if d.get("enabled", True)
                      else f"{COLOR_DARKGRAY}[disabled]{COLOR_RESET}")
            schedule = d.get("schedule", "daily")
            print(f"  {i+1}. {status} {d.get('name', '?')} ({schedule})")
            print(f"     Intent: {d.get('intent', 'trending')}")
            # 解析 channels 引用 → domain 列表
            task_ch_ids = d.get("channels") or []
            if task_ch_ids:
                domains = [ch_map[str(cid).lower()].get("domain", "?")
                           for cid in task_ch_ids if str(cid).lower() in ch_map]
                ch_text = ", ".join(domains) if domains else "(无匹配渠道)"
            else:
                ch_text = "(全部渠道)"
            print(f"     Channels: {ch_text}")
            print(f"     Max results: {d.get('max_results', 15)}")
            print(f"     Min rating: {d.get('min_rating', 40)}")
            print()


def main():
    parser = argparse.ArgumentParser(
        prog="crawler",
        description="AgentBuddy 插件市场 — 定时抓取 Worker（CrawlerAgent + BuildAgent）",
    )
    # CrawlerAgent
    parser.add_argument("--crawler-agent", default=None, const="__all__", nargs="?", metavar="NAME",
                        help="执行 CrawlerAgent 任务（搜索智能体）：搜索 → 抓取 → 评级 → 抽 skills → 写 spec.yaml。"
                             "不带值=跑全部启用任务，带值=模糊匹配任务名")
    # BuildAgent
    parser.add_argument("--build-agent", action="store_true",
                        help="执行 BuildAgent（构建智能体）：读 spec.yaml → 构建 → 发布。"
                             "可配合 --dry-run 只构建不发布")
    parser.add_argument("--max-publish", type=int, default=0,
                        help="BuildAgent 本次最多发布几个（0 表示不限，默认 0）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只分析+构建，不发布")
    # 列表
    parser.add_argument("--list", action="store_true",
                        help="列出所有 CrawlerAgent 任务及状态（基于固定 channels 池 + intent）")
    # 每日调度
    parser.add_argument("--daily", action="store_true",
                        help="执行每日调度：串联 CrawlerAgent + BuildAgent，发布满 quota 个即停")
    parser.add_argument("--quota", type=int, default=None,
                        help="每日发布配额（覆盖 env AGENTBUDDY_CRAWL_QUOTA，仅 --daily 生效）")
    parser.add_argument("--force", action="store_true",
                        help="忽略今日已发布计数，从头开始（仅 --daily 生效）")
    args = parser.parse_args()

    if args.list:
        cmd_list_discovery()
        return
    if args.daily:
        run_daily(quota=args.quota, force=args.force)
        return
    if args.crawler_agent is not None:
        task_name = None if args.crawler_agent == "__all__" else args.crawler_agent
        cmd_run_crawler_agent(task_name=task_name)
        return
    if args.build_agent:
        cmd_run_build_agent(dry_run=args.dry_run, max_publish=args.max_publish)
        return

    # 无参数时打印帮助
    parser.print_help()


if __name__ == "__main__":
    main()
