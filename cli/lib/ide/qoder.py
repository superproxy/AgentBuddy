"""Qoder IDE 分发器。

迁移自 scripts/init-ide.py 的 init_qoder()。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class QoderTarget(IdeTarget):
    name = "Qoder"

    def init_rules(self, source_rules: Path):
        qoder_rules_dir = self.root / ".qoder" / "rules"
        qoder_rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, qoder_rules_dir, ".qoder/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        qoder_dir = self.root / ".qoder"
        qoder_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, qoder_dir / "mcp.json", ".qoder/mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        # 同步到全局目录（~/.qoder/skills/）
        qoder_skills_dir = Path.home() / ".qoder" / "skills"
        copy_skills_safe(source_skills_dir, qoder_skills_dir, "~/.qoder/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, qoder_skills_dir / "README.md",
                           "Qoder", self.force, self.include_skills)
