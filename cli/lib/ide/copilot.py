"""GitHub Copilot IDE 分发器。

GitHub Copilot 是 GitHub 官方 AI 编程助手，支持多种形态：
- CLI: npm @github/copilot（copilot 命令）
- Desktop App: GitHub Copilot.app
- VS Code 扩展: GitHub.copilot
- JetBrains 插件: com.github.copilot（Marketplace ID 17718）
- ACP 模式: npx -y @github/copilot-language-server --acp

本分发器同步策略（全量自动同步）：
- LLM: 不直接同步（Copilot 通过 GitHub 账号认证，不读取本地 llm.yaml）
- MCP: 写入 ~/.copilot/mcp.json（Copilot CLI 与 JetBrains 插件均从此读取）
- Skills: 复制到 ~/.copilot/skills/
- Rules: 复制到 ~/.copilot/AGENTS.md
- ACP: 写入 ~/.jetbrains/acp.json 的 agent_servers.GitHub Copilot 条目
      （使 JetBrains AI Assistant / Zed 等可发现并启动 Copilot ACP 进程）

参考：
- ACP 规范: https://agentclientprotocol.com
- Copilot ACP 模式: npx -y @github/copilot-language-server --acp
- JetBrains ACP 配置: ~/.jetbrains/acp.json
"""
import json
import os
from pathlib import Path

from ..logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_DARKGRAY, COLOR_RESET,
)
from ..mcp import copy_file_safe, copy_dir_safe
from ..skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


# ============================================================
# 配置目录解析
# ============================================================

def _copilot_home() -> Path:
    """获取 Copilot 配置目录（$COPILOT_HOME 或 ~/.copilot）。"""
    env_home = os.environ.get("COPILOT_HOME")
    if env_home:
        return Path(env_home)
    return Path.home() / ".copilot"


def _jetbrains_acp_file() -> Path:
    """获取 JetBrains ACP 配置文件路径。

    跨平台：~/.jetbrains/acp.json
    （JetBrains AI Assistant 自 2025.12 起原生支持 ACP）
    """
    return Path.home() / ".jetbrains" / "acp.json"


# ============================================================
# ACP agent_servers 配置
# ============================================================

# Copilot ACP agent 名称（在 JetBrains/Zed 中显示的名称）
_ACP_AGENT_NAME = "GitHub Copilot"

# Copilot ACP 启动命令
_ACP_COMMAND = "npx"
_ACP_ARGS = ["-y", "@github/copilot-language-server@latest", "--acp"]


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
    """合并 GitHub Copilot 条目到 ~/.jetbrains/acp.json 的 agent_servers 段。

    保留用户已有的其他 agent_servers 条目，仅更新 GitHub Copilot。

    Returns:
        True 表示有更新（新增或覆盖），False 表示跳过。
    """
    existing = _read_acp_json(acp_file)
    agent_servers = existing.get("agent_servers", {})
    if not isinstance(agent_servers, dict):
        agent_servers = {}

    copilot_entry = {
        "command": _ACP_COMMAND,
        "args": list(_ACP_ARGS),
    }

    if agent_servers.get(_ACP_AGENT_NAME) == copilot_entry:
        # 配置已完全一致，无需重写
        print(f"{COLOR_DARKGRAY}[~] ACP agent_servers.{_ACP_AGENT_NAME} 已存在且一致{COLOR_RESET}")
        return False

    if _ACP_AGENT_NAME in agent_servers and not force:
        print(f"{COLOR_YELLOW}[!] agent_servers.{_ACP_AGENT_NAME} 已存在，使用 --force 覆盖{COLOR_RESET}")
        return False

    agent_servers[_ACP_AGENT_NAME] = copilot_entry
    existing["agent_servers"] = agent_servers
    _write_acp_json(acp_file, existing)
    print(f"{COLOR_CYAN}  → {_ACP_AGENT_NAME}: {_ACP_COMMAND} {' '.join(_ACP_ARGS)}{COLOR_RESET}")
    return True


# ============================================================
# CopilotTarget 分发器
# ============================================================

class CopilotTarget(IdeTarget):
    """GitHub Copilot IDE 分发器。

    全量自动同步 MCP/Skills/Rules 到 ~/.copilot/ 配置目录，
    并同步 ACP 配置到 ~/.jetbrains/acp.json（供 JetBrains AI Assistant 调用）。

    LLM 不同步：Copilot 通过 GitHub 账号认证，API Key 由 GitHub 服务端管理。
    """
    name = "Copilot"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.copilot/AGENTS.md。

        Copilot CLI 与 JetBrains 插件均会读取 ~/.copilot/AGENTS.md 作为项目指令。
        source_rules 目录下可能有多个 .md 文件，合并写入。
        """
        copilot_home = _copilot_home()
        copilot_home.mkdir(parents=True, exist_ok=True)
        agents_md = copilot_home / "AGENTS.md"

        srcs = source_rules if isinstance(source_rules, list) else [source_rules]
        srcs = [s for s in srcs if s.exists()]
        if not srcs:
            print(f"{COLOR_YELLOW}[!] No rules source dirs found{COLOR_RESET}")
            return

        if agents_md.exists() and not self.force:
            print(f"{COLOR_YELLOW}[!] {agents_md.name} exists, use --force to overwrite{COLOR_RESET}")
            return

        # 收集所有 rules markdown 文件内容
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
        """同步 MCP 配置到 ~/.copilot/mcp.json。

        Copilot CLI 与 JetBrains 插件均从 ~/.copilot/mcp.json 读取 MCP 服务器配置。
        格式与 VS Code 的 mcp.json 兼容（mcpServers 字段）。
        """
        copilot_home = _copilot_home()
        copilot_home.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, copilot_home / "mcp.json",
                       "~/.copilot/mcp.json", self.force)

    def init_llm(self, source_rules_dirs):
        """Copilot 不同步 LLM 配置。

        Copilot 通过 GitHub 账号认证（OAuth Device Flow），API Key 由 GitHub 服务端管理，
        不读取本地 llm.yaml。用户需在 Copilot CLI 首次启动时完成 GitHub 登录授权。
        """
        # 显式跳过，避免被误认为遗漏
        print(f"{COLOR_DARKGRAY}[~] Copilot LLM 由 GitHub 账号管理，跳过本地 LLM 同步{COLOR_RESET}")

    def init_skills(self, source_skills_dir: Path):
        """同步 Skills 到 ~/.copilot/skills/。

        Copilot CLI 支持 skills 发现（社区预览特性），格式与 VS Code 兼容。
        """
        copilot_home = _copilot_home()
        copilot_skills_dir = copilot_home / "skills"
        copy_skills_safe(source_skills_dir, copilot_skills_dir, "~/.copilot/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, copilot_skills_dir / "README.md",
                           "GitHub Copilot", self.force, self.include_skills)

    def init_manifest(self, source_agents_md: Path):
        """同步 ACP 配置到 ~/.jetbrains/acp.json。

        将 GitHub Copilot 注册为 ACP agent，使 JetBrains AI Assistant、Zed 等
        ACP 兼容客户端能发现并启动 Copilot 进程。

        配置格式（参考 @github/copilot-language-server 官方文档）:
        {
          "agent_servers": {
            "GitHub Copilot": {
              "command": "npx",
              "args": ["-y", "@github/copilot-language-server@latest", "--acp"]
            }
          }
        }
        """
        acp_file = _jetbrains_acp_file()
        _merge_acp_agent_server(acp_file, self.force)
