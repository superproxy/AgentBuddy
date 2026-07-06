"""IDE 检测模块。

通过 shutil.which + 已知安装路径，探测本机已安装的 AI 编程 IDE。
返回每个 IDE 的 key/label/installed/exe_path/version/config_paths/sessions_dir。

支持检测的 IDE（与 IDE_REGISTRY 对齐）：
- Claude Code（claude CLI）
- Codex（codex CLI）
- Cursor（cursor 命令 + macOS .app）
- Trae / Trae CN / Trae Work CN（macOS .app + CLI）
- OpenCode（opencode CLI）
- Qoder（macOS .app + CLI）
- OpenClaw（openclaw CLI）
- WorkBuddy（workbuddy CLI）
- ZCode（智谱 ADE，zcode CLI + macOS .app）
- IDEA（idea 命令 + Toolbox）
- Agents（通用，无独立 CLI，按配置目录存在判断）
- Kimi Code（kimi CLI，非 IDE_REGISTRY 成员但作为扩展检测）
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ===== IDE 元数据注册表 =====
# 每个 IDE 定义：cli_names（CLI 命令名列表，按优先级）、macos_apps（macOS .app 路径列表）、
#                config_dirs（配置目录列表，相对 Path.home()）、sessions_subdir（会话子目录名）、
#                is_tui（CLI 是否为交互式 TUI 应用，需 TTY 才能显示界面）
IDE_DETECT_META = {
    "Claude": {
        "label": "Claude Code",
        "cli_names": ["claude"],
        "macos_apps": [],
        "config_dirs": [".claude"],
        "sessions_subdir": "projects",  # Claude 会话按项目哈希存于 projects/
        "is_tui": True,
    },
    "Codex": {
        "label": "Codex",
        "cli_names": ["codex"],
        "macos_apps": [],
        "config_dirs": [".codex"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "Cursor": {
        "label": "Cursor",
        "cli_names": ["cursor"],
        "macos_apps": [
            "/Applications/Cursor.app",
        ],
        "config_dirs": [".cursor"],
        "sessions_subdir": "projects",
        "is_tui": False,
    },
    "Trae": {
        "label": "Trae",
        "cli_names": ["trae"],
        "macos_apps": ["/Applications/Trae.app"],
        "config_dirs": [".trae"],
        "sessions_subdir": "sessions",
        "is_tui": False,
    },
    "TraeCN": {
        "label": "Trae CN",
        "cli_names": ["trae-cn"],
        "macos_apps": ["/Applications/Trae CN.app"],
        "config_dirs": [".trae-cn", ".traecn"],
        "sessions_subdir": "sessions",
        "is_tui": False,
    },
    "TraeSoloCN": {
        "label": "Trae Work CN",
        "cli_names": ["trae-solo-cn"],
        "macos_apps": ["/Applications/Trae Solo CN.app"],
        "config_dirs": [".trae-solo-cn", ".traesolocn"],
        "sessions_subdir": "sessions",
        "is_tui": False,
    },
    "OpenCode": {
        "label": "OpenCode",
        "cli_names": ["opencode"],
        "macos_apps": [],
        "config_dirs": [".config/opencode"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "Qoder": {
        "label": "Qoder",
        "cli_names": ["qoder"],
        "macos_apps": ["/Applications/Qoder.app"],
        "config_dirs": [".qoder"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "QoderCN": {
        "label": "Qoder CN",
        "cli_names": ["qoder-cn"],
        "macos_apps": ["/Applications/Qoder CN.app", "/Applications/Qoder中国版.app"],
        "config_dirs": [".qoder-cn", ".qodercn"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "OpenClaw": {
        "label": "OpenClaw",
        "cli_names": ["openclaw"],
        "macos_apps": [],
        "config_dirs": [".openclaw"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "WorkBuddy": {
        "label": "WorkBuddy",
        "cli_names": ["workbuddy"],
        "macos_apps": [],
        "config_dirs": [".workbuddy"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    "IDEA": {
        "label": "IDEA",
        "cli_names": ["idea"],
        "macos_apps": [
            "/Applications/IntelliJ IDEA.app",
            "/Applications/IntelliJ IDEA CE.app",
        ],
        "config_dirs": [".idea", ".jetbrains"],
        "sessions_subdir": None,  # IDEA 无 CLI 会话概念
        "is_tui": False,
    },
    "Agents": {
        "label": "Agents",
        "cli_names": [],
        "macos_apps": [],
        "config_dirs": [".agents"],
        "sessions_subdir": None,
        "is_tui": False,
    },
    # 扩展：Kimi Code（非 IDE_REGISTRY 成员，作为 CLI 伙伴工具检测）
    "KimiCode": {
        "label": "Kimi Code",
        "cli_names": ["kimi", "kimi-code"],
        "macos_apps": [],
        "config_dirs": [".kimi-code"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
    # 智谱 ZCode ADE（Agent Development Environment）
    "ZCode": {
        "label": "ZCode",
        "cli_names": ["zcode"],
        "macos_apps": ["/Applications/ZCode.app"],
        "config_dirs": [".zcode"],
        "sessions_subdir": "sessions",
        "is_tui": True,
    },
}


def _which(cli_name: str) -> str | None:
    """shutil.which 封装，返回绝对路径或 None。"""
    return shutil.which(cli_name)


def _check_macos_app(app_path: str) -> bool:
    """检查 macOS .app 是否存在。"""
    return sys.platform == "darwin" and Path(app_path).exists()


def _get_cli_version(exe_path: str) -> str:
    """尝试获取 CLI 版本（--version），失败返回空字符串。"""
    if not exe_path:
        return ""
    # 只试 --version（绝大多数 CLI 支持），失败快速返回，避免逐个 flag 串行拖慢
    try:
        r = subprocess.run(
            [exe_path, "--version"],
            capture_output=True, text=True, timeout=2,
        )
        out = (r.stdout + r.stderr).strip()
        if out:
            return out.split("\n", 1)[0][:80]
    except Exception:
        pass
    return ""


def _resolve_config_paths(config_dirs: list[str]) -> list[str]:
    """将相对 Path.home() 的配置目录解析为绝对路径，返回存在的路径列表。"""
    home = Path.home()
    found = []
    for d in config_dirs:
        abs_path = home / d if not d.startswith("/") else Path(d)
        if abs_path.exists():
            found.append(str(abs_path))
    return found


def _resolve_sessions_dir(ide_key: str, config_paths: list[str]) -> str:
    """根据 sessions_subdir 推测会话目录绝对路径。"""
    meta = IDE_DETECT_META.get(ide_key, {})
    subdir = meta.get("sessions_subdir")
    if not subdir or not config_paths:
        return ""
    # 取第一个存在的 config_path/subdir
    for cp in config_paths:
        candidate = Path(cp) / subdir
        if candidate.exists():
            return str(candidate)
    return ""


def detect_ide(ide_key: str) -> dict:
    """检测单个 IDE。

    Returns:
        {
            "key": str,
            "label": str,
            "installed": bool,
            "exe_path": str,        # CLI 可执行文件路径（可能为空）
            "app_path": str,        # macOS .app 路径（可能为空）
            "version": str,
            "config_paths": list[str],
            "sessions_dir": str,
        }
    """
    meta = IDE_DETECT_META.get(ide_key)
    if not meta:
        return {
            "key": ide_key, "label": ide_key, "installed": False,
            "exe_path": "", "app_path": "", "version": "",
            "config_paths": [], "sessions_dir": "",
        }

    exe_path = ""
    version = ""
    for cli_name in meta["cli_names"]:
        p = _which(cli_name)
        if p:
            exe_path = p
            version = _get_cli_version(p)
            break

    app_path = ""
    for ap in meta["macos_apps"]:
        if _check_macos_app(ap):
            app_path = ap
            break

    config_paths = _resolve_config_paths(meta["config_dirs"])
    sessions_dir = _resolve_sessions_dir(ide_key, config_paths)

    installed = bool(exe_path or app_path or config_paths)

    return {
        "key": ide_key,
        "label": meta["label"],
        "installed": installed,
        "exe_path": exe_path,
        "app_path": app_path,
        "version": version,
        "config_paths": config_paths,
        "sessions_dir": sessions_dir,
    }


def detect_all() -> list[dict]:
    """检测所有支持的 IDE，返回列表（并行加速，按 key 字母升序）。"""
    from concurrent.futures import ThreadPoolExecutor
    keys = sorted(IDE_DETECT_META.keys())
    with ThreadPoolExecutor(max_workers=min(len(keys), 8)) as ex:
        results = list(ex.map(detect_ide, keys))
    return results


def is_installed(ide_key: str) -> bool:
    """快速判断 IDE 是否安装。"""
    return detect_ide(ide_key)["installed"]


__all__ = ["IDE_DETECT_META", "detect_ide", "detect_all", "is_installed"]
