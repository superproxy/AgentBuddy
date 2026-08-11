"""OpenWorker 分发器。

OpenWorker（吴恩达 Andrew Ng 开源桌面 AI 智能体，仅桌面 App）：
- App：OpenWork.app（bundle id com.differentai.openwork）
- 配置目录：~/.openworker/（macOS/Linux），%USERPROFILE%\\.openworker\（Windows）
- 模型/MCP 主要通过 GUI 配置；本分发器同步 skills 与 mcp 到 ~/.openworker/，
  供 OpenWorker 读取（SKILL.md 目录格式与 AgentBuddy 兼容）。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RED, COLOR_RESET
from lib.mcp import copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class OpenWorkerTarget(IdeTarget):
    name = "OpenWorker"

    def init_rules(self, source_rules: Path):
        # OpenWorker 无 rules 概念，跳过
        pass

    def init_mcp(self, source_mcp_file: Path):
        ow_dir = Path.home() / ".openworker"
        ow_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, ow_dir / "mcp.json",
                       "~/.openworker/mcp.json", self.force)

    def init_llm(self, source_rules_dirs):
        # OpenWorker 模型由 GUI 配置，跳过
        pass

    def init_skills(self, source_skills_dir: Path):
        ow_skills_dir = Path.home() / ".openworker" / "skills"
        copy_skills_safe(source_skills_dir, ow_skills_dir, "~/.openworker/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, ow_skills_dir / "README.md",
                           "OpenWorker", self.force, self.include_skills)
        print(f"{COLOR_GREEN}[OK] OpenWorker skills synced to ~/.openworker/skills/{COLOR_RESET}")
