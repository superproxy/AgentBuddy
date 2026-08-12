"""LLM generate/sync regression tests for OpenCode and OpenWorker."""

import argparse
import importlib.util
import os
import sys
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
