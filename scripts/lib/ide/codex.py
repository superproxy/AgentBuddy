"""Codex IDE 分发器。

迁移自 scripts/init-ide.py 的 init_codex()。
MCP 配置转换为 Codex TOML 格式（.codex/config.toml），并复制 auth.json。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe, convert_to_codex_mcp
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class CodexTarget(IdeTarget):
    name = "Codex"

    def init_rules(self, source_rules: Path):
        codex_rules_dir = self.root / ".codex" / "rules"
        codex_rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, codex_rules_dir, ".codex/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        codex_dir = self.root / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)

        # Codex TOML 模板：source_dir 是项目根（source_rules.parent.parent = agents/ 的父目录）
        source_dir = self.root
        codex_template = source_dir / "ide" / "codex" / "config.toml"
        convert_to_codex_mcp(source_mcp_file, codex_dir / "config.toml",
                             self.force, codex_template)

        # 复制 auth.json
        codex_auth_src = source_dir / "ide" / "codex" / "auth.json"
        copy_file_safe(codex_auth_src, codex_dir / "auth.json",
                       ".codex/auth.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        codex_skills_dir = self.root / ".codex" / "skills"
        copy_skills_safe(source_skills_dir, codex_skills_dir, ".codex/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, codex_skills_dir / "README.md",
                           "Codex", self.force, self.include_skills)
