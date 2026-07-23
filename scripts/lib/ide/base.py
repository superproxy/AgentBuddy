"""IDE 分发器基类。

各 IDE 子类继承 IdeTarget，按需覆写 init_rules / init_mcp / init_skills / init_llm。
迁移自 scripts/init-ide.py 的 12 个 init_<ide>() 函数，保持行为一致。

SCOPE 机制：通过 scope 参数控制同步范围（llm/mcp/skill/rules），替代原模块级全局变量。
"""
import sys
from pathlib import Path

from lib.logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_DARKGRAY,
    COLOR_MAGENTA, COLOR_WHITE, COLOR_RESET,
)
from lib.mcp import copy_dir_safe, copy_file_safe, copy_mcp_file_safe
from lib.skills import copy_skills_safe, write_skills_index


# 默认同步范围（plugin 的 mcp/skill 已分别并入 mcp/skill 阶段处理）
DEFAULT_SCOPE = {"llm", "mcp", "skill", "rules"}


def get_ide_user_dir(ide_name: str) -> Path:
    """获取 IDE 的 User 目录（跨平台）。

    迁移自 init-ide.py 的 _get_ide_user_dir()，供 Trae 系列分发器使用。
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / ide_name / "User"
    elif sys.platform == "win32":
        return Path.home() / "AppData" / "Roaming" / ide_name / "User"
    else:
        return Path.home() / ".config" / ide_name / "User"


class IdeTarget:
    """IDE 分发器基类。

    子类需设置类属性：
        name: IDE 名称（用于日志标识）
    并按需覆写 init_rules / init_mcp / init_skills / init_llm。

    通用流程（run 方法）：rules → mcp → llm → skills → manifest

    link_skills: True 时同步 skills 用软链接（单个 skill 级别，非整个 skills 目录）。
                 Windows 下非管理员会自动回退到 junction 或复制。
    """
    name: str = ""
    link_skills: bool = True

    def __init__(self, project_root: Path, force: bool = False,
                 include_skills=None, scope=None, link_skills=None):
        self.root = project_root
        self.force = force
        self.include_skills = include_skills
        self.scope = scope if scope is not None else set(DEFAULT_SCOPE)
        if link_skills is not None:
            self.link_skills = link_skills

    # ---------- 各阶段钩子（子类按需覆写） ----------

    def init_rules(self, source_rules: Path):
        """默认不操作；子类可指定 rules 目录并复制。"""
        pass

    def init_mcp(self, source_mcp_file: Path):
        """默认不操作；子类可指定 mcp 文件并复制/转换。"""
        pass

    def init_llm(self, source_rules_dir: Path):
        """默认不操作；子类可生成 LLM 相关配置（如 Claude settings / WorkBuddy models）。"""
        pass

    def init_skills(self, source_skills_dir: Path):
        """默认不操作；子类可指定 skills 目录并复制。"""
        pass

    def init_manifest(self, source_agents_md: Path):
        """默认不操作；子类可复制 AGENTS.md 等清单文件。"""
        pass

    # ---------- 编排入口 ----------

    def run(self, source_rules: Path, source_mcp_file: Path,
            source_skills_dir: Path, source_agents_md: Path) -> str:
        """执行完整的 IDE 同步流程。"""
        print(f"\n{COLOR_MAGENTA}--- {self.name} IDE ---{COLOR_RESET}")

        if "rules" in self.scope:
            self.init_rules(source_rules)

        if "mcp" in self.scope:
            self.init_mcp(source_mcp_file)

        if "llm" in self.scope:
            self.init_llm(source_rules)

        if "skill" in self.scope:
            self.init_skills(source_skills_dir)

        self.init_manifest(source_agents_md)
        return self.name
