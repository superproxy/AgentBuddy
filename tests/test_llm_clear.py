# -*- coding: utf-8 -*-
"""LLM：只同步勾选的 IDE；按当前设定清空原配置文件中的 LLM 设置。"""

from __future__ import annotations

import json
from pathlib import Path

from agentctl.lib.ide.clear_llm import clear_llm_for_ide, clear_llm_for_ides


def test_clear_claude_strips_llm_env_keeps_other_settings(tmp_path: Path):
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({
            "env": {"ANTHROPIC_API_KEY": "x", "OPEN_AI_API_KEY": "y", "MY_CUSTOM": "keep"},
            "permissions": {"allow": ["Bash"]},
        })
        + "\n",
        encoding="utf-8",
    )
    result = clear_llm_for_ide(tmp_path / "proj", "Claude", home=tmp_path / "home")
    assert result["skipped"] is False
    assert settings.exists()
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["permissions"] == {"allow": ["Bash"]}
    assert data["env"] == {"MY_CUSTOM": "keep"}
    assert "ANTHROPIC_API_KEY" not in data["env"]
    assert result["cleared"]


def test_clear_codex_keeps_mcp_and_strips_models(tmp_path: Path):
    home = tmp_path / "home"
    path = home / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join([
            'model = "gpt-5.4"',
            'review_model = "gpt-5.4"',
            'model_provider = "agentbuddy-gateway"',
            "network_access = true",
            "",
            "[model_providers.gw]",
            'name = "gw"',
            "",
            "[mcp_servers.fs]",
            'command = "npx"',
            "",
        ]),
        encoding="utf-8",
    )
    result = clear_llm_for_ide(tmp_path / "proj", "Codex", home=home)
    assert result["skipped"] is False
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "mcp_servers" in text or "command" in text
    assert "gpt-5.4" not in text
    assert "model_providers" not in text
    assert "network_access" in text
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    data = tomllib.loads(text)
    assert "fs" in (data.get("mcp_servers") or {})
    assert "model" not in data
    assert "model_providers" not in data


def test_clear_opencode_keeps_mcp(tmp_path: Path):
    home = tmp_path / "home"
    path = home / ".config" / "opencode" / "opencode.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"$schema": "s", "model": "gw/a", "provider": {"gw": {}}, "mcp": {"fs": {"command": "npx"}}, "permission": {}}\n',
        encoding="utf-8",
    )
    result = clear_llm_for_ide(tmp_path / "proj", "OpenCode", home=home)
    assert result["skipped"] is False
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "model" not in data
    assert "provider" not in data
    assert data["mcp"]["fs"]["command"] == "npx"
    assert data["permission"] == {}
    assert data["$schema"] == "s"


def test_clear_workbuddy_deletes_models_json(tmp_path: Path):
    home = tmp_path / "home"
    path = home / ".workbuddy" / "models.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"models": []}\n', encoding="utf-8")
    result = clear_llm_for_ide(tmp_path / "proj", "WorkBuddy", home=home)
    assert not path.exists()
    assert result["cleared"]


def test_clear_cursor_is_skipped(tmp_path: Path):
    result = clear_llm_for_ide(tmp_path / "proj", "Cursor", home=tmp_path / "home")
    assert result["skipped"] is True
    assert result["cleared"] == []


def test_clear_pi_deletes_models_and_strips_defaults(tmp_path: Path):
    home = tmp_path / "home"
    agent = home / ".pi" / "agent"
    agent.mkdir(parents=True)
    models = agent / "models.json"
    settings = agent / "settings.json"
    models.write_text('{"providers": {"deepseek": {}}}\n', encoding="utf-8")
    settings.write_text(
        json.dumps({
            "theme": "dark",
            "defaultProvider": "deepseek",
            "defaultModel": "deepseek-v4",
            "packages": ["npm:pi-plan"],
        }),
        encoding="utf-8",
    )
    result = clear_llm_for_ide(tmp_path / "proj", "Pi", home=home)
    assert result["skipped"] is False
    assert not models.exists()
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert data["packages"] == ["npm:pi-plan"]
    assert "defaultProvider" not in data
    assert "defaultModel" not in data


