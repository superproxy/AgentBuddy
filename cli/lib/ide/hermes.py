"""Hermes Agent IDE 分发器。

配置目录：
- rules / mcp → 项目 .ade-hermes/（既有路径）
- skills → ~/.ade-hermes/skills/
- llm → ~/.hermes/config.yaml（官方 model + providers，docs/user-guide/configuration.md）

官方 model 段在设置了 base_url 后直接打该端点，不依赖内置厂商鉴权。
"""
from pathlib import Path

from ..logging import COLOR_CYAN, COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from ..mcp import copy_dir_safe, copy_file_safe
from ..llm import load_split_env_config
from ..skills import copy_skills_safe, write_skills_index
from .base import IdeTarget
from .pi import _build_pi_providers, _pick_default


# Pi api 字段 → Hermes model.api_mode
_HERMES_API_MODE = {
    "openai-completions": "chat_completions",
    "openai-responses": "codex_responses",
    "anthropic-messages": "anthropic_messages",
}


def _hermes_providers(pi_providers: dict) -> dict:
    """把 Pi providers 转成 Hermes providers 字典（base_url / api_key / models）。"""
    providers = {}
    for name, cfg in pi_providers.items():
        providers[name] = {
            "base_url": cfg["baseUrl"],
            "api_key": cfg["apiKey"],
            "api_mode": _HERMES_API_MODE.get(cfg.get("api"), "chat_completions"),
            "models": [m["id"] for m in cfg.get("models", [])],
        }
    return providers


def _hermes_model_section(pi_providers: dict, env_config: dict | None) -> dict:
    name, model = _pick_default(pi_providers, env_config)
    cfg = pi_providers[name]
    return {
        "provider": "custom",
        "default": model,
        "base_url": cfg["baseUrl"],
        "api_key": cfg["apiKey"],
        "api_mode": _HERMES_API_MODE.get(cfg.get("api"), "chat_completions"),
    }


def generate_hermes_llm(env_config: dict | None, config_file: Path, force: bool,
                        ide_protocols: list[str] | None = None) -> None:
    """合并写入 ~/.hermes/config.yaml 的 model 与 providers。

    只更新 model 的 provider/default/base_url/api_key/api_mode，以及本次同步的
    providers 项；其余配置（auxiliary、terminal 等）保留。
    """
    if not env_config:
        print(f"{COLOR_YELLOW}[!] llm.yaml not found, skip Hermes config.yaml{COLOR_RESET}")
        return
    if config_file.exists() and not force:
        print(f"{COLOR_YELLOW}[!] {config_file.name} exists, use --force to overwrite{COLOR_RESET}")
        return

    pi_providers = _build_pi_providers(env_config, ide_protocols)
    if not pi_providers:
        print(f"{COLOR_YELLOW}[!] No enabled LLM providers to sync{COLOR_RESET}")
        return

    import yaml

    existing = {}
    if config_file.exists():
        try:
            loaded = yaml.safe_load(config_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, yaml.YAMLError):
            existing = {}

    model = existing.get("model")
    if not isinstance(model, dict):
        model = {}
    model.update(_hermes_model_section(pi_providers, env_config))
    existing["model"] = model

    providers = existing.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    providers.update(_hermes_providers(pi_providers))
    existing["providers"] = providers

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        yaml.safe_dump(existing, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"{COLOR_CYAN}  → model {model.get('default')} @ {model.get('base_url')}{COLOR_RESET}")
    print(f"{COLOR_GREEN}[OK] {config_file}{COLOR_RESET}")


class HermesTarget(IdeTarget):
    name = "Hermes"

    def init_rules(self, source_rules: Path):
        rules_dir = self.root / ".ade-hermes" / "rules"
        rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, rules_dir, ".ade-hermes/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        hermes_dir = self.root / ".ade-hermes"
        hermes_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, hermes_dir / "mcp.json", ".ade-hermes/mcp.json", self.force)

    def init_llm(self, source_rules_dir: Path):
        """同步 LLM 到 ~/.hermes/config.yaml（官方 model + providers）。"""
        first = source_rules_dir[0] if isinstance(source_rules_dir, list) else source_rules_dir
        source_dir = first.parent.parent
        env_config = load_split_env_config(source_dir, silent=True)
        generate_hermes_llm(
            env_config,
            Path.home() / ".hermes" / "config.yaml",
            self.force,
            ide_protocols=self.ide_protocols,
        )

    def init_skills(self, source_skills_dir: Path):
        skills_dir = Path.home() / ".ade-hermes" / "skills"
        copy_skills_safe(source_skills_dir, skills_dir, "~/.ade-hermes/skills/",
                         self.force, self.include_skills, link=self.link_skills)
        write_skills_index(source_skills_dir, skills_dir / "README.md",
                           "Hermes", self.force, self.include_skills)
