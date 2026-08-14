"""OpenCode IDE 分发器。

迁移自 scripts/init-ide.py 的 init_opencode()。
生成 ~/.config/opencode/opencode.json（从模板 + llm.yaml/mcp.yaml 注入模型）。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_RESET
from lib.mcp import convert_to_opencode_mcp
from lib.skills import copy_skills_safe, write_skills_index
from lib.llm import load_split_env_config
from .base import IdeTarget


class OpenCodeTarget(IdeTarget):
    name = "OpenCode"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.config/opencode/rules/。"""
        from lib.mcp import copy_dir_safe
        oc_rules_dir = Path.home() / ".config" / "opencode" / "rules"
        srcs = source_rules if isinstance(source_rules, list) else [source_rules]
        srcs = [s for s in srcs if s.exists()]
        if not srcs:
            print(f"{COLOR_YELLOW}[!] No rules source dirs found{COLOR_RESET}")
            return
        for src in srcs:
            copy_dir_safe(src, oc_rules_dir, "~/.config/opencode/rules/", self.force)

    def _sync_opencode_config(self, source_mcp_file: Path):
        """同步 opencode.json 到 ~/.config/opencode/。

        opencode.json 同时承载 MCP（mcpServers）与 LLM（provider/models）配置，
        因此 mcp 和 llm 两个 scope 都触发本方法。
        """
        # 优先从 config/ide/opencode/opencode.json 复制（由 generate 生成）
        source_dir = self.root
        generated = source_dir / "config" / "ide" / "opencode" / "opencode.json"
        opencode_template = source_dir / "template" / "ide" / "opencode" / "opencode.template.json"
        opencode_dir = Path.home() / ".config" / "opencode"
        opencode_dir.mkdir(parents=True, exist_ok=True)

        if generated.exists():
            # 从 generate 产物复制
            from lib.mcp import copy_file_safe
            copy_file_safe(generated, opencode_dir / "opencode.json",
                           "~/.config/opencode/opencode.json", self.force)
        else:
            # 回退：直接从模板生成
            env_config = load_split_env_config(source_dir, silent=True)
            convert_to_opencode_mcp(source_mcp_file, opencode_dir / "opencode.json",
                                    self.force, opencode_template, env_config,
                                    ide_protocols=self.ide_protocols)

    def init_mcp(self, source_mcp_file: Path):
        self._sync_opencode_config(source_mcp_file)

    def init_llm(self, source_rules_dir: Path):
        # OpenCode 的 LLM 配置（provider/models）在 opencode.json 中，
        # llm scope 同步时必须重新同步该文件，否则 LLM 配置不生效
        source_mcp_file = self.root / "config" / "mcp" / "mcp.json"
        self._sync_opencode_config(source_mcp_file)

    def init_skills(self, source_skills_dir: Path):
        opencode_skills_dir = Path.home() / ".config" / "opencode" / "skills"
        copy_skills_safe(source_skills_dir, opencode_skills_dir, ".opencode/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, opencode_skills_dir / "README.md",
                           "OpenCode", self.force, self.include_skills)
