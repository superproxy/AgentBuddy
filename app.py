"""飞翼 - pywebview 桌面启动器。

在后台线程启动 Flask 服务，前台用 pywebview 打开嵌入窗口。
- 默认窗口 1400x900，最小 1000x680
- 窗口关闭时自动结束 Flask 进程
- pywebview 未安装时回退到系统浏览器

用法：
    python app.py                 # 默认 5050 端口
    python app.py --port 5050     # 指定端口
"""
import argparse
import os
import runpy
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _setup_ssl_certs() -> None:
    """PyInstaller frozen 模式下，Python 默认 SSL verify path 指向构建机路径，
    在用户机器上不存在，导致 HTTPS 请求报 CERTIFICATE_VERIFY_FAILED。

    优先用 certifi 的 cacert.pem（PyInstaller hook 会打包到 _MEIPASS）；
    找不到时回退到 macOS 系统钥匙串导出的根证书。
    必须在任何 requests / urllib 调用之前执行。
    """
    ca_path = None
    try:
        import certifi
        ca_path = certifi.where()
    except Exception:
        pass

    # frozen 模式下 certifi.where() 可能指向不存在的源码路径，校验一下
    if not ca_path or not os.path.isfile(ca_path):
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                cand = Path(meipass) / "certifi" / "cacert.pem"
                if cand.is_file():
                    ca_path = str(cand)
        if (not ca_path or not os.path.isfile(ca_path)) and sys.platform == "darwin":
            # 回退：从 macOS 系统钥匙串导出根证书（Keychain Verifier Settings）
            cand = "/etc/ssl/cert.pem"
            if os.path.isfile(cand):
                ca_path = cand

    if ca_path and os.path.isfile(ca_path):
        os.environ.setdefault("SSL_CERT_FILE", ca_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
        os.environ.setdefault("CURL_CA_BUNDLE", ca_path)
        # 让 stdlib urllib 也走同一证书
        try:
            import ssl
            ssl.get_default_verify_paths  # 触发模块加载
            _orig_ctx = ssl.create_default_context
            def _patched_ctx(purpose=None):
                ctx = _orig_ctx(purpose) if purpose is not None else _orig_ctx()
                ctx.load_verify_locations(cafile=ca_path)
                return ctx
            ssl.create_default_context = _patched_ctx
        except Exception:
            pass


_setup_ssl_certs()


def _resolve_project_root() -> Path:
    """Frozen-aware：dev 用 __file__ 上级，frozen 用 exe 所在目录。

    macOS .app bundle 安装到 /Applications 后，exe 所在目录不可写
    （root 权限），改用 ~/Library/Application Support/AgentBuddy/ 作为
    用户数据目录（config/、.agents/ 等可写资源均落在此处）。
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            data_root = Path.home() / "Library" / "Application Support" / "AgentBuddy"
            data_root.mkdir(parents=True, exist_ok=True)
            return data_root
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _migrate_legacy_data_dir() -> None:
    """从旧品牌名 AdeBuddy 迁移用户数据到 AgentBuddy。

    品牌改名后数据目录路径变化，旧目录里的用户数据（config/、.agents/）
    需迁移到新目录，避免用户密钥等数据丢失。
    仅在新目录缺少关键用户数据时迁移，迁移后不删除旧目录（留作备份）。

    平台差异：
    - macOS: 旧 ~/Library/Application Support/AdeBuddy/ → 新 .../AgentBuddy/
    - Windows: 旧 C:\\Program Files\\AdeBuddy\\ → 新 C:\\Program Files\\AgentBuddy\\
              （也检查 Program Files (x86)）
    """
    if not getattr(sys, "frozen", False):
        return

    current = PROJECT_ROOT

    # 定位旧品牌数据目录
    legacy_candidates: list = []
    if sys.platform == "darwin":
        legacy_candidates.append(Path.home() / "Library" / "Application Support" / "AdeBuddy")
    elif sys.platform == "win32":
        # Program Files / Program Files (x86) 下的旧安装目录
        for env_var in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env_var)
            if base:
                legacy_candidates.append(Path(base) / "AdeBuddy")
        # LOCALAPPDATA 下也可能有（便携版）
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            legacy_candidates.append(Path(localappdata) / "AdeBuddy")
    else:
        # Linux: 旧 ~/.adebuddy/ 或 /opt/AdeBuddy/
        legacy_candidates.append(Path.home() / ".adebuddy")
        legacy_candidates.append(Path("/opt/AdeBuddy"))

    legacy = None
    for c in legacy_candidates:
        if c.exists() and c != current:
            legacy = c
            break
    if legacy is None:
        return

    # 新目录已有 config/keys/keys.yaml 且非空 → 已迁移过，跳过
    dst_keys = current / "config" / "keys" / "keys.yaml"
    if dst_keys.exists() and dst_keys.stat().st_size > 16:
        return

    import shutil

    def _merge_dir(src: Path, dst: Path) -> None:
        """递归合并目录：已存在的目录递归拷贝，已存在的文件不覆盖（新版优先）。"""
        if not src.exists():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            dst_item = dst / item.name
            if item.is_dir():
                _merge_dir(item, dst_item)
            else:
                if not dst_item.exists():
                    shutil.copy2(item, dst_item)

    try:
        # 迁移 config/（用户密钥、llm、mcp 等配置）
        legacy_config = legacy / "config"
        dst_config = current / "config"
        if legacy_config.exists():
            _merge_dir(legacy_config, dst_config)
            print(f"[migrate] 已从旧目录迁移 config/: {legacy_config} → {dst_config}", file=sys.stderr)
        # 迁移 .agents/（智能体数据）
        legacy_agents = legacy / ".agents"
        dst_agents = current / ".agents"
        if legacy_agents.exists():
            _merge_dir(legacy_agents, dst_agents)
            print(f"[migrate] 已从旧目录迁移 .agents/: {legacy_agents} → {dst_agents}", file=sys.stderr)
    except Exception as e:
        print(f"[migrate][WARN] 迁移旧数据失败: {e}", file=sys.stderr)


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
        print(f"\n===== AgentBuddy 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
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


def _make_writable(path: Path) -> None:
    """递归设置目录权限：目录 rwxr-xr-x，文件 rw-r--r--。

    macOS .app bundle 内的文件由 root 安装，权限为 r--r--r--（只读）。
    shutil.copy2 / copytree 会保留源权限，导致后续覆盖写入失败。
    复制后强制设为用户可写。
    """
    import os
    if path.is_dir():
        os.chmod(path, 0o755)
        for entry in path.rglob("*"):
            if entry.is_dir():
                os.chmod(entry, 0o755)
            else:
                os.chmod(entry, 0o644)
    elif path.is_file():
        os.chmod(path, 0o644)


def _remove_readonly(func, path, excinfo):
    """shutil.rmtree onerror 回调：移除只读文件后重试。

    macOS .app bundle 复制过来的文件可能只读，rmtree 删除时失败，
    先 chmod 再重试。
    """
    import os
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _bootstrap_from_bundle() -> None:
    """frozen 模式每次启动：把 bundled 资源从 _MEIPASS 同步到数据目录（PROJECT_ROOT）。

    平台差异：
    - Windows/Linux: PROJECT_ROOT == exe 所在目录（可写），用 dirs_exist_ok 合并覆盖
    - macOS: PROJECT_ROOT == ~/Library/Application Support/AgentBuddy/（可写），
      .app bundle 内源文件为 root 只读，需先删旧只读目录再拷贝，拷贝后 chmod 设可写

    程序资源（scripts/template/tools/AGENTS.md）每次启动用 bundle 新版本覆盖；
    用户数据（config/、.agents/）不在 resources 列表，天然保留不被覆盖。
    """
    if not getattr(sys, "frozen", False):
        return
    import shutil
    meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    project = PROJECT_ROOT
    is_macos = sys.platform == "darwin"

    resources = [
        "scripts", "template", "tools",
        "AGENTS.md",
    ]
    copied = []
    for name in resources:
        src = meipass / name
        if not src.exists():
            continue
        dst = project / name
        try:
            if src.is_dir():
                if is_macos:
                    # macOS: 源文件可能只读，先删后拷 + chmod
                    if dst.exists():
                        shutil.rmtree(dst, onerror=_remove_readonly)
                    shutil.copytree(src, dst)
                    _make_writable(dst)
                else:
                    # Windows/Linux: 直接合并覆盖
                    shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                if is_macos and dst.exists():
                    dst.unlink()
                shutil.copy2(src, dst)
                if is_macos:
                    _make_writable(dst)
            copied.append(name)
        except Exception as e:
            print(f"[bootstrap][WARN] 复制 {name} 失败: {e}", file=sys.stderr)

    if copied:
        print(f"[bootstrap] 已从 bundle 同步资源到数据目录: {', '.join(copied)}")
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
        import sys as _sys
        import subprocess as _sp
        import os as _os

        # macOS：用 osascript 弹原生保存对话框（不依赖 tkinter）
        if _sys.platform == "darwin":
            ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".zip"
            prompt = f"选择保存位置（{filename}）"
            # AppleScript choose file name 弹保存对话框
            script = (
                f'set theFile to choose file name with prompt "{prompt}" '
                f'default name "{filename}"'
            )
            try:
                r = _sp.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=120,
                )
            except Exception as e:
                return {"ok": False, "error": f"保存对话框失败: {e}"}

            if r.returncode != 0:
                # 用户点了取消（error -128）或其他错误
                if "-128" in (r.stderr or "") or "User canceled" in (r.stderr or ""):
                    return {"ok": False, "error": "cancelled"}
                return {"ok": False, "error": f"保存对话框失败: {r.stderr.strip()}"}

            # osascript 返回格式：alias "Macintosh HD:Users:...:file.zip"
            # 或 POSIX path：file "Macintosh HD:Users:...:file.zip"
            raw_out = (r.stdout or "").strip()
            if not raw_out:
                return {"ok": False, "error": "cancelled"}

            # 解析 AppleScript 返回的路径
            path = _osascript_to_posix(raw_out)
            if not path:
                return {"ok": False, "error": f"无法解析路径: {raw_out}"}

            try:
                raw = _b64.b64decode(data_base64)
                with open(path, "wb") as f:
                    f.write(raw)
                return {"ok": True, "path": path}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        # Windows/Linux：尝试 tkinter，回退到 Downloads 目录
        try:
            import tkinter as _tk
            from tkinter import filedialog as _fd

            root = _tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

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

            raw = _b64.b64decode(data_base64)
            with open(path, "wb") as f:
                f.write(raw)
            return {"ok": True, "path": path}
        except ImportError:
            # tkinter 不可用，回退到 Downloads 目录
            downloads = _os.path.join(_os.path.expanduser("~"), "Downloads")
            if not _os.path.isdir(downloads):
                downloads = _os.path.expanduser("~")
            path = _os.path.join(downloads, filename)
            try:
                raw = _b64.b64decode(data_base64)
                with open(path, "wb") as f:
                    f.write(raw)
                return {"ok": True, "path": path}
            except Exception as e:
                return {"ok": False, "error": str(e)}

    def open_external(self, url: str) -> dict:
        """用系统默认浏览器打开外部 URL（pywebview 下 window.open 会被忽略）。

        用于：升级弹窗的下载链接、官网链接等。浏览器会自动处理 GitHub release
        的重定向下载。
        """
        import sys as _sys
        import subprocess as _sp
        if not url or not isinstance(url, str):
            return {"ok": False, "error": "invalid url"}
        try:
            if _sys.platform == "darwin":
                _sp.Popen(["open", url])
            elif _sys.platform == "win32":
                _sp.Popen(["cmd", "/c", "start", "", url], shell=False)
            else:
                _sp.Popen(["xdg-open", url])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def _osascript_to_posix(raw: str) -> str:
    """将 osascript choose file name 的返回值转为 POSIX 路径。

    返回格式可能为：
      alias "Macintosh HD:Users:foo:bar.zip"
      file "Macintosh HD:Users:foo:bar.zip"
      POSIX file "/Users/foo/bar.zip"
    """
    import os as _os
    raw = raw.strip()

    # POSIX file "/path/to/file"
    if raw.startswith("POSIX file"):
        # 提取引号中的路径
        start = raw.find('"')
        end = raw.rfind('"')
        if start >= 0 and end > start:
            return raw[start + 1:end]

    # alias "Macintosh HD:Users:..." 或 file "Macintosh HD:Users:..."
    start = raw.find('"')
    end = raw.rfind('"')
    if start >= 0 and end > start:
        hfs_path = raw[start + 1:end]
        # HFS 路径用 : 分隔，第一段是卷名
        parts = hfs_path.split(":")
        if len(parts) >= 2:
            # Macintosh HD:Users:foo:bar.zip → /Users/foo/bar.zip
            # 去掉卷名，前面加 /
            posix = "/" + "/".join(parts[1:])
            # 验证路径是否存在其父目录
            return posix

    # 直接是 POSIX 路径
    if raw.startswith("/"):
        return raw

    return ""


def open_with_pywebview(url: str, title: str = "飞翼", width: int = 1400, height: int = 900) -> bool:
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
    parser = argparse.ArgumentParser(description="飞翼 (pywebview 桌面版)")
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

    # macOS: 从旧品牌名 AdeBuddy 迁移用户数据（密钥等）到 AgentBuddy
    _migrate_legacy_data_dir()

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
