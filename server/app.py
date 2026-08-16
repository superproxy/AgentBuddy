"""AgentBuddy 平台服务 — 独立部署入口。

作为远程服务运行，提供插件市场 + AI 插件生成功能。
桌面应用通过 HTTP API 调用本服务。

运行方式：
    cd server && python app.py
    # 或
    python -m server.app

环境变量：
    AGENTBUDDY_SERVER_HOST  监听地址（默认 0.0.0.0）
    AGENTBUDDY_SERVER_PORT  监听端口（默认 5001）
    AGENTBUDDY_DATA_DIR     数据目录（默认 ./data）
    AGENTBUDDY_LLM_CONFIG   LLM 配置文件路径（默认 ./config/llm/llm.yaml）
"""
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

# server 目录加入 sys.path，使 marketplace / ai_generator 可 import
SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

# 数据目录
DATA_DIR = Path(os.environ.get("AGENTBUDDY_DATA_DIR", SERVER_DIR / "data"))
MARKETPLACE_DIR = DATA_DIR / "marketplace"

# LLM 配置
LLM_CONFIG_PATH = Path(os.environ.get(
    "AGENTBUDDY_LLM_CONFIG",
    SERVER_DIR / "config" / "llm" / "llm.yaml",
))

# 项目根目录（用于 ai_generator 读取 skills/rules 等）
PROJECT_ROOT = SERVER_DIR


def create_app() -> Flask:
    """创建并配置 Flask 应用。"""
    app = Flask(__name__)
    CORS(app)  # 允许跨域（桌面应用调用）

    # 确保数据目录存在
    MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)

    # 初始化用户认证数据库
    from auth.models import set_db_path, set_marketplace_dir, migrate_index_json
    DB_PATH = DATA_DIR / "agentbuddy.db"
    set_db_path(DB_PATH)
    set_marketplace_dir(MARKETPLACE_DIR)
    migrate_index_json()

    # 注册认证 + 团队路由
    from auth.routes import create_auth_bp
    auth_bp = create_auth_bp()
    app.register_blueprint(auth_bp, url_prefix="/api")

    # 注册插件市场路由
    from marketplace import create_marketplace_bp
    bp = create_marketplace_bp(marketplace_dir=MARKETPLACE_DIR)
    app.register_blueprint(bp, url_prefix="/api/marketplace")

    # 注册 AI 生成路由
    from ai_generator.routes import create_ai_bp
    ai_bp = create_ai_bp(project_root=PROJECT_ROOT, llm_config_path=LLM_CONFIG_PATH)
    app.register_blueprint(ai_bp, url_prefix="/api/ai")

    # === 定时捞取（Crawler）管理 API + 内置每日调度 ===
    # 环境变量：
    #   AGENTBUDDY_CRAWL_ENABLED=0       关闭内置调度（默认开）
    #   AGENTBUDDY_CRAWL_HOUR=3          每日执行时刻（0-23，默认 3 点）
    #   AGENTBUDDY_CRAWL_QUOTA=10        每日发布配额（默认 10）
    from auth.middleware import require_auth, get_current_user
    from flask import g as _g

    @app.route("/api/crawler/status", methods=["GET"])
    @require_auth
    def crawler_status():
        """捞取调度状态：今日进度 + 源列表 + 上次运行结果。"""
        import crawler as crawler_mod
        import yaml as _yaml
        from pathlib import Path as _P
        sources_file = _P(__file__).resolve().parent / "config" / "plugin-sources.yaml"
        try:
            cfg = _yaml.safe_load(sources_file.read_text(encoding="utf-8")) or {}
            sources = cfg.get("sources", [])
        except Exception:
            sources = []
        state = crawler_mod.load_state()
        return jsonify({
            "ok": True,
            "today": crawler_mod.get_daily_progress(),
            "scheduler": {
                "enabled": os.environ.get("AGENTBUDDY_CRAWL_ENABLED", "1") != "0",
                "hour": int(os.environ.get("AGENTBUDDY_CRAWL_HOUR", "3")),
                "quota": int(os.environ.get("AGENTBUDDY_CRAWL_QUOTA",
                                            str(crawler_mod.DEFAULT_DAILY_QUOTA))),
            },
            "sources": [{"name": s.get("name"), "enabled": s.get("enabled", True)} for s in sources],
            "last_run": state.get("last_run", ""),
            "last_result": state.get("last_result"),
        })

    @app.route("/api/crawler/run", methods=["POST"])
    @require_auth
    def crawler_run():
        """手动触发一次定量捞取（仅 admin）。Body: {quota?, force?}。"""
        from flask import request as _req
        if (_g.current_user or {}).get("role") != "admin":
            return jsonify({"ok": False, "error": "仅管理员可手动触发捞取"}), 403
        body = _req.get_json(silent=True) or {}
        import crawler as crawler_mod
        quota = body.get("quota")
        force = bool(body.get("force", False))
        result = crawler_mod.run_daily(
            quota=int(quota) if isinstance(quota, (int, float)) else None,
            force=force,
        )
        return jsonify({"ok": True, "result": result, "today": crawler_mod.get_daily_progress()})

    def _start_crawler_scheduler():
        """内置每日调度线程：到点执行 run_daily（状态文件保证重启不重复）。"""
        import threading
        import time as _time
        import crawler as crawler_mod

        def _loop():
            hour = int(os.environ.get("AGENTBUDDY_CRAWL_HOUR", "3"))
            while True:
                try:
                    now = _time.localtime()
                    # 计算距离下一个 hour 点的秒数
                    target = _time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour, 0, 0, 0, 0, -1))
                    if target <= _time.time():
                        target += 86400
                    _time.sleep(max(1, target - _time.time()))
                    # 到点：state 里当天已满额则 run_daily 内部自动跳过
                    crawler_mod.run_daily()
                except Exception as e:  # 调度线程绝不能挂
                    print(f"[crawler-scheduler] 运行异常: {e}", flush=True)
                    _time.sleep(600)

        t = threading.Thread(target=_loop, daemon=True, name="crawler-scheduler")
        t.start()
        print(f"[crawler-scheduler] 已启动：每日 {os.environ.get('AGENTBUDDY_CRAWL_HOUR', '3')} 点执行，"
              f"每日发布配额 {os.environ.get('AGENTBUDDY_CRAWL_QUOTA', str(crawler_mod.DEFAULT_DAILY_QUOTA))} 个",
              flush=True)
        return t

    if os.environ.get("AGENTBUDDY_CRAWL_ENABLED", "1") != "0":
        _start_crawler_scheduler()

    # 健康检查
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"ok": True, "service": "AgentBuddy Server"})

    # === Web 前端（插件市场官网） ===
    WEB_DIR = SERVER_DIR / "web"

    @app.route("/")
    def web_index():
        return send_from_directory(str(WEB_DIR), "index.html")

    @app.route("/<path:path>")
    def web_static(path):
        full = WEB_DIR / path
        if full.exists():
            return send_from_directory(str(WEB_DIR), path)
        # 未匹配的路径返回首页（SPA fallback）
        return send_from_directory(str(WEB_DIR), "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("AGENTBUDDY_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("AGENTBUDDY_SERVER_PORT", "5001"))
    print(f"AgentBuddy Server starting on {host}:{port}")
    print(f"  Data dir: {DATA_DIR}")
    print(f"  LLM config: {LLM_CONFIG_PATH}")
    app.run(host=host, port=port, debug=True, threaded=True)
