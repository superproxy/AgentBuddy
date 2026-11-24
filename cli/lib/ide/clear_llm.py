# -*- coding: utf-8 -*-
"""清除飞翼同步到各 AIDE 的 LLM 设置。

按当前勾选的 AIDE，在「原来的配置文件」里把飞翼写入的 LLM 配置真正清掉，
而不是只追加新键、留下旧值。不动 MCP / Skills，不改本机 llm.yaml，
不删除 Codex auth.json。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


# Codex config.toml 中由飞翼 init_llm / convert_to_codex 写入的键
_CODEX_LLM_KEYS = {
    "model",
    "review_model",
    "model_provider",
    "model_providers",
    "model_reasoning_effort",
}

# OpenCode opencode.json 中由飞翼写入的 LLM 字段
_OPENCODE_LLM_KEYS = {"provider", "providers", "model", "small_model"}

# Claude settings.json env 中由模板占位符注入的 LLM 键
_CLAUDE_ENV_KEYS = {
    "OPEN_AI_API_BASE_URL",
    "OPEN_AI_API_KEY",
    "OPENAI_MODEL",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
}

# OpenWorker secrets.json 中由飞翼写入的 profile 槽位
_OPENWORKER_PROFILE_KEYS = ("provider:openai", "provider:anthropic")

# Hermes config.yaml 的 model 段里由飞翼写入的字段
_HERMES_MODEL_KEYS = ("provider", "default", "base_url", "api_key", "api_mode")


def _rel(path: Path) -> str:
    return str(path)


def _delete_file(path: Path) -> Optional[str]:
    try:
        if path.is_file():
            path.unlink()
            return _rel(path)
    except OSError:
        return None
    return None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_yaml(path: Path) -> dict:
    import yaml
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _write_yaml(path: Path, data: dict) -> None:
    import yaml
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _load_toml(path: Path) -> dict:
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[ " + ", ".join(_toml_value(v) for v in value) + " ]"
    if value is None:
        return '""'
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped + '"'


def _dump_toml(data: dict) -> str:
    try:
        import tomli_w
        return tomli_w.dumps(data)
    except Exception:
        pass
    lines: list[str] = []

    def emit_table(header: str, obj: dict) -> None:
        scalars: list[tuple[str, Any]] = []
        tables: list[tuple[str, dict]] = []
        for key, val in obj.items():
            if isinstance(val, dict):
                tables.append((key, val))
            else:
                scalars.append((key, val))
        if header:
            lines.append("[" + header + "]")
        for key, val in scalars:
            lines.append(key + " = " + _toml_value(val))
        for key, val in tables:
            if lines and lines[-1] != "":
                lines.append("")
            child = (header + "." + key) if header else key
            emit_table(child, val)

    top_scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    top_tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    for key, val in top_scalars.items():
        lines.append(key + " = " + _toml_value(val))
    for key, val in top_tables.items():
        if lines and lines[-1] != "":
            lines.append("")
        emit_table(key, val)
    return "\n".join(lines).rstrip() + "\n"


def _is_claude_llm_env_key(key: str) -> bool:
    upper = str(key).upper()
    if upper in _CLAUDE_ENV_KEYS:
        return True
    return (
        upper.startswith("LLM_")
        or upper.startswith("ANTHROPIC_")
        or upper.startswith("OPEN_AI_")
        or upper.startswith("OPENAI_")
    )


def _strip_json_keys(path: Path, keys: set[str]) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        data = _load_json(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    removed = False
    for key in list(data.keys()):
        if key in keys:
            del data[key]
            removed = True
    if not removed:
        return None
    if not data:
        return _delete_file(path)
    _write_json(path, data)
    return _rel(path)


def _strip_claude_settings(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        data = _load_json(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    removed = False
    env = data.get("env")
    if isinstance(env, dict):
        for key in list(env.keys()):
            if _is_claude_llm_env_key(key):
                del env[key]
                removed = True
        if not env:
            del data["env"]
    if "model" in data and not isinstance(data.get("model"), dict):
        del data["model"]
        removed = True
    if not removed:
        return None
    if not data:
        return _delete_file(path)
    _write_json(path, data)
    return _rel(path)


def _strip_codex_toml(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    data = _load_toml(path)
    removed = False
    for key in list(data.keys()):
        if key in _CODEX_LLM_KEYS:
            del data[key]
            removed = True
    if not removed:
        return None
    if not data:
        return _delete_file(path)
    path.write_text(_dump_toml(data), encoding="utf-8")
    return _rel(path)


def _strip_opencode_json(path: Path) -> Optional[str]:
    return _strip_json_keys(path, _OPENCODE_LLM_KEYS)


def _strip_pi_settings(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        data = _load_json(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    removed = False
    for key in ("defaultProvider", "defaultModel"):
        if key in data:
            del data[key]
            removed = True
    if not removed:
        return None
    if not data:
        return _delete_file(path)
    _write_json(path, data)
    return _rel(path)


def _strip_openworker_secrets(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        data = _load_json(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    removed = False
    for key in _OPENWORKER_PROFILE_KEYS:
        if key in data:
            del data[key]
            removed = True
    if not removed:
        return None
    if not data:
        return _delete_file(path)
    _write_json(path, data)
    return _rel(path)


def _strip_openworker_model(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    import re
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    kept = [line for line in lines if not re.match(r"^\s*model\s*=", line)]
    if len(kept) == len(lines):
        return None
    new = "\n".join(kept).rstrip()
    if not new:
        return _delete_file(path)
    path.write_text(new + "\n", encoding="utf-8")
    return _rel(path)


def _strip_deepseek_llm(settings_file: Path, cred_file: Path) -> list[str]:
    cleared: list[str] = []
    env_vars: list[str] = []
    if settings_file.is_file():
        try:
            data = _load_yaml(settings_file)
        except Exception:
            data = None
        if isinstance(data, dict) and "llm-pi-ai" in data:
            section = data.get("llm-pi-ai")
            if isinstance(section, dict):
                providers = section.get("providers")
                if isinstance(providers, dict):
                    for profile in providers.values():
                        if isinstance(profile, dict):
                            env_name = profile.get("apiKeyEnv")
                            if env_name:
                                env_vars.append(str(env_name))
                if "providers" in section:
                    del section["providers"]
                    if section:
                        data["llm-pi-ai"] = section
                    else:
                        del data["llm-pi-ai"]
                    if data:
                        _write_yaml(settings_file, data)
                    else:
                        _delete_file(settings_file)
                    cleared.append(_rel(settings_file))
    if cred_file.is_file() and env_vars:
        try:
            creds = _load_yaml(cred_file)
        except Exception:
            creds = None
        if isinstance(creds, dict):
            removed = False
            for key in env_vars:
                if key in creds:
                    del creds[key]
                    removed = True
            if removed:
                if creds:
                    _write_yaml(cred_file, creds)
                else:
                    _delete_file(cred_file)
                cleared.append(_rel(cred_file))
    return cleared


def _strip_hermes_config(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        data = _load_yaml(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    removed = False
    model = data.get("model")
    if isinstance(model, dict):
        for key in _HERMES_MODEL_KEYS:
            if key in model:
                del model[key]
                removed = True
        if not model:
            del data["model"]
    elif "model" in data:
        del data["model"]
        removed = True
    if "providers" in data:
        del data["providers"]
        removed = True
    if not removed:
        return None
    if not data:
        return _delete_file(path)
    _write_yaml(path, data)
    return _rel(path)


def _strip_zcode_providers(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        data = _load_json(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    providers = data.get("provider")
    if not isinstance(providers, dict):
        return None
    removed = False
    for key in list(providers.keys()):
        if str(key).startswith("custom:"):
            del providers[key]
            removed = True
    if not removed:
        return None
    data["provider"] = providers
    _write_json(path, data)
    return _rel(path)


def _coworker_dir(home: Path, home_overridden: bool) -> Path:
    env = os.environ.get("COWORKER_STATE_DIR")
    if env:
        return Path(env)
    if home_overridden:
        return Path(home) / ".config" / "coworker"
    from agentctl.lib.ide.openworker import openworker_state_dir
    return openworker_state_dir()


def _dsh_dir(home: Path) -> Path:
    env = os.environ.get("DSH_HOME")
    if env:
        return Path(env)
    return Path(home) / ".dsh"


_NO_LLM_WRITE_IDES = {
    "Cursor", "Cline", "Copilot", "KimiCode", "KimiCLI", "KimiWork",
    "Trae", "TraeCN", "TraeSoloCN", "Qoder", "QoderCN", "OpenClaw",
    "IDEA", "VSCode", "CommandCode", "Agents",
}


def clear_llm_for_ide(
    project_root: Path,
    ide_key: str,
    *,
    home: Optional[Path] = None,
) -> dict[str, Any]:
    """按当前设定，清除某个 AIDE 配置文件里已同步的 LLM 内容。

    返回 {key, cleared: [path], skipped: bool, hint?: str}。
    """
    project_root = Path(project_root)
    home_overridden = home is not None
    home = Path(home) if home else Path.home()
    cleared: list[str] = []

    def add(path_or_none: Optional[str]) -> None:
        if path_or_none:
            cleared.append(path_or_none)

    if ide_key == "Claude":
        add(_strip_claude_settings(project_root / ".claude" / "settings.json"))
    elif ide_key == "Codex":
        add(_strip_codex_toml(project_root / ".codex" / "config.toml"))
        add(_strip_codex_toml(home / ".codex" / "config.toml"))
    elif ide_key == "OpenCode":
        add(_strip_opencode_json(home / ".config" / "opencode" / "opencode.json"))
    elif ide_key == "WorkBuddy":
        add(_delete_file(home / ".workbuddy" / "models.json"))
    elif ide_key == "CodeBuddy":
        add(_delete_file(home / ".codebuddy" / "models.json"))
    elif ide_key == "CherryStudio":
        add(_delete_file(project_root / "config" / "ide" / "cherrystudio" / "providers.json"))
    elif ide_key == "Pi":
        pi_agent = home / ".pi" / "agent"
        add(_delete_file(pi_agent / "models.json"))
        add(_strip_pi_settings(pi_agent / "settings.json"))
    elif ide_key == "OpenWorker":
        base = _coworker_dir(home, home_overridden)
        add(_strip_openworker_secrets(base / "secrets.json"))
        add(_strip_openworker_model(base / "config.toml"))
    elif ide_key == "DeepSeek":
        dsh = _dsh_dir(home)
        cleared.extend(_strip_deepseek_llm(dsh / "settings.yaml", dsh / ".credentials.yaml"))
    elif ide_key == "Hermes":
        add(_strip_hermes_config(home / ".hermes" / "config.yaml"))
    elif ide_key == "ZCode":
        add(_strip_zcode_providers(home / ".zcode" / "v2" / "config.json"))
    elif ide_key in _NO_LLM_WRITE_IDES:
        return {
            "key": ide_key,
            "cleared": [],
            "skipped": True,
            "hint": "该 AIDE 的模型不由飞翼写入本地 LLM 配置，无需清除",
        }
    else:
        return {
            "key": ide_key,
            "cleared": [],
            "skipped": True,
            "hint": "暂不自动清除该 AIDE 中可能与用户自己的配置混在一起的 LLM 文件",
        }

    return {"key": ide_key, "cleared": cleared, "skipped": False}


def clear_llm_for_ides(
    project_root: Path,
    ide_keys: list[str],
    *,
    home: Optional[Path] = None,
) -> dict[str, Any]:
    results = [clear_llm_for_ide(project_root, key, home=home) for key in ide_keys]
    cleared_count = sum(len(r.get("cleared") or []) for r in results)
    return {"ok": True, "ides": results, "cleared_count": cleared_count, "count": len(results)}
