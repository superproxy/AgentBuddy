"""路径与目录链接工具。junction→symlink→copy 降级链。

本环境沙箱默认使用 copy 模式，避免 symlink 权限问题。
"""
import os
import shutil
import sys
from pathlib import Path


def _resolve_project_root() -> Path:
    """Frozen-aware 项目根定位。

    macOS .app bundle 安装到 /Applications 后不可写，
    改用 ~/Library/Application Support/AgentBuddy/。
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            data_root = Path.home() / "Library" / "Application Support" / "AgentBuddy"
            data_root.mkdir(parents=True, exist_ok=True)
            return data_root
        return Path(sys.executable).parent
    # scripts/lib/paths.py → scripts/lib/ → scripts/ → 项目根
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _resolve_project_root()


def make_dir_link(src: Path, dst: Path, prefer_copy: bool = True) -> str:
    """创建目录链接，降级链：symlink→copy（macOS 无 junction）。

    返回使用的方式："symlink" 或 "copy"。
    """
    src = Path(src)
    dst = Path(dst)

    # 清理已存在的目标
    if dst.is_symlink() or dst.exists():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()

    dst.parent.mkdir(parents=True, exist_ok=True)

    if prefer_copy:
        shutil.copytree(src, dst)
        return "copy"

    try:
        os.symlink(src, dst)
        return "symlink"
    except (OSError, NotImplementedError):
        shutil.copytree(src, dst)
        return "copy"
