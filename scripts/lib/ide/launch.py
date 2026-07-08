"""IDE 启动模块。

封装各 IDE 的启动逻辑，支持：
- 直接启动 IDE（打开新窗口或最近项目）
- 启动 IDE 并指定工作目录
- 启动 IDE 并恢复指定会话（如 claude --resume <id>）

启动策略：
1. 优先用 CLI 可执行文件（exe_path）启动，支持 resume 参数
   - TUI 类 CLI（Claude/Codex/OpenCode 等）在 macOS 上通过 Terminal.app 启动，确保有 TTY
   - 非 TUI CLI 直接 Popen 启动
2. macOS 无 CLI 时用 `open -a <App.app>` 启动 GUI
3. 启动为非阻塞子进程（Popen），不等待退出
"""
import os
import shlex
import subprocess
import sys
from pathlib import Path

from .detect import detect_ide, IDE_DETECT_META
from .session import build_resume_command


# macOS .app 启动命令模板（{app} 为 .app 路径，{cwd} 为工作目录）
MACOS_OPEN_TEMPLATE = "open -a \"{app}\""
MACOS_OPEN_CWD_TEMPLATE = "open -a \"{app}\" \"{cwd}\""


def _launch_cli(exe_path: str, args: list[str], cwd: str = "", env: dict | None = None) -> dict:
    """启动 CLI 子进程（非阻塞，无 TTY，适用于非交互式 CLI）。

    Returns:
        {ok: bool, pid: int, cmd: str, error: str}
    """
    if not exe_path:
        return {"ok": False, "pid": 0, "cmd": "", "error": "exe_path is empty"}
    cmd = [exe_path] + args
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd or None,
            env={**os.environ, **(env or {})},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # 脱离父进程会话，避免父退出时被杀
        )
        return {"ok": True, "pid": proc.pid, "cmd": " ".join(cmd), "error": ""}
    except Exception as e:
        return {"ok": False, "pid": 0, "cmd": " ".join(cmd), "error": str(e)}


def _launch_cli_in_new_console_win32(exe_path: str, args: list[str], cwd: str = "",
                                     env: dict | None = None, title: str = "") -> dict:
    """在新的 Windows 控制台窗口中启动 TUI CLI（非阻塞，有 TTY）。

    用 CREATE_NEW_CONSOLE 标志让 Popen 开新 cmd 窗口；Windows 11 默认终端为
    Windows Terminal，会自动接管新控制台。窗口关闭即终止子进程。

    Args:
        title: 窗口标题（Windows 控制台标题，会被 cmd /K TITLE 设置）

    Returns:
        {ok: bool, pid: int, cmd: str, error: str}
    """
    if not exe_path:
        return {"ok": False, "pid": 0, "cmd": "", "error": "exe_path is empty"}

    # 构造在窗口内执行的 shell 命令：cd /d <cwd> && <exe> <args>
    # 路径含空格用双引号包裹；args 之间空格分隔（build_resume_command 已拆好）
    quote = lambda s: f'"{s}"' if " " in s and not s.startswith('"') else s
    inner_parts = [quote(exe_path)] + [quote(a) for a in args]
    inner_cmd = " ".join(inner_parts)
    if cwd:
        inner_cmd = f'cd /d "{cwd}" && {inner_cmd}'

    # 用 cmd /K 让窗口保持打开（关窗即退进程）；TITLE 设置窗口标题
    safe_title = (title or "TUI CLI").replace('"', '')
    full_cmd = f'TITLE {safe_title} && {inner_cmd}'
    cmd = ["cmd.exe", "/K", full_cmd]

    try:
        # CREATE_NEW_CONSOLE = 0x00000010：新建控制台窗口（有 TTY）
        # 不用 start_new_session，否则关窗不会终止子进程
        proc = subprocess.Popen(
            cmd,
            cwd=cwd or None,
            env={**os.environ, **(env or {})},
            creationflags=0x00000010,
        )
        return {
            "ok": True, "pid": proc.pid,
            "cmd": f"{exe_path} {' '.join(args)}".strip(),
            "error": "", "_new_console": True,
        }
    except Exception as e:
        return {"ok": False, "pid": 0, "cmd": " ".join(cmd), "error": str(e)}


