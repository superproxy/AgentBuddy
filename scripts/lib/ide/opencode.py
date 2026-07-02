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
        # OpenCode 无 rules 目录配置（原 init_opencode 也未处理 rules）
        pass

    def init_mcp(self, source_mcp_file: Path):
        # 优先从 .agents/ide/opencode/opencode.json 复制（由 generate 生成）
        source_dir = self.root
        generated = source_dir / ".agents" / "ide" / "opencode" / "opencode.json"
        opencode_template = source_dir / "ide" / "opencode" / "opencode.template.json"
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
                                    self.force, opencode_template, env_config)

    def init_llm(self, source_rules_dir: Path):
        # OpenCode 的 LLM 配置已在 init_mcp 中合并生成（opencode.json 含 models）
        pass

    def init_skills(self, source_skills_dir: Path):
        opencode_skills_dir = Path.home() / ".config" / "opencode" / "skills"
        copy_skills_safe(source_skills_dir, opencode_skills_dir, ".opencode/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, opencode_skills_dir / "README.md",
                           "OpenCode", self.force, self.include_skills)
