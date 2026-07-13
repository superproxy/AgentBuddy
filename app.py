"""AdeBuddy 配置工具 - pywebview 桌面启动器。

在后台线程启动 Flask 服务，前台用 pywebview 打开嵌入窗口。
- 默认窗口 1400x900，最小 1000x680
- 窗口关闭时自动结束 Flask 进程
- pywebview 未安装时回退到系统浏览器

用法：
    python app.py                 # 默认 5050 端口
    python app.py --port 5050     # 指定端口
"""
import argparse
import runpy
import sys
import threading
import time
import webbrowser
from pathlib import Path

def _resolve_project_root() -> Path:
    """Frozen-aware：dev 用 __file__ 上级，frozen 用 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _redirect_stdio_to_log(project_root: Path) -> None:
    """windowed 模式下 stdout/stderr 被丢弃，重定向到 exe 目录 app.log 便于排查。

    仅在 frozen 且无控制台（stdout 非 tty）时生效；dev 模式或带控制台时不干预。
    """
    if not getattr(sys, "frozen", False):
        return
    # windowed 模式 stdout 不是 tty（指向 /dev/null 或为 None）；带控制台则是 tty
    out_is_tty = bool(sys.stdout and sys.stdout.isatty())
    err_is_tty = bool(sys.stderr and sys.stderr.isatty())
    if out_is_tty and err_is_tty:
        return
    try:
        log_path = project_root / "app.log"
        log_fp = open(log_path, "a", encoding="utf-8", buffering=1)
        if not out_is_tty:
            sys.stdout = log_fp
        if not err_is_tty:
            sys.stderr = log_fp
        print(f"\n===== AdeBuddy 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
    except Exception:
        pass  # 重定向失败也不阻塞启动


PROJECT_ROOT = _resolve_project_root()
TOOLS_DIR = PROJECT_ROOT / "tools"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# 把 tools/ 加入 sys.path 以便 import config_server
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _run_bundled_script(script_name: str, extra_args: list) -> int:
    """在当前进程中运行 scripts/<name>.py，捕获 sys.exit 并返回退出码。
    用于 PyInstaller frozen 模式下替代 `python script.py` 的子进程调用。
    """
    candidates = [
        SCRIPTS_DIR / f"{script_name}.py",
        PROJECT_ROOT / "scripts" / f"{script_name}.py",
    ]
    # frozen 模式：脚本可能被打包到 sys._MEIPASS，作为最后兜底
    # （优先用 PROJECT_ROOT/scripts 的副本，使脚本的 __file__ 解析出正确的 PROJECT_ROOT）
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.append(meipass / "scripts" / f"{script_name}.py")

    script_path = next((p for p in candidates if p.exists()), None)
    if script_path is None:
        print(f"[--run][ERROR] 找不到脚本: {script_name}.py", file=sys.stderr)
        return 2

    # 设置 sys.argv 让脚本内的 argparse 正常工作
    saved_argv = sys.argv
    sys.argv = [str(script_path)] + list(extra_args)
    try:
        runpy.run_path(str(script_path), run_name="__main__")
        return 0
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return 1
    finally:
        sys.argv = saved_argv


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    """轮询 URL 直到服务就绪或超时。"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _bootstrap_from_bundle() -> None:
    """frozen 模式首次运行：把 bundled 只读资源从 _MEIPASS 复制到 exe 目录（PROJECT_ROOT）。

    这样所有脚本的 `source_dir = script_dir.parent` 逻辑无需改动即可工作，
    用户数据（llm.yaml/mcp.yaml/config/）也在 exe 目录可写。
    已存在的目标不覆盖，保留用户修改；删除 exe 目录可重置。
    """
    if not getattr(sys, "frozen", False):
        return
    import shutil
    meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    project = Path(sys.executable).parent

    resources = [
        "scripts", "template", "tools",
        "AGENTS.md",
    ]
    copied = []
    for name in resources:
        src = meipass / name
        dst = project / name
        if not src.exists() or dst.exists():
            continue
        try:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=False)
            else:
                shutil.copy2(src, dst)
            copied.append(name)
        except Exception as e:
            print(f"[bootstrap][WARN] 复制 {name} 失败: {e}", file=sys.stderr)

    if copied:
        print(f"[bootstrap] 首次运行，已从 bundle 复制资源到 exe 目录: {', '.join(copied)}")
    # 写入标记，便于诊断
    try:
        (project / ".bundle_bootstrapped").write_text("1", encoding="utf-8")
    except Exception:
        pass


