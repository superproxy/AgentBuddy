"""Codex IDE 分发器。

迁移自 scripts/init-ide.py 的 init_codex()。
MCP 配置转换为 Codex TOML 格式（.codex/config.toml），并复制 auth.json。
"""
from pathlib import Path

from ..logging import COLOR_YELLOW, COLOR_RESET
from ..mcp import copy_dir_safe, copy_file_safe, convert_to_codex_mcp
from ..skills import copy_skills_safe, write_skills_index
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
        """同步 MCP 配置到 .codex/config.toml 和 ~/.codex/config.toml。

        config.toml 同时包含 LLM 配置（model_provider / model_providers），
        所以 MCP 和 LLM 同步都需要调用 convert_to_codex_mcp。
        """
        self._sync_codex_config(source_mcp_file)

    def init_llm(self, source_rules_dirs):
        """同步 LLM 配置（config.toml + auth.json）。

        scope=llm 时也需同步 config.toml（含 model_provider）和 auth.json。
        """
        source_mcp_file = self.root / "config" / "mcp" / "mcp.json"
        if source_mcp_file.exists():
            self._sync_codex_config(source_mcp_file)
        self._sync_codex_auth()

    def _sync_codex_config(self, source_mcp_file: Path):
        """生成 Codex config.toml（合并 LLM 配置 + MCP 配置）。"""
        codex_dir = self.root / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)

        source_dir = self.root
        codex_template = source_dir / "config" / "ide" / "codex" / "config.toml"

        # 项目级 .codex/config.toml
        convert_to_codex_mcp(source_mcp_file, codex_dir / "config.toml",
                             self.force, codex_template)

        # 全局 ~/.codex/config.toml
        global_codex_dir = Path.home() / ".codex"
        global_codex_dir.mkdir(parents=True, exist_ok=True)
        convert_to_codex_mcp(source_mcp_file, global_codex_dir / "config.toml",
                             self.force, codex_template)

    def _sync_codex_auth(self):
        """复制 auth.json 到项目级和全局。"""
        source_dir = self.root
        codex_auth_src = source_dir / "config" / "ide" / "codex" / "auth.json"
        codex_dir = self.root / ".codex"
        global_codex_dir = Path.home() / ".codex"
        copy_file_safe(codex_auth_src, codex_dir / "auth.json",
                       ".codex/auth.json", self.force)
        copy_file_safe(codex_auth_src, global_codex_dir / "auth.json",
                       "~/.codex/auth.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        # 同步到全局目录（~/.codex/skills/）
        codex_skills_dir = Path.home() / ".codex" / "skills"
        copy_skills_safe(source_skills_dir, codex_skills_dir, "~/.codex/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, codex_skills_dir / "README.md",
                           "Codex", self.force, self.include_skills)
