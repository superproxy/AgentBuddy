"""Command Code IDE 分发器。

Command Code 是面向命令行场景的 AI 编程智能体。
官网：https://commandcode.ai/
npm 包：command-code

配置目录：~/.commandcode/
- rules → ~/.commandcode/rules/
- mcp → ~/.commandcode/mcp.json
- skills → ~/.commandcode/skills/
"""
from pathlib import Path

from ..logging import COLOR_YELLOW, COLOR_RESET
from ..mcp import copy_dir_safe, copy_file_safe
from ..skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class CommandCodeTarget(IdeTarget):
    name = "CommandCode"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.commandcode/rules/。"""
        cc_rules_dir = Path.home() / ".commandcode" / "rules"
        cc_rules_dir.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, cc_rules_dir, "~/.commandcode/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 配置到 ~/.commandcode/mcp.json。"""
        cc_dir = Path.home() / ".commandcode"
        cc_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, cc_dir / "mcp.json",
                       "~/.commandcode/mcp.json", self.force)

    def init_llm(self, source_rules_dir: Path):
        # Command Code 的 LLM 配置通过项目级 .commandcode/ 目录管理，暂不自动生成
        pass

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 ~/.commandcode/skills/。"""
        cc_skills_dir = Path.home() / ".commandcode" / "skills"
        copy_skills_safe(source_skills_dir, cc_skills_dir, "~/.commandcode/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, cc_skills_dir / "README.md",
                           "Command Code", self.force, self.include_skills)
