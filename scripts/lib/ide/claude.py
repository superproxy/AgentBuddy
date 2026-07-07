"""Claude IDE 分发器。

迁移自 scripts/init-ide.py 的 init_claude() 和 _generate_claude_settings()。
生成 .claude/settings.json（从模板 + llm.yaml 占位符替换）。
"""
import json
from pathlib import Path

from lib.logging import COLOR_YELLOW, COLOR_GREEN, COLOR_RESET
from lib.mcp import copy_dir_safe, copy_file_safe, _resolve_placeholders, _collect_placeholders
from lib.skills import copy_skills_safe, write_skills_index
from lib.llm import load_split_env_config
from .base import IdeTarget


def _generate_claude_settings(template_file: Path, target_file: Path,
                              env_config: dict | None, force: bool) -> None:
    """从模板生成 Claude settings.json，用 llm.yaml 解析占位符。"""
    if not template_file.exists():
        print(f"{COLOR_YELLOW}[!] Claude settings template not found: {template_file}{COLOR_RESET}")
        return

    if target_file.exists():
        if not force:
            print(f"{COLOR_YELLOW}[!] Claude settings.json already exists, use --force to overwrite{COLOR_RESET}")
            return
        target_file.unlink()

    with open(template_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    env_map = {}
    if env_config:
        active_provider = ""
        active_protocols = ["openai"]
        llm_section = env_config.get("llm", {})
        if isinstance(llm_section, dict):
            active_provider = llm_section.get("_active_provider", "")
            raw = llm_section.get("_active_protocol", "openai")
            active_protocols = [p.strip() for p in str(raw).split("|") if p.strip()]
        protocol_env_map = {
            "openai": {"base_url": "OPEN_AI_API_BASE_URL", "api_key": "OPEN_AI_API_KEY", "model": "OPENAI_MODEL"},
            "anthropic": {"base_url": "ANTHROPIC_BASE_URL", "api_key": "ANTHROPIC_AUTH_TOKEN", "model": "ANTHROPIC_MODEL"},
        }
        for provider_name, provider_value in llm_section.items():
            if provider_name.startswith("_"):
                continue
            if not isinstance(provider_value, dict):
                continue
            is_active = provider_name == active_provider
            for protocol_name, protocol_value in provider_value.items():
                if protocol_name.startswith("_"):
                    continue
                if not isinstance(protocol_value, dict):
                    continue
                if is_active and protocol_name in active_protocols:
                    mapping = protocol_env_map.get(protocol_name, {})
                    models_dict = protocol_value.get("models", {})
                    if isinstance(models_dict, dict) and models_dict:
                        default_model = next(iter(models_dict.keys()), "")
                        std_model_key = mapping.get("model")
                        if std_model_key and default_model:
                            env_map[std_model_key] = default_model
                    for k, v in protocol_value.items():
                        if k.startswith("_") or k == "models":
                            continue
                        if not v or not str(v).strip():
                            continue
                        std_key = mapping.get(k)
                        if std_key:
                            env_map[std_key] = str(v)
                        else:
                            env_map[k] = str(v)
        for section_key in ("mcp", "misc"):
            section_value = env_config.get(section_key, {})
            if not isinstance(section_value, dict):
                continue
            for k, v in section_value.items():
                if k.startswith("_"):
                    continue
                if v and str(v).strip():
                    env_map[k] = str(v)

    if env_map:
        config, replaced = _resolve_placeholders(config, env_map)
        if replaced > 0:
            print(f"{COLOR_GREEN}[OK] Resolved {replaced} placeholder(s) in Claude settings{COLOR_RESET}")

    remaining = []
    _collect_placeholders(config, remaining)
    if remaining:
        print(f"{COLOR_YELLOW}[!] Unresolved placeholders in Claude settings: {', '.join(sorted(set(remaining)))}{COLOR_RESET}")

    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"{COLOR_GREEN}[OK] Claude settings generated: {target_file}{COLOR_RESET}")


class ClaudeTarget(IdeTarget):
    name = "Claude"

    def init_rules(self, source_rules: Path):
        claude_rules_dir = self.root / ".claude" / "rules"
        claude_rules_dir.parent.mkdir(parents=True, exist_ok=True)
        if source_rules.exists():
            copy_dir_safe(source_rules, claude_rules_dir, ".claude/rules/", self.force)
        else:
            print(f"{COLOR_YELLOW}[!] Source rules/ not found, skipping{COLOR_RESET}")

    def init_mcp(self, source_mcp_file: Path):
        claude_dir = self.root / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        copy_file_safe(source_mcp_file, claude_dir / "mcp.json",
                       ".claude/mcp.json", self.force)

    def init_llm(self, source_rules_dir: Path):
        # source_rules_dir 是 agents/rules，其 parent.parent 是项目根
        source_dir = source_rules_dir.parent.parent
        # 优先从 config/ide/claude/settings.json 复制（由 generate 生成）
        generated = source_dir / "config" / "ide" / "claude" / "settings.json"
        target = self.root / ".claude" / "settings.json"

        if generated.exists():
            copy_file_safe(generated, target, ".claude/settings.json", self.force)
        else:
            # 回退：直接从模板生成
            claude_settings_template = source_dir / "template" / "ide" / "claude" / "settings.template.json"
            env_config = load_split_env_config(source_dir, silent=True)
            _generate_claude_settings(claude_settings_template, target,
                                      env_config, self.force)

    def init_skills(self, source_skills_dir: Path):
        # 同步到全局目录（~/.claude/skills/）
        claude_skills_dir = Path.home() / ".claude" / "skills"
        copy_skills_safe(source_skills_dir, claude_skills_dir, "~/.claude/skills/",
                         self.force, self.include_skills)
        write_skills_index(source_skills_dir, claude_skills_dir / "README.md",
                           "Claude", self.force, self.include_skills)
