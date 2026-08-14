"""Cline IDE 分发器。

Cline 是开源 AI 编程代理（Apache 2.0），多形态部署：
- CLI: npm i -g cline（命令 cline）
- VS Code 扩展: saoudrizwan.claude-dev
- JetBrains 插件: 27189 (xmlId: com.cline)
- ACP 模式: 通过 cline acp 启动（参考 docs.cline.bot/usage/acp）

同步策略（全量自动同步）：
- LLM: 不同步（Cline 通过 Cline Provider/ClinePass/BYOK 三种模式认证，不读取本地 llm.yaml）
- MCP: 写入 ~/.cline/mcp.json（mcpServers 格式）
- Skills: 复制到 ~/.cline/skills/
- Rules: 合并写入 ~/.cline/rules/AGENTS.md
- ACP: 写入 ~/.jetbrains/acp.json 的 agent_servers.Cline 条目

参考：
- 官网: https://cline.bot
- 文档: https://docs.cline.bot
- ACP 模式: https://docs.cline.bot/usage/acp
"""
import json
import os
from pathlib import Path

from ..logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_DARKGRAY, COLOR_RESET,
)
from ..mcp import copy_file_safe
from ..skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


# ============================================================
# 配置目录解析
# ============================================================

def _cline_home() -> Path:
    """获取 Cline 配置目录（$CLINE_HOME 或 ~/.cline）。"""
    env_home = os.environ.get("CLINE_HOME")
    if env_home:
        return Path(env_home)
    return Path.home() / ".cline"


def _jetbrains_acp_file() -> Path:
    """获取 JetBrains ACP 配置文件路径（~/.jetbrains/acp.json）。"""
    return Path.home() / ".jetbrains" / "acp.json"


# ============================================================
# ACP agent_servers 配置
# ============================================================

# Cline ACP agent 名称
_ACP_AGENT_NAME = "Cline"

# Cline ACP 启动命令
# 参考: https://docs.cline.bot/usage/acp
_ACP_COMMAND = "npx"
_ACP_ARGS = ["-y", "cline@latest", "acp"]


def _read_acp_json(acp_file: Path) -> dict:
    """读取 acp.json，返回 dict（文件不存在返回空 dict）。"""
    if not acp_file.exists():
        return {}
    try:
        with open(acp_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"{COLOR_YELLOW}[!] 读取 {acp_file.name} 失败: {e}{COLOR_RESET}")
        return {}


def _write_acp_json(acp_file: Path, data: dict) -> None:
    """写入 acp.json（pretty print）。"""
    acp_file.parent.mkdir(parents=True, exist_ok=True)
    with open(acp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"{COLOR_GREEN}[OK] 写入 {acp_file}{COLOR_RESET}")


def _merge_acp_agent_server(acp_file: Path, force: bool) -> bool:
    """合并 Cline 条目到 ~/.jetbrains/acp.json 的 agent_servers 段。

    保留用户已有的其他 agent_servers 条目，仅更新 Cline。
    """
    existing = _read_acp_json(acp_file)
    agent_servers = existing.get("agent_servers", {})
    if not isinstance(agent_servers, dict):
        agent_servers = {}

    cline_entry = {
        "command": _ACP_COMMAND,
        "args": list(_ACP_ARGS),
    }

    if agent_servers.get(_ACP_AGENT_NAME) == cline_entry:
        print(f"{COLOR_DARKGRAY}[~] ACP agent_servers.{_ACP_AGENT_NAME} 已存在且一致{COLOR_RESET}")
        return False

    if _ACP_AGENT_NAME in agent_servers and not force:
        print(f"{COLOR_YELLOW}[!] agent_servers.{_ACP_AGENT_NAME} 已存在，使用 --force 覆盖{COLOR_RESET}")
        return False

    agent_servers[_ACP_AGENT_NAME] = cline_entry
    existing["agent_servers"] = agent_servers
    _write_acp_json(acp_file, existing)
    print(f"{COLOR_CYAN}  → {_ACP_AGENT_NAME}: {_ACP_COMMAND} {' '.join(_ACP_ARGS)}{COLOR_RESET}")
    return True


