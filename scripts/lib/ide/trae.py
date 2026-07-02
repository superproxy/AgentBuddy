"""Trae IDE 分发器（含 Trae / Trae CN / Trae Solo CN）。

迁移自 scripts/init-ide.py 的 init_trae() / init_trae_cn() / init_trae_solo_cn()。
三个变体共享相同结构，差异在全局目录名和 IDE User 目录名。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_mcp_file_safe
from lib.skills import copy_skills_safe
from .base import IdeTarget, get_ide_user_dir


class _TraeBaseTarget(IdeTarget):
    """Trae 系列基类。子类设置 _global_dirname 和 _user_dirname。"""
    _global_dirname: str = ""   # 如 ".trae" / ".trae-cn" / ".trae-solo-cn"
    _user_dirname: str = ""     # 如 "Trae" / "Trae CN" / "TRAE SOLO CN"
    _copy_mcp_to_global: bool = False  # Trae CN 需要同时复制到全局目录

    def init_rules(self, source_rules: Path):
        global_dir = Path.home() / self._global_dirname
        global_dir.mkdir(parents=True, exist_ok=True)
        rules_dir = global_dir / "rules"
        if source_rules.exists():
            copy_dir_safe(source_rules, rules_dir,
                          f"~/{self._global_dirname}/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        # MCP 配置写到 IDE User 目录
        user_mcp = get_ide_user_dir(self._user_dirname) / "mcp.json"
        copy_mcp_file_safe(source_mcp_file, user_mcp,
                           f"{self._user_dirname} User/mcp.json", self.force)

        # Trae CN 额外复制到全局目录
        if self._copy_mcp_to_global:
            global_mcp = Path.home() / self._global_dirname / "mcp.json"
            copy_mcp_file_safe(source_mcp_file, global_mcp,
                               f"~/{self._global_dirname}/mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        global_dir = Path.home() / self._global_dirname
        skills_dir = global_dir / "skills"
        copy_skills_safe(source_skills_dir, skills_dir,
                         f"~/{self._global_dirname}/skills/",
                         self.force, self.include_skills)

        if source_skills_dir.exists():
            skill_count = sum(1 for d in source_skills_dir.iterdir() if d.is_dir())
            print(f"{COLOR_GREEN}[OK] {skill_count} skills available in agents/skills/{COLOR_RESET}")


class TraeTarget(_TraeBaseTarget):
    name = "Trae"
    _global_dirname = ".trae"
    _user_dirname = "Trae"


class TraeCNTarget(_TraeBaseTarget):
    name = "TraeCN"
    _global_dirname = ".trae-cn"
    _user_dirname = "Trae CN"
    _copy_mcp_to_global = True


class TraeSoloCNTarget(_TraeBaseTarget):
    name = "TraeSoloCN"
    _global_dirname = ".trae-solo-cn"
    _user_dirname = "TRAE SOLO CN"
