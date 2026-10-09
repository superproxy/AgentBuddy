"""Pi IDE 分发器。

Pi 是 earendil-works 开发的极简 agent harness（CLI 工具）。
官网：https://pi.dev/
GitHub：https://github.com/earendil-works/pi

配置目录：~/.pi/
- rules → ~/.pi/agent/（AGENTS.md 项目指令）
- mcp → ~/.pi/agent/mcp.json（Pi 全局 MCP 覆盖文件；home 下 ~/.pi/mcp.json 非标准加载路径）
- skills → ~/.pi/skills/
- llm → ~/.pi/agent/models.json（官方路径，docs/models.md + docs/custom-provider.md）
"""
import json
from pathlib import Path

from ..logging import COLOR_CYAN, COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from ..mcp import copy_dir_safe, copy_file_safe
from ..llm import load_split_env_config, resolve_config_secret
from ..skills import copy_skills_safe, write_skills_index
from .base import IdeTarget


# Pi models.json 支持的 api 协议（与 dsh 的 llm-pi-ai 一致）
_PI_PROTO_MAP = {
    "openaiv1": "openai-completions",
    "openai": "openai-completions",
    "responses": "openai-responses",
    "anthropic": "anthropic-messages",
}
# 协议优先级：openaiv1/openai > responses > anthropic
_PI_PROTO_PRIORITY = {"openaiv1": 0, "openai": 0, "responses": 1, "anthropic": 2}
# 网关在 Pi models.json 中的 provider 名（与 Codex/Claude 的 agentbuddy-gateway 一致）
_GATEWAY_ROUTE = "agentbuddy-gateway"


def _usable_secret(value, env_config: dict | None) -> str:
    """解析 ${VAR}。仍是占位符或空串时返回空，表示该字段不可用。"""
    resolved = resolve_config_secret(str(value or ""), env_config)
    if not resolved or resolved.startswith("${"):
        return ""
    return resolved


def _enabled_models(models_dict) -> list[dict]:
    if not isinstance(models_dict, dict):
        return []
    models = []
    for model_id, meta in models_dict.items():
        if str(model_id).startswith("~"):
            continue
        if isinstance(meta, dict) and meta.get("_enabled", True) is False:
            continue
        name = str(meta.get("name", "")).strip() if isinstance(meta, dict) else str(meta).strip()
        models.append({"id": model_id, "name": name or model_id})
    return models


def _pick_default(providers: dict, env_config: dict | None) -> tuple[str, str]:
    """选出写入 settings.json 的 provider 与 model。"""
    llm = env_config.get("llm", {}) if isinstance(env_config, dict) else {}
    if not isinstance(llm, dict):
        llm = {}
    active_provider = str(llm.get("_active_provider") or "").strip().lower()
    active_model = str(llm.get("_active_model") or "").strip()

    if _GATEWAY_ROUTE in providers:
        name = _GATEWAY_ROUTE
    elif active_provider in providers:
        name = active_provider
    else:
        name = next(iter(providers))
    model_ids = [m["id"] for m in providers[name].get("models", [])]
    model = active_model if active_model in model_ids else (model_ids[0] if model_ids else "")
    return name, model