# ============================================================
# ClineTarget 分发器
# ============================================================

class ClineTarget(IdeTarget):
    """Cline IDE 分发器。

    全量自动同步 MCP/Skills/Rules 到 ~/.cline/ 配置目录，
    并同步 ACP 配置到 ~/.jetbrains/acp.json。

    LLM 不同步：Cline 通过 Cline Provider / ClinePass / BYOK 三种模式认证。
    """
    name = "Cline"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.cline/rules/AGENTS.md。

        Cline CLI 与 JetBrains 插件均支持 ~/.cline/rules/ 作为全局 rules 目录。
        """
        cline_home = _cline_home()
        rules_dir = cline_home / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        agents_md = rules_dir / "AGENTS.md"

        srcs = source_rules if isinstance(source_rules, list) else [source_rules]
        srcs = [s for s in srcs if s.exists()]
        if not srcs:
            print(f"{COLOR_YELLOW}[!] No rules source dirs found{COLOR_RESET}")
            return

        if agents_md.exists() and not self.force:
            print(f"{COLOR_YELLOW}[!] {agents_md.name} exists, use --force to overwrite{COLOR_RESET}")
            return

        chunks = []
        for src in srcs:
            for md_file in sorted(src.glob("*.md")):
                content = md_file.read_text(encoding="utf-8").strip()
                if content:
                    chunks.append(f"<!-- from {md_file.name} -->\n{content}")

        if not chunks:
            print(f"{COLOR_YELLOW}[!] No .md rules files found in source dirs{COLOR_RESET}")
            return

        merged = "\n\n---\n\n".join(chunks)
        agents_md.write_text(merged + "\n", encoding="utf-8")
        print(f"{COLOR_GREEN}[OK] Rules 同步到 {agents_md}{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 配置到 ~/.cline/mcp.json。

        Cline CLI 与 IDE 扩展均从 ~/.cline/mcp.json 读取 MCP 服务器配置。
        格式与 VS Code 的 mcp.json 兼容（mcpServers 字段）。
        """
        cline_home = _cline_home()
        cline_home.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, cline_home / "mcp.json",
                       "~/.cline/mcp.json", self.force)

    def init_llm(self, source_rules_dirs):
        """Cline 不同步 LLM 配置。

        Cline 通过三种模式认证：
        - Cline Provider（usage-billing，最简单）
        - ClinePass（$9.99/月订阅）
        - BYOK（自带 API Key，支持 Anthropic/OpenAI/Google/Bedrock/Vertex/Ollama 等）

        用户需在 Cline 设置面板中配置 Provider，不读取本地 llm.yaml。
        """
        print(f"{COLOR_DARKGRAY}[~] Cline LLM 通过 Cline Provider/ClinePass/BYOK 管理，跳过本地 LLM 同步{COLOR_RESET}")

    def init_skills(self, source_skills_dir: Path):
        """同步 Skills 到 ~/.cline/skills/。

        Cline 通过 MCP Marketplace 提供 skills 发现，此处将本地 skills 复制到
        ~/.cline/skills/ 作为参考库（需用户在 Cline 中手动引用）。
        """
        cline_home = _cline_home()
        cline_skills_dir = cline_home / "skills"
        copy_skills_safe(source_skills_dir, cline_skills_dir, "~/.cline/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, cline_skills_dir / "README.md",
                           "Cline", self.force, self.include_skills)

    def init_manifest(self, source_agents_md: Path):
        """同步 ACP 配置到 ~/.jetbrains/acp.json。

        将 Cline 注册为 ACP agent，使 JetBrains AI Assistant、Zed 等
        ACP 兼容客户端能发现并启动 Cline 进程。
        """
        acp_file = _jetbrains_acp_file()
        _merge_acp_agent_server(acp_file, self.force)
