"""Kimi 三件套 IDE 分发器。

Kimi 是月之暗面（Moonshot AI）的 AI 编程产品线，包含三个互补产品：

1. Kimi CLI（旧版，Python/uv）：技术预览版 CLI agent，仓库 MoonshotAI/kimi-cli
   - 配置目录：~/.kimi/
   - 主配置：~/.kimi/config.toml
   - MCP：~/.kimi/mcp.json（通过 `kimi --mcp-config-file <path>` 加载）
   - 会话：~/.kimi/sessions/<workDirHash>/<sessionId>/{state.json, context.jsonl, wire.jsonl}
   - 已逐步迁移到新版 Kimi Code CLI

2. Kimi Code（新版，Node.js 二进制发行）：仓库 MoonshotAI/kimi-code
   - 配置目录：~/.kimi-code/
   - 主配置：~/.kimi-code/config.toml
   - MCP：~/.kimi-code/mcp.json（通过 `kimi --mcp-config-file <path>` 加载，也支持 `/mcp-config` 对话式配置）
   - 会话：~/.kimi-code/sessions/<workDirKey>/<sessionId>/{state.json, agents/*/wire.jsonl}
   - 支持 ACP、子 Agent、Hooks、插件生态

3. Kimi Work（桌面应用，Kimi Desktop App 的 Work 模式）：知识工作者桌面 Agent
   - macOS：/Applications/Kimi Work.app（或 /Applications/Kimi.app）
   - Windows：%LOCALAPPDATA%/Programs/Kimi Work/Kimi Work.exe
   - 工作区：~/Documents/KimiWorkspace（用户文件）
   - 内置 Skill 系统、Cron 定时、WebBridge 浏览器自动化、Agent Swarm
   - 配置目录：~/.kimi-work/（运行态数据）

三者均支持标准 mcpServers 格式的 MCP 配置，可用 `--mcp-config-file` 参数加载。
"""
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class KimiCLITarget(IdeTarget):
    """Kimi CLI（旧版 Python/uv）分发器。

    仓库：MoonshotAI/kimi-cli
    安装：`uv tool install --python 3.13 kimi-cli`
    配置：~/.kimi/config.toml
    """
    name = "KimiCLI"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.kimi/rules/。"""
        rules_dir = Path.home() / ".kimi" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        srcs = source_rules if isinstance(source_rules, list) else [source_rules]
        srcs = [s for s in srcs if s.exists()]
        if not srcs:
            print(f"{COLOR_YELLOW}[!] No rules source dirs found{COLOR_RESET}")
            return
        for src in srcs:
            copy_dir_safe(src, rules_dir, "~/.kimi/rules/", self.force)

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 到 ~/.kimi/mcp.json。

        Kimi CLI 通过 `kimi --mcp-config-file <path>` 加载 MCP 配置，
        格式为标准 mcpServers JSON（与 Cursor/Claude 一致）。
        """
        kimi_dir = Path.home() / ".kimi"
        kimi_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, kimi_dir / "mcp.json",
                       "~/.kimi/mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 ~/.kimi/skills/。

        注：Kimi CLI 的 KIMI_SHARE_DIR 仅影响运行态数据，
        不影响 Agent Skills 搜索路径，故 skills 单独放 ~/.kimi/skills/。
        """
        skills_dir = Path.home() / ".kimi" / "skills"
        copy_skills_safe(source_skills_dir, skills_dir, "~/.kimi/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, skills_dir / "README.md",
                           "Kimi CLI", self.force, self.include_skills)


class KimiCodeTarget(IdeTarget):
    """Kimi Code（新版 Node.js 二进制）分发器。

    仓库：MoonshotAI/kimi-code
    安装：
      macOS/Linux：`curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash`
      Windows：`irm https://code.kimi.com/kimi-code/install.ps1 | iex`
    配置：~/.kimi-code/config.toml
    """
    name = "KimiCode"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.kimi-code/rules/。"""
        rules_dir = Path.home() / ".kimi-code" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        srcs = source_rules if isinstance(source_rules, list) else [source_rules]
        srcs = [s for s in srcs if s.exists()]
        if not srcs:
            print(f"{COLOR_YELLOW}[!] No rules source dirs found{COLOR_RESET}")
            return
        for src in srcs:
            copy_dir_safe(src, rules_dir, "~/.kimi-code/rules/", self.force)

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 到 ~/.kimi-code/mcp.json。

        Kimi Code 支持两种 MCP 配置方式：
        1. 命令行 `kimi --mcp-config-file <path>` 加载标准 mcpServers JSON
        2. 交互式 `/mcp-config` 对话配置（写入 config.toml）

        本同步采用方式 1，写入 ~/.kimi-code/mcp.json，
        用户可在启动 kimi 时加 `--mcp-config-file ~/.kimi-code/mcp.json` 加载。
        """
        kimi_dir = Path.home() / ".kimi-code"
        kimi_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, kimi_dir / "mcp.json",
                       "~/.kimi-code/mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 ~/.kimi-code/skills/。"""
        skills_dir = Path.home() / ".kimi-code" / "skills"
        copy_skills_safe(source_skills_dir, skills_dir, "~/.kimi-code/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, skills_dir / "README.md",
                           "Kimi Code", self.force, self.include_skills)


class KimiWorkTarget(IdeTarget):
    """Kimi Work（桌面应用）分发器。

    定位：Moonshot 桌面 AI Agent，面向知识工作者（非 IDE 编程）。
    内置 Skill 系统、Cron 定时、WebBridge 浏览器自动化、Agent Swarm。

    macOS：/Applications/Kimi Work.app
    Windows：%LOCALAPPDATA%/Programs/Kimi Work/Kimi Work.exe
    配置目录：~/.kimi-work/
    工作区：~/Documents/KimiWorkspace（用户文件，非配置）
    """
    name = "KimiWork"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.kimi-work/rules/。"""
        rules_dir = Path.home() / ".kimi-work" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        srcs = source_rules if isinstance(source_rules, list) else [source_rules]
        srcs = [s for s in srcs if s.exists()]
        if not srcs:
            print(f"{COLOR_YELLOW}[!] No rules source dirs found{COLOR_RESET}")
            return
        for src in srcs:
            copy_dir_safe(src, rules_dir, "~/.kimi-work/rules/", self.force)

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 到 ~/.kimi-work/mcp.json。

        Kimi Work 插件系统支持 MCP 服务器，可通过标准 mcpServers JSON 配置加载。
        """
        kimi_dir = Path.home() / ".kimi-work"
        kimi_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, kimi_dir / "mcp.json",
                       "~/.kimi-work/mcp.json", self.force)

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 ~/.kimi-work/skills/。

        Kimi Work 内置 Skill 系统，可安装/复用社区分享的 Skill
        （建站、PPT、金融分析等），与本仓库的 skills 体系天然对齐。
        """
        skills_dir = Path.home() / ".kimi-work" / "skills"
        copy_skills_safe(source_skills_dir, skills_dir, "~/.kimi-work/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, skills_dir / "README.md",
                           "Kimi Work", self.force, self.include_skills)