def start_flask_thread(host: str, port: int) -> threading.Thread:
    """在守护线程中启动 Flask 服务（不自动打开浏览器）。"""
    import config_server  # noqa: E402  (位于 tools/)

    # 调用 ensure 函数确保配置文件存在
    config_server._ensure_llm_file()
    config_server._ensure_mcp_config_file()

    def _run():
        config_server.app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True, name="flask-backend")
    t.start()
    return t


class _DownloadApi:
    """暴露给前端的文件保存接口（pywebview JS-Python 桥接）。

    前端 fetch 导出接口拿到 blob → 转 base64 → 调用 window.pywebview.api.save_file()
    → 原生保存对话框 → 写盘，规避 pywebview 不处理 attachment 下载的问题。
    """
    def save_file(self, filename, data_base64):
        import base64 as _b64
        import tkinter as _tk
        from tkinter import filedialog as _fd

        root = _tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        # 根据扩展名推断文件类型过滤器
        ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".zip"
        if ext == ".zip":
            filetypes = [("ZIP 压缩包", "*.zip"), ("所有文件", "*.*")]
        elif ext in (".yaml", ".yml"):
            filetypes = [("YAML 文件", "*.yaml *.yml"), ("所有文件", "*.*")]
        else:
            filetypes = [("所有文件", "*.*")]

        path = _fd.asksaveasfilename(
            defaultextension=ext,
            initialfile=filename,
            filetypes=filetypes,
            parent=root,
        )
        root.destroy()

        if not path:
            return {"ok": False, "error": "cancelled"}

        try:
            raw = _b64.b64decode(data_base64)
            with open(path, "wb") as f:
                f.write(raw)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def open_with_pywebview(url: str, title: str = "AdeBuddy 配置工具", width: int = 1400, height: int = 900) -> bool:
    """用 pywebview 打开窗口，成功返回 True。"""
    try:
        import webview  # type: ignore
    except ImportError:
        return False

    api = _DownloadApi()
    window = webview.create_window(title, url, width=width, height=height,
                                   min_size=(1000, 680), text_select=True, js_api=api)
    webview.start()
    # webview.start 阻塞直到窗口关闭
    try:
        window.destroy()
    except Exception:
        pass
    return True


def main():
    parser = argparse.ArgumentParser(description="AdeBuddy 配置工具 (pywebview 桌面版)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--no-webview", action="store_true", help="不使用 pywebview，回退到系统浏览器")
    parser.add_argument("--run", metavar="SCRIPT", help="frozen 模式下运行 bundled scripts/<name>.py（内部用，不启动窗口）")
    args, extra = parser.parse_known_args()

    # --run 派发：在当前进程运行 scripts 下的脚本，供 config_server 子进程调用
    if args.run:
        # --run 子进程由 config_server 捕获 stdout，无需重定向
        rc = _run_bundled_script(args.run, extra)
        sys.exit(rc)

    # windowed 模式：stdout/stderr 为 None，重定向到 exe 目录 app.log
    _redirect_stdio_to_log(PROJECT_ROOT)

    # frozen 模式首次运行：从 bundle 复制资源到 exe 目录
    _bootstrap_from_bundle()

    url = f"http://{args.host}:{args.port}"
    print(f"[App] 项目根: {PROJECT_ROOT}")
    print(f"[App] 配置目录: {PROJECT_ROOT / 'config'}")
    print(f"[App] 启动 Flask: {url}")

    start_flask_thread(args.host, args.port)

    if not _wait_for_server(url, timeout=15.0):
        print("[App][ERROR] Flask 启动超时", file=sys.stderr)
        sys.exit(1)
    print(f"[App] Flask 就绪: {url}")

    if args.no_webview:
        webbrowser.open(url)
        print("[App] 已用系统浏览器打开，Ctrl+C 退出 Flask")
        # 阻塞主线程，让 Flask 守护线程持续运行
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[App] 退出")
        return

    used = open_with_pywebview(url)
    if not used:
        print("[App][WARN] 未安装 pywebview，回退到系统浏览器。可执行: pip install pywebview")
        webbrowser.open(url)
        print("[App] 已用系统浏览器打开，Ctrl+C 退出 Flask")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[App] 退出")


if __name__ == "__main__":
    main()
