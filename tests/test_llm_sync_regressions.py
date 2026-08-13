"""LLM generate/sync regression tests for OpenCode and OpenWorker."""

import argparse
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("agentctl_under_test", SCRIPTS / "agentctl.py")
agentctl = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(agentctl)

from lib.ide.openworker import OpenWorkerTarget, openworker_state_dir


def _sync_args(ide="OpenCode"):
    return argparse.Namespace(
        ide=ide,
        force=True,
        scope="llm,mcp",
        skills=None,
    )


def test_sync_regenerates_all_ide_outputs_before_copying(tmp_path):
    target = Mock(name="OpenCodeTarget")
    target.name = "OpenCode"
    target.run.return_value = None
    llm_file = tmp_path / "config" / "llm" / "llm.yaml"
    llm_file.parent.mkdir(parents=True)
    llm_file.write_text("llm: {}\n", encoding="utf-8")

    with (
        patch.object(agentctl, "PROJECT_ROOT", tmp_path),
        patch.object(agentctl, "cmd_generate") as generate,
        patch.object(agentctl, "get_ide", return_value=[target]),
        patch.object(agentctl.llm, "load_split_env_config", return_value={}),
    ):
        result = agentctl.cmd_sync(_sync_args())

    assert result is True
    generate.assert_called_once()
    assert target.run.call_count >= 1


def test_sync_returns_false_when_any_ide_fails(tmp_path):
    target = Mock(name="OpenWorkerTarget")
    target.name = "OpenWorker"
    target.run.side_effect = RuntimeError("write failed")

    with (
        patch.object(agentctl, "PROJECT_ROOT", tmp_path),
        patch.object(agentctl, "cmd_generate"),
        patch.object(agentctl, "get_ide", return_value=[target]),
        patch.object(agentctl.llm, "load_split_env_config", return_value={}),
    ):
        result = agentctl.cmd_sync(_sync_args("OpenWorker"))

    assert result is False


def test_codex_claude_llm_sync_requires_exactly_one_default_source_and_model():
    codex = types.SimpleNamespace(name="Codex")
    claude = types.SimpleNamespace(name="Claude")

    assert "只能选择一个" in agentctl._validate_default_llm_selection({}, [codex])
    assert "只能选择一个" in agentctl._validate_default_llm_selection(
        {
            "llm": {"_active_provider": "openai", "_active_model": "gpt-5"},
            "proxy": {"gateway": {"enabled": True}},
        },
        [claude],
    )
    assert "默认模型" in agentctl._validate_default_llm_selection(
        {"llm": {"_active_provider": "openai", "openai": {"_enabled": True}}},
        [codex],
    )
    assert "不存在或未启用" in agentctl._validate_default_llm_selection(
        {
            "llm": {
                "_active_provider": "openai",
                "_active_model": "gpt-5",
                "openai": {"_enabled": False},
            }
        },
        [codex],
    )


def test_codex_claude_llm_sync_accepts_provider_or_gateway_selection():
    targets = [types.SimpleNamespace(name="Codex"), types.SimpleNamespace(name="Claude")]
    provider_config = {
        "llm": {
            "_active_provider": "openai",
            "_active_model": "gpt-5",
            "openai": {"_enabled": True},
        }
    }
    gateway_config = {
        "llm": {"_active_provider": "", "_active_model": "gpt-5"},
        "proxy": {"gateway": {"enabled": True}},
    }

    assert agentctl._validate_default_llm_selection(provider_config, targets) is None
    assert agentctl._validate_default_llm_selection(gateway_config, targets) is None
    assert agentctl._validate_default_llm_selection({}, [types.SimpleNamespace(name="OpenCode")]) is None


