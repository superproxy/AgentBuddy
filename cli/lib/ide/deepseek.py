"""DeepSeek Harness (dsh) IDE 分发器。

DeepSeek Harness（命令行简称 dsh）是 DeepSeek AI 开源的原生 Agent Harness，
采用"一切皆插件"（Everything is a Plugin）架构，由 Cordis 微内核驱动。

核心特性：
- 启动入口：`npx @deepseek-ai/dsh web`（Web UI，默认 http://127.0.0.1:3080）、
  `dsh --profile <name>`（命名 profile）、`dsh --profile headless "<job>"`（单次任务）
- 工作模式：标准 / 极简 / PTC / 创造（内置 Agent Preset）
- 配置目录：$DSH_HOME（默认 ~/.dsh），模型/凭证/技能均由 Web UI 或插件系统管理
- 模型密钥：~/.dsh/.credentials.yaml（Web UI Settings→Models 输入 DeepSeek API Key）

同步策略（全量自动同步）：
- LLM：写入 ~/.dsh/settings.yaml 的 llm-pi-ai.providers 段 + ~/.dsh/.credentials.yaml 凭证
- MCP：写入 ~/.dsh/cordis.patch.yml 的 mcp-client 插件条目
- Skills：复制到 ~/.dsh/skills/（dsh 本地发现的 user-dsh 源，rank 400）
- Rules：复制到 ~/.dsh/AGENTS.md（dsh 用户全局指令文件）
"""
import json
import os
from pathlib import Path

from lib.logging import (
    COLOR_CYAN, COLOR_GREEN, COLOR_YELLOW, COLOR_DARKGRAY, COLOR_RESET,
)
from lib.skills import copy_skills_safe, write_skills_index
from lib.llm import load_split_env_config
from .base import IdeTarget


# ============================================================
# dsh 配置目录解析
# ============================================================

def _dsh_home() -> Path:
    """获取 dsh 配置目录（$DSH_HOME 或 ~/.dsh）。"""
    env_home = os.environ.get("DSH_HOME")
    if env_home:
        return Path(env_home)
    return Path.home() / ".dsh"


# ============================================================
# LLM 协议映射：llm.yaml → dsh pi-ai api 字段
# ============================================================

# dsh llm-pi-ai 支持的协议：openai-completions / openai-responses / anthropic-messages
_PROTO_MAP = {
    "openaiv1": "openai-completions",
    "openai": "openai-completions",
    "responses": "openai-responses",
    "anthropic": "anthropic-messages",
}


def _credential_env_name(provider_name: str) -> str:
    """生成 provider 对应的环境变量名（apiKeyEnv）。

    规则：DEEPSEEK_API_KEY / OPENAI_API_KEY / <PROVIDER>_API_KEY
    """
    special = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    if provider_name in special:
        return special[provider_name]
    return f"{provider_name.upper().replace('-', '_')}_API_KEY"


