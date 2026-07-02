"""Cursor IDE 分发器。

迁移自 scripts/init-ide.py 的 init_cursor()。
MCP 配置转换为 Cursor 格式（提取 mcpServers 到 .cursor/mcp.json）。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.mcp import copy_dir_safe, convert_to_cursor_mcp
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class CursorTarget(IdeTarget):
    name = "Cursor"

    def init_rules(self, source_rules: Path):
        cursor_dir = self.root / ".cursor" / "rules"
        cursor_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, cursor_dir, ".cursor/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        cursor_dir = self.root / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        convert_to_cursor_mcp(source_mcp_file, cursor_dir / "mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        cursor_skills_dir = self.root / ".cursor" / "skills"
        copy_skills_safe(source_skills_dir, cursor_skills_dir, ".cursor/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, cursor_skills_dir / "README.md",
                           "Cursor", self.force, self.include_skills)