def _write_pi_settings(settings_file: Path, provider: str, model: str) -> None:
    """合并 defaultProvider / defaultModel，保留 theme、packages 等已有字段。"""
    existing = {}
    if settings_file.exists():
        try:
            loaded = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}
    existing["defaultProvider"] = provider
    existing["defaultModel"] = model
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _build_pi_providers(env_config: dict | None,
                        ide_protocols: list[str] | None = None) -> dict:
    """从 llm.yaml / proxy.gateway 构建 Pi models.json 的 providers 段。

    网关启用时只生成网关 provider（路由全部走 LiteLLM 网关）；
    否则遍历启用的 provider，按协议优先级展开模型列表。
    """
    if not env_config:
        return {}

    # --- LLM 网关模式 ---
    gateway = env_config.get("proxy", {}).get("gateway", {})
    if isinstance(gateway, dict) and gateway.get("enabled"):
        base_url = _usable_secret(
            gateway.get("base_url", "http://127.0.0.1:4000/v1"), env_config,
        ) or "http://127.0.0.1:4000/v1"
        raw_key = str(gateway.get("api_key", "") or "").strip()
        api_key = _usable_secret(raw_key, env_config) if raw_key else ""
        if raw_key.startswith("${") and not api_key:
            return {}
        api_key = api_key or "sk-agentbuddy-gateway"
        models = []
        for route in gateway.get("routes", []):
            if not isinstance(route, dict) or not route.get("enabled", True):
                continue
            gateway_model = str(route.get("gateway_model", "")).strip()
            if not gateway_model:
                continue
            models.append({"id": gateway_model, "name": gateway_model})
        if not models:
            return {}
        return {
            _GATEWAY_ROUTE: {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": api_key,
                "models": models,
            }
        }

    # --- 独立 Provider 直连模式 ---
    llm_section = env_config.get("llm", {})
    if not isinstance(llm_section, dict):
        return {}

    providers = {}
    for provider_name, provider_value in llm_section.items():
        if provider_name.startswith("_") or provider_name == "proxy":
            continue
        if not isinstance(provider_value, dict) or provider_value.get("_enabled") is False:
            continue
        # 同一 provider 只取优先级最高的有效协议
        protocol_items = sorted(
            (p for p in provider_value.items()
             if not p[0].startswith("_") and isinstance(p[1], dict)),
            key=lambda item: _PI_PROTO_PRIORITY.get(item[0], 9),
        )
        for protocol_name, protocol_value in protocol_items:
            proto_check = "openaiv1" if protocol_name == "openai" else protocol_name
            if ide_protocols is not None and proto_check not in ide_protocols:
                continue
            base_url = _usable_secret(protocol_value.get("base_url", ""), env_config)
            api_key = _usable_secret(protocol_value.get("api_key", ""), env_config)
            if not base_url or not api_key:
                continue
            pi_api = _PI_PROTO_MAP.get(proto_check)
            if not pi_api:
                continue
            models = _enabled_models(protocol_value.get("models", {}))
            if not models:
                continue
            providers[provider_name.lower()] = {
                "baseUrl": base_url,
                "api": pi_api,
                "apiKey": api_key,
                "models": models,
            }
            break  # 一个 provider 只取第一个有效协议

    return providers


def generate_pi_models(env_config: dict | None, target_file: Path, force: bool,
                       ide_protocols: list[str] | None = None) -> None:
    """生成 ~/.pi/agent/models.json，并更新同目录 settings.json 的默认模型。

    格式：{"providers": {"<name>": {"baseUrl", "api", "apiKey", "models": [{"id","name"}]}}}
    - 文件已存在且未 --force 时跳过（保留用户手动配置）
    - settings.json 只改 defaultProvider / defaultModel，其余字段保留
    """
    if not env_config:
        print(f"{COLOR_YELLOW}[!] llm.yaml not found, skip models.json{COLOR_RESET}")
        return

    if target_file.exists() and not force:
        print(f"{COLOR_YELLOW}[!] {target_file.name} exists, use --force to overwrite{COLOR_RESET}")
        return

    providers = _build_pi_providers(env_config, ide_protocols)
    if not providers:
        print(f"{COLOR_YELLOW}[!] No enabled LLM providers to sync{COLOR_RESET}")
        return

    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump({"providers": providers}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    provider, model = _pick_default(providers, env_config)
    _write_pi_settings(target_file.parent / "settings.json", provider, model)
    for name, cfg in providers.items():
        print(f"{COLOR_CYAN}  → {name}: {cfg['api']} ({len(cfg['models'])} models){COLOR_RESET}")
    print(f"{COLOR_CYAN}  → default {provider}/{model}{COLOR_RESET}")
    print(f"{COLOR_GREEN}[OK] {target_file}{COLOR_RESET}")


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
        """同步 MCP 配置到 ~/.pi/agent/mcp.json（Pi 全局 MCP 覆盖文件）。

        Pi 官方全局 MCP 路径是 ~/.pi/agent/mcp.json（AGENT_DIR 下），
        home 下 ~/.pi/mcp.json 不是标准加载路径（项目级覆盖是 <cwd>/.pi/mcp.json）。
        """
        pi_agent_dir = Path.home() / ".pi" / "agent"
        pi_agent_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, pi_agent_dir / "mcp.json",
                       "~/.pi/agent/mcp.json", self.force)

    def init_llm(self, source_rules_dir: Path):
        # 生成 ~/.pi/agent/models.json（Pi 的 LLM 提供商/模型列表）
        # 网关启用时生成 agentbuddy-gateway provider（指向 LiteLLM 网关），
        # 否则遍历启用的 llm provider 展开模型
        first = source_rules_dir[0] if isinstance(source_rules_dir, list) else source_rules_dir
        source_dir = first.parent.parent
        env_config = load_split_env_config(source_dir, silent=True)
        generate_pi_models(env_config, Path.home() / ".pi" / "agent" / "models.json",
                           self.force, ide_protocols=self.ide_protocols)

    def init_skills(self, source_skills_dir: Path):
        """同步 skills 到 ~/.pi/skills/。"""
        pi_skills_dir = Path.home() / ".pi" / "skills"
        copy_skills_safe(source_skills_dir, pi_skills_dir, "~/.pi/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, pi_skills_dir / "README.md",
                           "Pi", self.force, self.include_skills)
