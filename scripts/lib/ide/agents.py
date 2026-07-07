"""config/skills 本地运行目录分发器。

定位（与 AGENTS.md 一致）：
  - config/skills/ 是根据配置生成的目录，或存放 skill 的目录
  - config/skills/  → 插件安装的技能（开发环境，不提交）
  - config/skill.yaml → 已启用技能清单
  - 不再同步 rules/ 和 mcp/（这些由 agents/ 单一数据源维护）
"""
from pathlib import Path

from lib.logging import COLOR_GREEN, COLOR_RESET
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class AgentsTarget(IdeTarget):
    name = "Agents"

    def init_rules(self, source_rules: Path):
        """不同步 rules — rules 由 agents/rules/ 单一数据源维护。"""
        pass

    def init_mcp(self, source_mcp_file: Path):
        """不同步 mcp — mcp 由 agents/mcp/ 单一数据源维护。"""
        pass

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 config/skills/（插件安装的技能开发环境）。"""
        agents_skills_dir = self.root / "config" / "skills"
        copy_skills_safe(source_skills_dir, agents_skills_dir, "config/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, agents_skills_dir / "README.md",
                           "Agents", self.force, self.include_skills)

        if isinstance(source_skills_dir, list):
            srcs = [s for s in source_skills_dir if s.exists()]
        else:
            srcs = [source_skills_dir] if source_skills_dir.exists() else []
        if srcs:
            seen = set()
            skill_count = 0
            for s in srcs:
                for d in s.iterdir():
                    if d.is_dir() and d.name not in seen:
                        seen.add(d.name)
                        skill_count += 1
            print(f"{COLOR_GREEN}[OK] {skill_count} skills available in config/skills/{COLOR_RESET}")
