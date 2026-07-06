"""IDE 分发器注册表。

通过 get_ide(name, **kw) 获取一个或所有 IDE 分发器实例。
支持 "All" 返回全部 12 个分发器。
"""
from pathlib import Path

from .base import IdeTarget, DEFAULT_SCOPE, get_ide_user_dir
from .cursor import CursorTarget
from .codex import CodexTarget
from .opencode import OpenCodeTarget
from .trae import TraeTarget, TraeCNTarget, TraeSoloCNTarget
from .claude import ClaudeTarget
from .workbuddy import WorkBuddyTarget
from .qoder import QoderTarget
from .qodercn import QoderCNTarget
from .openclaw import OpenClawTarget
from .idea import IdeATarget
from .agents import AgentsTarget
from .zcode import ZCodeTarget


# IDE 注册表：名称 → 类（按字母顺序排列）
IDE_REGISTRY = {
    "Agents": AgentsTarget,
    "Claude": ClaudeTarget,
    "Codex": CodexTarget,
    "Cursor": CursorTarget,
    "IDEA": IdeATarget,
    "OpenClaw": OpenClawTarget,
    "OpenCode": OpenCodeTarget,
    "Qoder": QoderTarget,
    "QoderCN": QoderCNTarget,
    "Trae": TraeTarget,
    "TraeCN": TraeCNTarget,
    "TraeSoloCN": TraeSoloCNTarget,
    "WorkBuddy": WorkBuddyTarget,
    "ZCode": ZCodeTarget,
}


def get_ide(name: str, project_root: Path, force: bool = False,
            include_skills=None, scope=None) -> list:
    """获取 IDE 分发器实例列表。

    Args:
        name: IDE 名称（如 "Cursor"）或 "All" 返回全部
        project_root: 项目根目录
        force: 是否强制覆盖已存在文件
        include_skills: 技能白名单集合，None 表示全部
        scope: 同步范围集合，None 表示默认全部（llm/mcp/skill/rules）

    Returns:
        分发器实例列表
    """
    kw = dict(project_root=project_root, force=force,
              include_skills=include_skills, scope=scope)
    if name == "All":
        return [cls(**kw) for cls in IDE_REGISTRY.values()]
    if name not in IDE_REGISTRY:
        raise ValueError(f"Unknown IDE: {name}. Available: {', '.join(IDE_REGISTRY.keys())}")
    return [IDE_REGISTRY[name](**kw)]


__all__ = [
    "IdeTarget", "DEFAULT_SCOPE", "get_ide_user_dir",
    "IDE_REGISTRY", "get_ide",
    "CursorTarget", "CodexTarget", "OpenCodeTarget",
    "TraeTarget", "TraeCNTarget", "TraeSoloCNTarget",
    "ClaudeTarget", "WorkBuddyTarget", "QoderTarget", "QoderCNTarget",
    "OpenClawTarget", "IdeATarget", "AgentsTarget", "ZCodeTarget",
]
