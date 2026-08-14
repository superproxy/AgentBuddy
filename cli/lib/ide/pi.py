"""Pi IDE 分发器。

Pi 是 earendil-works 开发的极简 agent harness（CLI 工具）。
官网：https://pi.dev/
GitHub：https://github.com/earendil-works/pi

配置目录：~/.pi/
- rules → ~/.pi/agent/（AGENTS.md 项目指令）
- mcp → ~/.pi/mcp.json
- skills → ~/.pi/skills/
- llm → ~/.pi/models.json
"""
from pathlib import Path

from ..logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from ..mcp import copy_dir_safe, copy_file_safe
from ..skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class PiTarget(IdeTarget):
    name = "Pi"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.pi/agent/（Pi 的 AGENTS.md 项目指令目录）。"""
        pi_agent_dir = Path.home() / ".pi" / "agent"
        pi_agent_dir.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, pi_agent_dir, "~/.pi/agent/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 配置到 ~/.pi/mcp.json。"""
        pi_dir = Path.home() / ".pi"
        pi_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, pi_dir / "mcp.json",
                       "~/.pi/mcp.json", self.force)

    def init_llm(self, source_rules_dir: Path):
        # Pi 的 LLM 配置通过 models.json 管理，暂不自动生成
        # 用户可通过 ~/.pi/models.json 自定义提供商和模型
        pass

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 ~/.pi/skills/。"""
        pi_skills_dir = Path.home() / ".pi" / "skills"
        copy_skills_safe(source_skills_dir, pi_skills_dir, "~/.pi/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, pi_skills_dir / "README.md",
                           "Pi", self.force, self.include_skills)