def test_llm_only_sync_does_not_append_agents_target(monkeypatch):
    class Target:
        name = "OpenCode"

        def run(self, *_args):
            return self.name

    requested = []

    def fake_get_ide(name, **_kwargs):
        requested.append(name)
        return [Target()]

    monkeypatch.setattr(agentctl, "get_ide", fake_get_ide)
    monkeypatch.setattr(agentctl.llm, "load_split_env_config", lambda *_args, **_kwargs: {
        "llm": {}, "proxy": {"gateway": {"enabled": False}},
    })
    monkeypatch.setattr(agentctl, "cmd_generate", lambda _args: None)
    monkeypatch.setattr(agentctl.Path, "exists", lambda _self: True)

    args = _sync_args()
    args.scope = "llm"
    assert agentctl.cmd_sync(args) is True
    assert requested == ["OpenCode"]


def test_opencode_injection_syncs_all_enabled_providers_by_name(tmp_path):
    from lib.llm import inject_opencode_native_providers

    target = tmp_path / "opencode.json"
    target.write_text(json.dumps({"provider": {"stale": {}}}), encoding="utf-8")
    env_config = {
        "llm": {
            "_active_provider": "openicu",
            "_active_protocol": "responses",
            "_active_model": "openai/gpt-5.4",
            "openicu": {
                "_enabled": True,
                "responses": {
                    "base_url": "https://openicu.example/v1",
                    "api_key": "openicu-key",
                    "models": {
                        "openai/gpt-5.4": {"name": "GPT 5.4", "_enabled": True},
                        "disabled": {"name": "Disabled", "_enabled": False},
                    },
                },
            },
            "deepseek": {
                "_enabled": True,
                "openaiv1": {
                    "base_url": "https://deepseek.example/v1",
                    "api_key": "deepseek-key",
                    "models": {"deepseek-chat": {"name": "DeepSeek Chat"}},
                },
            },
            "dual": {
                "_enabled": True,
                "responses": {
                    "base_url": "https://dual.example/openai",
                    "api_key": "dual-openai-key",
                    "models": {"dual-openai": {}},
                },
                "anthropic": {
                    "base_url": "https://dual.example/anthropic",
                    "api_key": "dual-anthropic-key",
                    "models": {"dual-claude": {}},
                },
            },
            "disabled": {
                "_enabled": False,
                "openaiv1": {
                    "base_url": "https://disabled.example/v1",
                    "api_key": "disabled-key",
                    "models": {"disabled-model": {}},
                },
            },
        },
        "proxy": {"gateway": {"enabled": False}},
    }

    inject_opencode_native_providers(target, env_config, "openicu", ["responses"])

    generated = json.loads(target.read_text(encoding="utf-8"))
    assert set(generated["provider"]) == {"openicu", "deepseek", "dual", "dual-anthropic"}
    assert generated["provider"]["openicu"]["npm"] == "@ai-sdk/openai"
    assert generated["provider"]["deepseek"]["npm"] == "@ai-sdk/openai-compatible"
    assert generated["provider"]["dual-anthropic"]["npm"] == "@ai-sdk/anthropic"
    assert set(generated["provider"]["openicu"]["models"]) == {"openai/gpt-5.4"}
    assert generated["model"] == "openicu/openai/gpt-5.4"


def test_openworker_state_dir_honors_environment_override(tmp_path):
    custom_dir = tmp_path / "custom-coworker"
    with patch.dict(os.environ, {"COWORKER_STATE_DIR": str(custom_dir)}):
        state_dir = openworker_state_dir()
        target = OpenWorkerTarget(tmp_path)

    assert state_dir == custom_dir
    assert target.base == custom_dir
    assert target.secrets_file == custom_dir / "secrets.json"
    assert target.config_file == custom_dir / "config.toml"


@pytest.mark.parametrize(
    ("platform", "env", "expected"),
    [
        ("darwin", {}, Path.home() / ".config" / "coworker"),
        ("linux", {}, Path.home() / ".config" / "coworker"),
        ("win32", {"APPDATA": "C:/Users/test/AppData/Roaming"}, Path("C:/Users/test/AppData/Roaming/coworker")),
    ],
)
def test_openworker_default_state_dir_is_platform_specific(platform, env, expected):
    clean_env = {"COWORKER_STATE_DIR": "", "APPDATA": env.get("APPDATA", "")}
    with patch.dict(os.environ, clean_env, clear=False), patch("sys.platform", platform):
        state_dir = openworker_state_dir()

    assert state_dir == expected
