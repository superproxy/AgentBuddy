"""OpenClaw IDE 分发器。

迁移自 scripts/init-ide.py 的 init_openclaw()。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class OpenClawTarget(IdeTarget):
    name = "OpenClaw"

    def init_rules(self, source_rules: Path):
        oc_rules_dir = self.root / ".openclaw" / "rules"
        oc_rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, oc_rules_dir, ".openclaw/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        oc_dir = self.root / ".openclaw"
        oc_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, oc_dir / "mcp.json", ".openclaw/mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        oc_skills_dir = self.root / ".openclaw" / "skills"
        copy_skills_safe(source_skills_dir, oc_skills_dir, ".openclaw/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, oc_skills_dir / "README.md",
                           "OpenClaw", self.force, self.include_skills)
