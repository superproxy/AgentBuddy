"""ZCode（智谱 ADE）IDE 分发器。

生成 ~/.zcode/zcode.json（从模板 + llm.yaml/mcp.yaml 注入模型）与 ~/.zcode/skills/。
MCP 配置文件结构与 opencode 类似（单 JSON 含 models + mcp）。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_RESET
from lib.mcp import copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class ZCodeTarget(IdeTarget):
    name = "ZCode"

    def init_rules(self, source_rules: Path):
        # ZCode 暂无 rules 目录配置（与 OpenCode 一致）
        pass

    def init_mcp(self, source_mcp_file: Path):
        # 优先从 .agents/ide/zcode/zcode.json 复制（由 generate 生成）
        source_dir = self.root
        generated = source_dir / ".agents" / "ide" / "zcode" / "zcode.json"
        zcode_dir = Path.home() / ".zcode"
        zcode_dir.mkdir(parents=True, exist_ok=True)

        if generated.exists():
            copy_file_safe(generated, zcode_dir / "zcode.json",
                           "~/.zcode/zcode.json", self.force)
        else:
            # 回退：直接复制 mcp.yaml 为 mcp.json（最小可用）
            copy_file_safe(source_mcp_file, zcode_dir / "mcp.json",
                           "~/.zcode/mcp.json", self.force)

    def init_llm(self, source_rules_dir: Path):
        # ZCode 的 LLM 配置已在 init_mcp 中合并生成（zcode.json 含 models）
        pass

    def init_skills(self, source_skills_dir: Path):
        zcode_skills_dir = Path.home() / ".zcode" / "skills"
        copy_skills_safe(source_skills_dir, zcode_skills_dir, "~/.zcode/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, zcode_skills_dir / "README.md",
                           "ZCode", self.force, self.include_skills)
