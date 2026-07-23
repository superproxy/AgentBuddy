"""ZCode（智谱 ADE）IDE 分发器。

同步 MCP 到 ~/.zcode/cli/config.json（mcp.servers 格式，ZCode 实际读取的文件），
同步 LLM 模型到 ~/.zcode/v2/config.json（ZCode provider 格式），
同步 skills 到 ~/.zcode/skills/。
"""
import json
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


class ZCodeTarget(IdeTarget):
    name = "ZCode"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.zcode/rules/。"""
        from lib.mcp import copy_dir_safe
        zcode_rules_dir = Path.home() / ".zcode" / "rules"
        srcs = source_rules if isinstance(source_rules, list) else [source_rules]
        srcs = [s for s in srcs if s.exists()]
        if not srcs:
            print(f"{COLOR_YELLOW}[!] No rules source dirs found{COLOR_RESET}")
            return
        for src in srcs:
            copy_dir_safe(src, zcode_rules_dir, "~/.zcode/rules/", self.force)

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 到 ~/.zcode/cli/config.json（mcp.servers 格式）。

        ZCode 实际读取的 MCP 配置是 ~/.zcode/cli/config.json 的 mcp.servers 字段，
        格式与标准 mcpServers 略有差异：
        - stdio 类型需显式 type: "stdio"
        - 路径为 cli/config.json 而非根目录 mcp.json

        合并已有 cli/config.json 的其他字段（如 plugins），仅更新 mcp.servers。
        force=True 用新 servers 覆盖；否则保留已有 + 新增。
        """
        cli_config = Path.home() / ".zcode" / "cli" / "config.json"
        cli_config.parent.mkdir(parents=True, exist_ok=True)

        if not source_mcp_file.exists():
            print(f"{COLOR_YELLOW}[!] MCP source not found: {source_mcp_file}{COLOR_RESET}")
            return
        try:
            with open(source_mcp_file, "r", encoding="utf-8") as f:
                mcp_data = json.load(f)
        except Exception as e:
            print(f"{COLOR_YELLOW}[!] 解析 mcp.json 失败: {e}{COLOR_RESET}")
            return
        raw_servers = mcp_data.get("mcpServers", {}) if isinstance(mcp_data, dict) else {}

        # 转换为 ZCode 格式：stdio 补 type 字段，跳过 disabled
        new_servers = {}
        for name, cfg in raw_servers.items():
            if not isinstance(cfg, dict):
                continue
            if cfg.get("disabled") is True or cfg.get("disabled") == "true":
                continue
            server = {}
            if "url" in cfg or cfg.get("type") in ("http", "streamableHttp"):
                # http 类型
                server["type"] = cfg.get("type", "http")
                server["url"] = cfg["url"]
                if cfg.get("headers"):
                    server["headers"] = dict(cfg["headers"])
            else:
                # stdio 类型，ZCode 需显式 type
                server["type"] = "stdio"
                server["command"] = cfg.get("command", "")
                if cfg.get("args"):
                    server["args"] = list(cfg["args"])
                if cfg.get("env"):
                    server["env"] = dict(cfg["env"])
            new_servers[name] = server

        existing = {}
        if cli_config.exists():
            try:
                with open(cli_config, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}

        mcp_section = existing.get("mcp", {})
        if not isinstance(mcp_section, dict):
            mcp_section = {}
        servers = mcp_section.get("servers", {})
        if not isinstance(servers, dict):
            servers = {}
        if self.force:
            servers = dict(new_servers)
        else:
            for name, cfg in new_servers.items():
                if name not in servers:
                    servers[name] = cfg
        mcp_section["servers"] = servers
        existing["mcp"] = mcp_section

        with open(cli_config, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"{COLOR_GREEN}[OK] MCP synced to ~/.zcode/cli/config.json ({len(servers)} servers){COLOR_RESET}")

    def init_llm(self, source_rules_dir: Path):
        """同步 LLM 模型到 ~/.zcode/v2/config.json（ZCode provider 格式）。

        从 llm.yaml 读 provider/protocol/model，转换为 ZCode provider：
            {provider: {"custom:<p>-<proto>": {name, kind, options:{apiKey,baseURL}, models}}}
        合并已有 v2/config.json，force 时覆盖同 key，否则新增。
        """
        from lib.config_io import load_env_config_file
        project_root = source_rules_dir.parent.parent
        llm_yaml = project_root / "config" / "llm" / "llm.yaml"
        if not llm_yaml.exists():
            return
        try:
            llm_data = load_env_config_file(llm_yaml)
        except Exception:
            return
        llm = llm_data.get("llm", {}) if isinstance(llm_data, dict) else {}

        new_providers = {}
        for provider_name, provider_value in llm.items():
            if provider_name.startswith("_") or provider_name == "proxy":
                continue
            if not isinstance(provider_value, dict):
                continue
            for protocol, cfg in provider_value.items():
                if not isinstance(cfg, dict) or protocol.startswith("_"):
                    continue
                key = f"custom:{provider_name}-{protocol}"
                kind = "anthropic" if protocol == "anthropic" else "openai-compatible"
                models = {}
                for model_id, model_cfg in (cfg.get("models") or {}).items():
                    m_name = (model_cfg.get("name") if isinstance(model_cfg, dict) else None) or model_id
                    models[model_id] = {
                        "name": m_name,
                        "limit": {"context": 200000},
                        "modalities": {"input": ["text"], "output": ["text"]},
                    }
                new_providers[key] = {
                    "name": f"{provider_name} - {protocol}",
                    "kind": kind,
                    "options": {"apiKey": cfg.get("api_key", ""), "baseURL": cfg.get("base_url", "")},
                    "enabled": False,
                    "source": "custom",
                    "models": models,
                }
        if not new_providers:
            return

        v2_config = Path.home() / ".zcode" / "v2" / "config.json"
        v2_config.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if v2_config.exists():
            try:
                with open(v2_config, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}
        providers = existing.get("provider", {})
        if not isinstance(providers, dict):
            providers = {}
        for key, prov in new_providers.items():
            if self.force or key not in providers:
                providers[key] = prov
        existing["provider"] = providers

        with open(v2_config, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"{COLOR_GREEN}[OK] LLM models synced to ~/.zcode/v2/config.json ({len(new_providers)} providers){COLOR_RESET}")

    def init_skills(self, source_skills_dir: Path):
        zcode_skills_dir = Path.home() / ".zcode" / "skills"
        copy_skills_safe(source_skills_dir, zcode_skills_dir, "~/.zcode/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, zcode_skills_dir / "README.md",
                           "ZCode", self.force, self.include_skills)