def _launch_cli_in_terminal(exe_path: str, args: list[str], cwd: str = "",
                            env: dict | None = None, title: str = "") -> dict:
    """在终端窗口中启动 TUI CLI（非阻塞，有 TTY）。

    用于 Claude/Codex/OpenCode 等 TUI 应用 —— 这些 CLI 需要 TTY 才能渲染界面，
    直接 Popen + DEVNULL 会导致进程虽启动但用户看不到界面，反复点击堆积僵尸进程。

    - macOS：用 Terminal.app（osascript do script）打开新窗口
    - Windows：用 CREATE_NEW_CONSOLE 新建 cmd 窗口（Windows 11 默认即 Windows Terminal）
    - 其他平台：回退到普通 Popen

    Returns:
        {ok: bool, pid: int, cmd: str, error: str}
    """
    if sys.platform == "win32":
        return _launch_cli_in_new_console_win32(exe_path, args, cwd, env, title)
    if sys.platform != "darwin":
        # 非 macOS/Linux 回退到普通 Popen
        return _launch_cli(exe_path, args, cwd, env)
    if not exe_path:
        return {"ok": False, "pid": 0, "cmd": "", "error": "exe_path is empty"}

    # 构造 shell 命令：cd <cwd> && <exe> <args>
    parts = [shlex.quote(exe_path)] + [shlex.quote(a) for a in args]
    shell_cmd = " ".join(parts)
    if cwd:
        shell_cmd = f"cd {shlex.quote(cwd)} && {shell_cmd}"
    # env 注入（仅非空键）
    if env:
        for k, v in env.items():
            if v is not None and v != os.environ.get(k):
                shell_cmd = f"export {k}={shlex.quote(str(v))} && {shell_cmd}"

    # 用 osascript 让 Terminal.app 打开新窗口执行命令
    # 采用单行 tell...to do script 形式（osascript 立即返回 tab id，不阻塞）
    # 不设置 custom title（多行 tell 块会阻塞 osascript 进程直到 TUI 退出）
    cmd_escaped = shell_cmd.replace("\\", "\\\\").replace('"', '\\"')
    apple_script = f'tell application "Terminal" to do script "{cmd_escaped}"'
    full_cmd = ["osascript", "-e", apple_script]
    try:
        proc = subprocess.Popen(
            full_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # 给 osascript 一点时间触发 Terminal 开窗口（osascript 本身会很快退出）
        # 注意：proc.pid 是 osascript 的 pid，不是 TUI 进程的 pid
        # TUI 进程在 Terminal.app 内运行，由 Terminal 持有
        return {
            "ok": True, "pid": proc.pid, "cmd": shell_cmd, "error": "",
            "_terminal": True,
        }
    except Exception as e:
        return {"ok": False, "pid": 0, "cmd": " ".join(full_cmd), "error": str(e)}


def _launch_macos_app(app_path: str, cwd: str = "") -> dict:
    """启动 macOS .app（非阻塞）。

    Returns:
        {ok: bool, pid: int, cmd: str, error: str}
    """
    if sys.platform != "darwin":
        return {"ok": False, "pid": 0, "cmd": "", "error": "not macOS"}
    if not Path(app_path).exists():
        return {"ok": False, "pid": 0, "cmd": "", "error": f"app not found: {app_path}"}
    # open 命令本身是非阻塞的
    args = ["-a", app_path]
    if cwd:
        args.append(cwd)
    cmd = ["open"] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"ok": True, "pid": proc.pid, "cmd": " ".join(f'"{c}"' if " " in c else c for c in cmd), "error": ""}
    except Exception as e:
        return {"ok": False, "pid": 0, "cmd": " ".join(cmd), "error": str(e)}


def launch_ide(ide_key: str, cwd: str = "", session_id: str = "", mode: str = "") -> dict:
    """启动 IDE。

    Args:
        ide_key: IDE 标识（如 "Claude"）
        cwd: 工作目录（可选）
        session_id: 要恢复的会话 ID（可选，仅 CLI 支持）
        mode: 启动模式 - "cli" 仅启动 CLI，"app" 仅启动 App，"" 自动（先 CLI 后 App）

    Returns:
        {ok, pid, cmd, error, ide, exe_path, app_path, mode}
        mode: "cli" | "app" | "none"
    """
    info = detect_ide(ide_key)
    exe_path = info.get("exe_path", "")
    app_path = info.get("app_path", "")
    meta = IDE_DETECT_META.get(ide_key, {})
    # is_tui 优先用 detect 返回的 per-cli 判定（同一 IDE 可能混合 TUI/非TUI CLI，
    # 如 Trae 命中 trae-cli 时为 TUI，命中 trae 时为非 TUI），回退 meta 默认值
    is_tui = info.get("is_tui", meta.get("is_tui", False))

    def _try_cli():
        if not exe_path:
            return None
        args = []
        if session_id:
            resume_cmd = build_resume_command(ide_key, exe_path, session_id, cwd)
            if resume_cmd:
                parts = resume_cmd.split()
                args = parts[1:]
        if is_tui:
            result = _launch_cli_in_terminal(
                exe_path, args, cwd,
                title=f"{meta.get('label', ide_key)} - {cwd or 'Home'}",
            )
        else:
            result = _launch_cli(exe_path, args, cwd)
        result.update({"ide": ide_key, "exe_path": exe_path, "app_path": "", "mode": "cli"})
        return result

    def _try_app():
        if not app_path:
            return None
        result = _launch_macos_app(app_path, cwd)
        result.update({"ide": ide_key, "exe_path": "", "app_path": app_path, "mode": "app"})
        return result

    # 按指定 mode 启动
    if mode == "cli":
        result = _try_cli()
        if result:
            return result
        return {
            "ok": False, "pid": 0, "cmd": "",
            "error": f"IDE {ide_key} CLI 未安装",
            "ide": ide_key, "exe_path": "", "app_path": "", "mode": "none",
        }
    if mode == "app":
        result = _try_app()
        if result:
            return result
        return {
            "ok": False, "pid": 0, "cmd": "",
            "error": f"IDE {ide_key} App 未安装",
            "ide": ide_key, "exe_path": "", "app_path": "", "mode": "none",
        }

    # 自动模式：优先 CLI（支持 resume），回退 App
    result = _try_cli()
    if result:
        return result
    result = _try_app()
    if result:
        return result

    # 都没有
    return {
        "ok": False, "pid": 0, "cmd": "", "error": f"IDE {ide_key} not installed",
        "ide": ide_key, "exe_path": "", "app_path": "", "mode": "none",
    }


def launch_ide_with_project(ide_key: str, project_path: str) -> dict:
    """启动 IDE 并打开指定项目目录。"""
    return launch_ide(ide_key, cwd=project_path)


def launch_ide_resume_session(ide_key: str, session_id: str, cwd: str = "", mode: str = "") -> dict:
    """启动 IDE 并恢复指定会话。"""
    return launch_ide(ide_key, cwd=cwd, session_id=session_id, mode=mode)


__all__ = ["launch_ide", "launch_ide_with_project", "launch_ide_resume_session"]
