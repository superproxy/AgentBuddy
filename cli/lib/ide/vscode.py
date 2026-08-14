"""VSCode 分发器。

Visual Studio Code（Microsoft 代码编辑器）。
官网：https://code.visualstudio.com/

配置目录：~/.vscode/
- rules → ~/.vscode/AGENTS.md（项目指令）
- mcp → ~/.vscode/mcp.json
- skills → ~/.vscode/skills/
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class VSCodeTarget(IdeTarget):
    name = "VSCode"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.vscode/AGENTS.md。"""
        vscode_dir = Path.home() / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, vscode_dir, "~/.vscode/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 配置到 ~/.vscode/mcp.json。"""
        vscode_dir = Path.home() / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, vscode_dir / "mcp.json",
                       "~/.vscode/mcp.json", self.force)

    def init_llm(self, source_rules_dir: Path):
        # VSCode 的 LLM 配置通过扩展管理，暂不自动生成
        pass

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 ~/.vscode/skills/。"""
        vscode_skills_dir = Path.home() / ".vscode" / "skills"
        copy_skills_safe(source_skills_dir, vscode_skills_dir, "~/.vscode/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, vscode_skills_dir / "README.md",
                           "VSCode", self.force, self.include_skills)
