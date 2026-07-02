""".agents 全局共享目录分发器。

迁移自 scripts/init-ide.py 的 init_agents()。
复制 rules / mcp / skills 到 .agents/ 目录（供多 IDE 共享）。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class AgentsTarget(IdeTarget):
    name = "Agents"

    def init_rules(self, source_rules: Path):
        agents_rules_dir = self.root / ".agents" / "rules"
        agents_rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, agents_rules_dir, ".agents/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        agents_mcp_dir = self.root / ".agents" / "mcp"
        agents_mcp_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, agents_mcp_dir / ".mcp.json",
                       ".agents/mcp/.mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        agents_skills_dir = self.root / ".agents" / "skills"
        copy_skills_safe(source_skills_dir, agents_skills_dir, ".agents/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, agents_skills_dir / "README.md",
                           "Agents", self.force, self.include_skills)

        if source_skills_dir.exists():
            skill_count = sum(1 for d in source_skills_dir.iterdir() if d.is_dir())
            print(f"{COLOR_GREEN}[OK] {skill_count} skills available in agents/skills/{COLOR_RESET}")
