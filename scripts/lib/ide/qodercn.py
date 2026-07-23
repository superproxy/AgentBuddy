"""Qoder CN（国内版）IDE 分发器。

与 QoderTarget 结构相同，差异在配置目录名（.qoder-cn）。
国际版见 qoder.py。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class QoderCNTarget(IdeTarget):
    name = "QoderCN"

    def init_rules(self, source_rules: Path):
        rules_dir = self.root / ".qoder-cn" / "rules"
        rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, rules_dir, ".qoder-cn/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        cfg_dir = self.root / ".qoder-cn"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, cfg_dir / "mcp.json", ".qoder-cn/mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        skills_dir = Path.home() / ".qoder-cn" / "skills"
        copy_skills_safe(source_skills_dir, skills_dir, "~/.qoder-cn/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, skills_dir / "README.md",
                           "Qoder CN", self.force, self.include_skills)