def _build_pi_ai_providers(env_config: dict | None,
                           ide_protocols: list[str] | None = None) -> tuple[dict, dict]:
    """从 llm.yaml 构建 dsh llm-pi-ai.providers 配置和 credentials 映射。

    Returns:
        (providers_dict, credentials_dict)
        - providers_dict: {provider_route: {apiKeyEnv, api, baseURL, models}}
        - credentials_dict: {ENV_VAR_NAME: api_key_value}
    """
    if not env_config:
        return {}, {}

    llm_section = env_config.get("llm", {})
    if not isinstance(llm_section, dict):
        return {}, {}

    providers = {}
    credentials = {}

    for provider_name, provider_value in llm_section.items():
        if provider_name.startswith("_") or not isinstance(provider_value, dict):
            continue
        # 跳过未启用的 provider
        if provider_value.get("_enabled") is False:
            continue

        # 协议优先级：openai/openaiv1 > responses > anthropic
        _PROTO_PRIORITY = {"openaiv1": 0, "openai": 0, "responses": 1, "anthropic": 2}
        protocol_items = sorted(
            (p for p in provider_value.items()
             if not p[0].startswith("_") and isinstance(p[1], dict)),
            key=lambda item: _PROTO_PRIORITY.get(item[0], 9),
        )

        for protocol_name, protocol_value in protocol_items:
            # 兼容旧协议名 openai → openaiv1
            proto_check = "openaiv1" if protocol_name == "openai" else protocol_name
            # IDE 协议过滤
            if ide_protocols is not None and proto_check not in ide_protocols:
                continue

            base_url = str(protocol_value.get("base_url", "")).strip()
            api_key = str(protocol_value.get("api_key", "")).strip()
            if not base_url or not api_key:
                continue
            if api_key.startswith("${"):
                continue  # 未解析的占位符

            dsh_api = _PROTO_MAP.get(proto_check)
            if not dsh_api:
                continue

            models_dict = protocol_value.get("models", {})
            if not isinstance(models_dict, dict) or not models_dict:
                continue

            # 构建 models 列表
            models_list = []
            for model_id, model_meta in models_dict.items():
                if model_id.startswith("~"):
                    continue
                if isinstance(model_meta, dict):
                    model_name = str(model_meta.get("name", "")).strip() or model_id
                else:
                    model_name = str(model_meta).strip() or model_id
                model_entry = {"id": model_id, "name": model_name}
                models_list.append(model_entry)

            if not models_list:
                continue

            # provider route 名称（dsh 用 lowercase provider id）
            route_name = provider_name.lower()
            env_var = _credential_env_name(provider_name.lower())

            # 同一 route 只取第一个有效协议（优先级最高）
            if route_name in providers:
                continue

            providers[route_name] = {
                "apiKeyEnv": env_var,
                "api": dsh_api,
                "baseURL": base_url,
                "models": models_list,
            }
            credentials[env_var] = api_key

    return providers, credentials


# ============================================================
# YAML 读写（保留注释和格式，合并写入）
# ============================================================

def _read_yaml_file(file_path: Path) -> dict:
    """读取 YAML 文件，返回 dict（文件不存在返回空 dict）。"""
    if not file_path.exists():
        return {}
    try:
        import yaml
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"{COLOR_YELLOW}[!] 读取 {file_path.name} 失败: {e}{COLOR_RESET}")
        return {}


def _write_yaml_file(file_path: Path, data: dict) -> None:
    """写入 YAML 文件。"""
    import yaml
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False, width=1000)
    print(f"{COLOR_GREEN}[OK] 写入 {file_path}{COLOR_RESET}")


def _merge_llm_to_settings(settings_file: Path, providers: dict, force: bool) -> None:
    """合并 llm-pi-ai.providers 到 settings.yaml。

    只更新 llm-pi-ai.providers 段，保留用户已有的其他配置。
    force=True 时覆盖已有 provider，否则保留用户手动添加的。
    """
    existing = _read_yaml_file(settings_file)

    # 获取或创建 llm-pi-ai 段
    llm_pi_ai = existing.get("llm-pi-ai", {})
    if not isinstance(llm_pi_ai, dict):
        llm_pi_ai = {}
    existing_providers = llm_pi_ai.get("providers", {})
    if not isinstance(existing_providers, dict):
        existing_providers = {}

    # 合并 providers
    updated = False
    for route_name, profile in providers.items():
        if route_name in existing_providers and not force:
            # 非 force 模式跳过已存在的（保留用户手动配置）
            continue
        existing_providers[route_name] = profile
        updated = True

    if not updated and not existing_providers:
        return

    llm_pi_ai["providers"] = existing_providers
    existing["llm-pi-ai"] = llm_pi_ai
    _write_yaml_file(settings_file, existing)


def _merge_credentials(cred_file: Path, credentials: dict, force: bool) -> None:
    """合并凭证到 .credentials.yaml（CredentialRef -> string 映射）。"""
    if not credentials:
        return

    existing = _read_yaml_file(cred_file)
    updated = False
    for env_var, api_key in credentials.items():
        if env_var in existing and not force:
            continue
        existing[env_var] = api_key
        updated = True

    if not updated:
        return

    _write_yaml_file(cred_file, existing)


