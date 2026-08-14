"""IDE 分发器注册表。

通过 get_ide(name, **kw) 获取一个或所有 IDE 分发器实例。
支持 "All" 返回全部 18 个分发器。
"""
from pathlib import Path

from .base import IdeTarget, DEFAULT_SCOPE, get_ide_user_dir
from .cursor import CursorTarget
from .codex import CodexTarget
from .opencode import OpenCodeTarget
from .openworker import OpenWorkerTarget
from .trae import TraeTarget, TraeCNTarget, TraeSoloCNTarget
from .cherrystudio import CherryStudioTarget
from .claude import ClaudeTarget
from .codebuddy import CodeBuddyTarget
from .workbuddy import WorkBuddyTarget
from .qoder import QoderTarget
from .qodercn import QoderCNTarget
from .openclaw import OpenClawTarget
from .idea import IdeATarget
from .agents import AgentsTarget
from .zcode import ZCodeTarget
from .hermes import HermesTarget
from .kimi import KimiCLITarget, KimiCodeTarget, KimiWorkTarget
from .pi import PiTarget
from .commandcode import CommandCodeTarget
from .vscode import VSCodeTarget
from .deepseek import DeepSeekTarget
from .copilot import CopilotTarget
from .cline import ClineTarget


# IDE 注册表：名称 → 类（按字母顺序排列）
IDE_REGISTRY = {
    "Agents": AgentsTarget,
    "Claude": ClaudeTarget,
    "CherryStudio": CherryStudioTarget,
    "Cline": ClineTarget,
    "CodeBuddy": CodeBuddyTarget,
    "Codex": CodexTarget,
    "CommandCode": CommandCodeTarget,
    "Copilot": CopilotTarget,
    "Cursor": CursorTarget,
    "DeepSeek": DeepSeekTarget,
    "IDEA": IdeATarget,
    "KimiCLI": KimiCLITarget,
    "KimiCode": KimiCodeTarget,
    "KimiWork": KimiWorkTarget,
    "OpenClaw": OpenClawTarget,
    "OpenCode": OpenCodeTarget,
    "OpenWorker": OpenWorkerTarget,
    "Pi": PiTarget,
    "Qoder": QoderTarget,
    "QoderCN": QoderCNTarget,
    "Trae": TraeTarget,
    "TraeCN": TraeCNTarget,
    "TraeSoloCN": TraeSoloCNTarget,
    "WorkBuddy": WorkBuddyTarget,
    "ZCode": ZCodeTarget,
    "Hermes": HermesTarget,
    "VSCode": VSCodeTarget,
}


def get_ide(name: str, project_root: Path, force: bool = False,
            include_skills=None, scope=None, env_config=None) -> list:
    """获取 IDE 分发器实例列表。

    Args:
        name: IDE 名称（如 "Cursor"）或 "All" 返回全部
        project_root: 项目根目录
        force: 是否强制覆盖已存在文件
        include_skills: 技能白名单集合，None 表示全部
        scope: 同步范围集合，None 表示默认全部（llm/mcp/skill/rules）
        env_config: 保留参数（向后兼容），协议配置已移至 ide.yaml

    Returns:
        分发器实例列表
    """
    from ._meta import get_ide_protocols
    targets = []
    if name == "All":
        for cls in IDE_REGISTRY.values():
            ide_name = cls.name if hasattr(cls, 'name') else ""
            proto = get_ide_protocols(ide_name)
            targets.append(cls(project_root=project_root, force=force,
                              include_skills=include_skills, scope=scope,
                              ide_protocols=proto))
    else:
        if name not in IDE_REGISTRY:
            raise ValueError(f"Unknown IDE: {name}. Available: {', '.join(IDE_REGISTRY.keys())}")
        cls = IDE_REGISTRY[name]
        proto = get_ide_protocols(name)
        targets.append(cls(project_root=project_root, force=force,
                          include_skills=include_skills, scope=scope,
                          ide_protocols=proto))
    return targets


__all__ = [
    "IdeTarget", "DEFAULT_SCOPE", "get_ide_user_dir",
    "IDE_REGISTRY", "get_ide",
    "CursorTarget", "CodexTarget", "OpenCodeTarget",
    "TraeTarget", "TraeCNTarget", "TraeSoloCNTarget",
    "ClaudeTarget", "WorkBuddyTarget", "QoderTarget", "QoderCNTarget",
    "OpenClawTarget", "IdeATarget", "AgentsTarget", "ZCodeTarget", "PiTarget", "CommandCodeTarget",
    "VSCodeTarget", "DeepSeekTarget", "CopilotTarget", "ClineTarget",
]