def test_clear_openworker_removes_synced_profiles_keeps_others(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    state = home / ".config" / "coworker"
    state.mkdir(parents=True)
    secrets = state / "secrets.json"
    config = state / "config.toml"
    secrets.write_text(
        json.dumps({
            "provider:openai": {"type": "openaiv1", "api_key": "sk-old", "model": "old"},
            "provider:anthropic": {"type": "anthropic", "api_key": "sk-a"},
            "provider:manual": {"api_key": "keep-me"},
        }),
        encoding="utf-8",
    )
    config.write_text('theme = "dark"\nmodel = "old-model"\nverbose = true\n', encoding="utf-8")
    result = clear_llm_for_ide(tmp_path / "proj", "OpenWorker", home=home)
    assert result["skipped"] is False
    data = json.loads(secrets.read_text(encoding="utf-8"))
    assert "provider:openai" not in data
    assert "provider:anthropic" not in data
    assert data["provider:manual"]["api_key"] == "keep-me"
    text = config.read_text(encoding="utf-8")
    assert "old-model" not in text
    assert "theme" in text
    assert "verbose" in text


def test_clear_deepseek_strips_providers_keeps_other_settings(tmp_path: Path, monkeypatch):
    dsh = tmp_path / "dsh"
    monkeypatch.setenv("DSH_HOME", str(dsh))
    dsh.mkdir(parents=True)
    settings = dsh / "settings.yaml"
    creds = dsh / ".credentials.yaml"
    settings.write_text(
        "\n".join([
            "other: kept",
            "llm-pi-ai:",
            "  providers:",
            "    deepseek:",
            "      apiKeyEnv: DEEPSEEK_API_KEY",
            "      api: openai-completions",
            "    stale:",
            "      apiKeyEnv: STALE_API_KEY",
        ])
        + "\n",
        encoding="utf-8",
    )
    creds.write_text(
        "DEEPSEEK_API_KEY: sk-ds\nSTALE_API_KEY: sk-old\nOTHER_KEY: keep\n",
        encoding="utf-8",
    )
    result = clear_llm_for_ide(tmp_path / "proj", "DeepSeek", home=tmp_path / "home")
    assert result["skipped"] is False
    import yaml
    data = yaml.safe_load(settings.read_text(encoding="utf-8"))
    assert data["other"] == "kept"
    assert "llm-pi-ai" not in data or "providers" not in (data.get("llm-pi-ai") or {})
    cred = yaml.safe_load(creds.read_text(encoding="utf-8"))
    assert "DEEPSEEK_API_KEY" not in cred
    assert "STALE_API_KEY" not in cred
    assert cred["OTHER_KEY"] == "keep"


def test_clear_hermes_strips_model_and_providers_keeps_other(tmp_path: Path):
    home = tmp_path / "home"
    path = home / ".hermes" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join([
            "terminal:",
            "  backend: local",
            "model:",
            "  provider: custom",
            "  default: old",
            "  base_url: https://old.example",
            "  api_key: sk-old",
            "  api_mode: chat_completions",
            "providers:",
            "  volcengine:",
            "    api_key: sk-old",
            "    models: [old]",
            "  stale:",
            "    api_key: leftover",
        ])
        + "\n",
        encoding="utf-8",
    )
    result = clear_llm_for_ide(tmp_path / "proj", "Hermes", home=home)
    assert result["skipped"] is False
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["terminal"]["backend"] == "local"
    assert "providers" not in data
    assert "model" not in data


def test_clear_zcode_removes_custom_providers_keeps_others(tmp_path: Path):
    home = tmp_path / "home"
    path = home / ".zcode" / "v2" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "theme": "dark",
            "provider": {
                "custom:deepseek-openaiv1": {"name": "ds", "source": "custom"},
                "custom:old-openai": {"name": "stale", "source": "custom"},
                "builtin": {"name": "keep"},
            },
        }),
        encoding="utf-8",
    )
    result = clear_llm_for_ide(tmp_path / "proj", "ZCode", home=home)
    assert result["skipped"] is False
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert "custom:deepseek-openaiv1" not in data["provider"]
    assert "custom:old-openai" not in data["provider"]
    assert data["provider"]["builtin"]["name"] == "keep"


def test_clear_multiple_ides(tmp_path: Path):
    payload = clear_llm_for_ides(tmp_path / "proj", ["Cursor", "Claude"], home=tmp_path / "home")
    assert payload["ok"] is True
    assert payload["count"] == 2
