"""IDE 启动模块。

封装各 IDE 的启动逻辑，支持：
- 直接启动 IDE（打开新窗口或最近项目）
- 启动 IDE 并指定工作目录
- 启动 IDE 并恢复指定会话（如 claude --resume <id>）

启动策略：
1. 优先用 CLI 可执行文件（exe_path）启动，支持 resume 参数
2. macOS 无 CLI 时用 `open -a <App.app>` 启动 GUI
3. 启动为非阻塞子进程（Popen），不等待退出
"""
import os
import subprocess
import sys
from pathlib import Path

from .detect import detect_ide, IDE_DETECT_META
from .session import build_resume_command


# macOS .app 启动命令模板（{app} 为 .app 路径，{cwd} 为工作目录）
MACOS_OPEN_TEMPLATE = "open -a \"{app}\""
MACOS_OPEN_CWD_TEMPLATE = "open -a \"{app}\" \"{cwd}\""


def _launch_cli(exe_path: str, args: list[str], cwd: str = "", env: dict | None = None) -> dict:
    """启动 CLI 子进程（非阻塞）。

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