# ============================================================
# MCP 配置转换：mcp.json → cordis.patch.yml
# ============================================================

def _convert_mcp_to_cordis_patch(source_mcp_file: Path) -> list:
    """读取 mcp.json，转换为 dsh cordis.patch.yml 的 insert 条目列表。

    每个 MCP server 对应一个 mcp-client 插件条目。
    """
    if not source_mcp_file.exists():
        return []

    with open(source_mcp_file, "r", encoding="utf-8") as f:
        content = json.load(f)

    mcp_servers = content.get("mcpServers", content)
    if not isinstance(mcp_servers, dict):
        return []

    entries = []
    for server_name, server_cfg in mcp_servers.items():
        # 跳过禁用的 server
        if server_cfg.get("disabled", False):
            continue

        plugin_id = f"mcp-{server_name}"
        is_http = (server_cfg.get("type") in ("http", "streamableHttp")
                    or server_cfg.get("url"))

        if is_http:
            config = {
                "transport": "streamable-http",
                "serverName": server_name,
                "url": server_cfg.get("url", ""),
            }
            headers = server_cfg.get("headers")
            if headers:
                config["headers"] = dict(headers)
        else:
            config = {
                "transport": "stdio",
                "serverName": server_name,
                "command": server_cfg.get("command", ""),
            }
            args = server_cfg.get("args")
            if args:
                config["args"] = list(args)
            env = server_cfg.get("env")
            if env:
                config["env"] = dict(env)

        entries.append({
            "id": plugin_id,
            "name": "@deepseek-ai/dsh-mcp-client",
            "config": config,
        })

    return entries


