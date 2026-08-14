"""Hermes Agent IDE 分发器。

配置目录 .ade-hermes，CLI 命令 hermes。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class HermesTarget(IdeTarget):
    name = "Hermes"

    def init_rules(self, source_rules: Path):
        rules_dir = self.root / ".ade-hermes" / "rules"
        rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, rules_dir, ".ade-hermes/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        hermes_dir = self.root / ".ade-hermes"
        hermes_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, hermes_dir / "mcp.json", ".ade-hermes/mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        skills_dir = Path.home() / ".ade-hermes" / "skills"
        copy_skills_safe(source_skills_dir, skills_dir, "~/.ade-hermes/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, skills_dir / "README.md",
                           "Hermes", self.force, self.include_skills)
