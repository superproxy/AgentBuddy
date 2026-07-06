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


def _launch_cli_in_terminal(exe_path: str, args: list[str], cwd: str = "",
                            env: dict | None = None, title: str = "") -> dict:
    """在 macOS Terminal.app 中启动 TUI CLI（非阻塞，有 TTY）。

    用于 Claude/Codex/OpenCode 等 TUI 应用 —— 这些 CLI 需要 TTY 才能渲染界面，
    直接 Popen + DEVNULL 会导致进程虽启动但用户看不到界面，反复点击堆积僵尸进程。

    Returns:
        {ok: bool, pid: int, cmd: str, error: str}
    """
    if sys.platform != "darwin":
        # 非 macOS 回退到普通 Popen
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


def launch_ide(ide_key: str, cwd: str = "", session_id: str = "") -> dict:
    """启动 IDE。

    Args:
        ide_key: IDE 标识（如 "Claude"）
        cwd: 工作目录（可选）
        session_id: 要恢复的会话 ID（可选，仅 CLI 支持）

    Returns:
        {ok, pid, cmd, error, ide, exe_path, app_path, mode}
        mode: "cli" | "app" | "none"
    """
    info = detect_ide(ide_key)
    exe_path = info.get("exe_path", "")
    app_path = info.get("app_path", "")
    meta = IDE_DETECT_META.get(ide_key, {})
    is_tui = meta.get("is_tui", False)

    # 优先 CLI（支持 resume）
    if exe_path:
        args = []
        if session_id:
            # 构造 resume 命令
            resume_cmd = build_resume_command(ide_key, exe_path, session_id, cwd)
            if resume_cmd:
                # resume_cmd 是完整字符串，需拆分
                parts = resume_cmd.split()
                # 第一部分是 exe_path，其余是 args
                args = parts[1:]
        # TUI 类 CLI 需要 TTY，在 macOS 上用 Terminal.app 启动；否则直接 Popen
        if is_tui:
            result = _launch_cli_in_terminal(
                exe_path, args, cwd,
                title=f"{meta.get('label', ide_key)} — {cwd or 'Home'}",
            )
        else:
            result = _launch_cli(exe_path, args, cwd)
        result.update({"ide": ide_key, "exe_path": exe_path, "app_path": "", "mode": "cli"})
        return result

    # 回退 macOS .app
    if app_path:
        result = _launch_macos_app(app_path, cwd)
        result.update({"ide": ide_key, "exe_path": "", "app_path": app_path, "mode": "app"})
        return result

    # 都没有
    return {
        "ok": False, "pid": 0, "cmd": "", "error": f"IDE {ide_key} not installed",
        "ide": ide_key, "exe_path": "", "app_path": "", "mode": "none",
    }


def launch_ide_with_project(ide_key: str, project_path: str) -> dict:
    """启动 IDE 并打开指定项目目录。"""
    return launch_ide(ide_key, cwd=project_path)


def launch_ide_resume_session(ide_key: str, session_id: str, cwd: str = "") -> dict:
    """启动 IDE 并恢复指定会话。"""
    return launch_ide(ide_key, cwd=cwd, session_id=session_id)


__all__ = ["launch_ide", "launch_ide_with_project", "launch_ide_resume_session"]