def _merge_mcp_to_patch(patch_file: Path, mcp_entries: list, force: bool) -> None:
    """合并 MCP 条目到 cordis.patch.yml。

    cordis.patch.yml 格式：顶层 YAML 数组，包含 insert/replace 操作。
    保留用户已有的非 mcp-* 条目。
    """
    import yaml

    # 读取现有 patch
    existing_entries = []
    if patch_file.exists():
        try:
            with open(patch_file, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if isinstance(raw, list):
                existing_entries = raw
            elif raw is None:
                existing_entries = []
        except Exception as e:
            print(f"{COLOR_YELLOW}[!] 读取 {patch_file.name} 失败: {e}，将覆盖{COLOR_RESET}")

    # 提取现有的 mcp 条目 id 集合
    existing_mcp_ids = set()
    cleaned_entries = []
    for entry in existing_entries:
        if isinstance(entry, dict):
            # 支持 - insert: [...] 和直接 - id: ... 两种格式
            if "insert" in entry and isinstance(entry["insert"], list):
                for item in entry["insert"]:
                    if isinstance(item, dict) and item.get("id", "").startswith("mcp-"):
                        existing_mcp_ids.add(item["id"])
                    else:
                        cleaned_entries.append({"insert": [item]})
                continue
            entry_id = entry.get("id", "")
            if entry_id.startswith("mcp-"):
                existing_mcp_ids.add(entry_id)
                continue
        cleaned_entries.append(entry)

    # 合并新 mcp 条目
    new_entries = []
    for mcp_entry in mcp_entries:
        entry_id = mcp_entry.get("id", "")
        if entry_id in existing_mcp_ids and not force:
            continue
        new_entries.append(mcp_entry)

    if not new_entries:
        if not existing_mcp_ids:
            return  # 没有任何 mcp 条目，也不需要新增
        print(f"{COLOR_DARKGRAY}[~] MCP 条目已存在，跳过（使用 --force 覆盖）{COLOR_RESET}")
        # 仍然重建文件以包含清理后的条目
    else:
        print(f"{COLOR_GREEN}[OK] 新增 {len(new_entries)} 个 MCP 条目{COLOR_RESET}")

    # 重写文件：非 MCP 条目 + 新 MCP 条目
    final_entries = cleaned_entries + new_entries
    if not final_entries:
        final_entries = []  # 空数组，dsh 要求空时用 []

    patch_file.parent.mkdir(parents=True, exist_ok=True)
    with open(patch_file, "w", encoding="utf-8") as f:
        yaml.dump(final_entries, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False, width=1000)
    print(f"{COLOR_GREEN}[OK] 写入 {patch_file}{COLOR_RESET}")


# ============================================================
# DeepSeekTarget 分发器
# ============================================================

class DeepSeekTarget(IdeTarget):
    """DeepSeek Harness (dsh) IDE 分发器。

    全量自动同步 LLM/MCP/Skills/Rules 到 ~/.dsh/ 配置目录。
    """
    name = "DeepSeek"

    def init_rules(self, source_rules: Path):
        """同步 rules 到 ~/.dsh/AGENTS.md（dsh 用户全局指令文件）。

        dsh 的 agent-instructions 插件会从 $DSH_HOME/AGENTS.md 加载用户全局指令。
        source_rules 目录下可能有多个 .md 文件，合并写入。
        """
        dsh_home = _dsh_home()
        agents_md = dsh_home / "AGENTS.md"

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

        agents_md.parent.mkdir(parents=True, exist_ok=True)
        merged = "\n\n---\n\n".join(chunks)
        agents_md.write_text(merged + "\n", encoding="utf-8")
        print(f"{COLOR_GREEN}[OK] Rules 同步到 {agents_md}{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        """同步 MCP 到 ~/.dsh/cordis.patch.yml（mcp-client 插件条目）。

        dsh 的 MCP 通过 cordis.patch.yml 声明 mcp-client 插件实例，
        支持 stdio 和 streamable-http 传输协议。
        """
        mcp_entries = _convert_mcp_to_cordis_patch(source_mcp_file)
        if not mcp_entries:
            print(f"{COLOR_YELLOW}[!] No MCP servers to sync{COLOR_RESET}")
            return

        dsh_home = _dsh_home()
        patch_file = dsh_home / "cordis.patch.yml"
        _merge_mcp_to_patch(patch_file, mcp_entries, self.force)

    def init_llm(self, source_rules_dirs):
        """同步 LLM 到 ~/.dsh/settings.yaml + ~/.dsh/.credentials.yaml。

        - settings.yaml 的 llm-pi-ai.providers 段配置 provider 路由（apiKeyEnv/api/baseURL/models）
        - .credentials.yaml 存储 API Key 实际值（CredentialRef -> string 映射）
        """
        env_config = load_split_env_config(self.root, silent=True)
        providers, credentials = _build_pi_ai_providers(env_config, self.ide_protocols)

        if not providers:
            print(f"{COLOR_YELLOW}[!] No enabled LLM providers to sync{COLOR_RESET}")
            return

        dsh_home = _dsh_home()
        settings_file = dsh_home / "settings.yaml"
        cred_file = dsh_home / ".credentials.yaml"

        _merge_llm_to_settings(settings_file, providers, self.force)
        _merge_credentials(cred_file, credentials, self.force)

        # 打印同步的 provider 列表
        for route_name, profile in providers.items():
            model_count = len(profile.get("models", []))
            print(f"{COLOR_CYAN}  → {route_name}: {profile['api']} ({model_count} models){COLOR_RESET}")

    def init_skills(self, source_skills_dir: Path):
        """同步 Skills 到 ~/.dsh/skills/（dsh 本地发现的 user-dsh 源，rank 400）。

        dsh 的 skill 本地发现支持：
        - <projectRoot>/.dsh/skills（project-dsh, rank 100）
        - <projectRoot>/.agents/skills（project-agents, rank 200）
        - <dshHome>/skills（user-dsh, rank 400）
        格式：<name>/SKILL.md 或 <name>.md
        """
        dsh_home = _dsh_home()
        dsh_skills_dir = dsh_home / "skills"
        copy_skills_safe(source_skills_dir, dsh_skills_dir, "~/.dsh/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, dsh_skills_dir / "README.md",
                           "DeepSeek Harness", self.force, self.include_skills)
