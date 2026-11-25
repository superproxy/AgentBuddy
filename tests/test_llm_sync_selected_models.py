"""同步时只应把当前选中（启用）的模型写入目标 IDE 配置。"""

import json

import yaml


def _env_with_mixed_models():
    return {
        "llm": {
            "_active_provider": "openicu",
            "_active_model": "kept-a",
            "openicu": {
                "_enabled": True,
                "openaiv1": {
                    "base_url": "https://openicu.example/v1",
                    "api_key": "sk-openicu",
                    "models": {
                        "kept-a": {"name": "Kept A", "_enabled": True},
                        "kept-b": {"name": "Kept B"},
                        "off": {"name": "Off", "_enabled": False},
                        "~legacy": {"name": "Legacy"},
                    },
                },
            },
            "disabled_p": {
                "_enabled": False,
                "openaiv1": {
                    "base_url": "https://disabled.example/v1",
                    "api_key": "sk-disabled",
                    "models": {"should-not-appear": {"name": "No"}},
                },
            },
        },
        "proxy": {"gateway": {"enabled": False}},
    }


ENABLED_IDS = ["kept-a", "kept-b"]
EXCLUDED_IDS = ["off", "~legacy", "should-not-appear", "old-stale"]


def test_workbuddy_writes_only_enabled_models(tmp_path):
    from agentctl.lib.ide.workbuddy import generate_workbuddy_models

    target = tmp_path / "models.json"
    target.write_text(
        json.dumps({"models": [{"id": "old-stale", "name": "Stale"}]}),
        encoding="utf-8",
    )
    generate_workbuddy_models(_env_with_mixed_models(), target, force=True)
    data = json.loads(target.read_text(encoding="utf-8"))
    ids = [item["id"] for item in data["models"]]
    assert ids == ENABLED_IDS
    for mid in EXCLUDED_IDS:
        assert mid not in ids


def test_codebuddy_writes_only_enabled_models(tmp_path):
    from agentctl.lib.ide.codebuddy import generate_codebuddy_models

    target = tmp_path / "models.json"
    generate_codebuddy_models(_env_with_mixed_models(), target, force=True)
    data = json.loads(target.read_text(encoding="utf-8"))
    ids = [item["id"] for item in data["models"]]
    assert ids == ENABLED_IDS
    for mid in EXCLUDED_IDS:
        assert mid not in ids


def test_deepseek_build_providers_includes_only_enabled_models():
    from agentctl.lib.ide.deepseek import _build_pi_ai_providers

    providers, _credentials = _build_pi_ai_providers(_env_with_mixed_models())
    assert set(providers) == {"openicu"}
    ids = [item["id"] for item in providers["openicu"]["models"]]
    assert ids == ENABLED_IDS
    for mid in EXCLUDED_IDS:
        assert mid not in ids


def test_zcode_force_writes_only_enabled_models(tmp_path, monkeypatch):
    from agentctl.lib.ide import zcode as zcode_mod
    from agentctl.lib.ide.zcode import ZCodeTarget

    home = tmp_path / "home"
    v2 = home / ".zcode" / "v2"
    v2.mkdir(parents=True)
    (v2 / "config.json").write_text(
        json.dumps({
            "provider": {
                "custom:openicu-openaiv1": {
                    "models": {"old-stale": {"name": "Stale"}},
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(zcode_mod.Path, "home", staticmethod(lambda: home))

    proj = tmp_path / "proj"
    llm_dir = proj / "config" / "llm"
    llm_dir.mkdir(parents=True)
    llm_dir.joinpath("llm.yaml").write_text(
        yaml.safe_dump(_env_with_mixed_models(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    ZCodeTarget(proj, force=True).init_llm([proj / "config" / "rules"])
    data = json.loads((v2 / "config.json").read_text(encoding="utf-8"))
    models = data["provider"]["custom:openicu-openaiv1"]["models"]
    assert set(models) == set(ENABLED_IDS)
    for mid in EXCLUDED_IDS:
        assert mid not in models


def test_cherrystudio_writes_only_enabled_models(tmp_path):
    from agentctl.lib.ide.cherrystudio import CherryStudioTarget

    proj = tmp_path / "proj"
    llm_dir = proj / "config" / "llm"
    llm_dir.mkdir(parents=True)
    llm_dir.joinpath("llm.yaml").write_text(
        yaml.safe_dump(_env_with_mixed_models(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    CherryStudioTarget(proj, force=True).init_llm([proj / "config" / "rules"])
    out = proj / "config" / "ide" / "cherrystudio" / "providers.json"
    providers = json.loads(out.read_text(encoding="utf-8"))
    assert len(providers) == 1
    ids = [item["id"] for item in providers[0]["models"]]
    assert ids == ENABLED_IDS
    for mid in EXCLUDED_IDS:
        assert mid not in ids


def test_openworker_first_model_skips_disabled_and_tilde():
    from agentctl.lib.ide.openworker import _first_model

    models = {
        "off": {"name": "Off", "_enabled": False},
        "~legacy": {"name": "Legacy"},
        "kept-a": {"name": "Kept A", "_enabled": True},
    }
    assert _first_model(models) == "kept-a"


def test_openworker_sync_default_model_skips_disabled(tmp_path, monkeypatch):
    from agentctl.lib.ide.openworker import OpenWorkerTarget

    state = tmp_path / "coworker"
    monkeypatch.setenv("COWORKER_STATE_DIR", str(state))
    env = {
        "llm": {
            "openicu": {
                "_enabled": True,
                "openaiv1": {
                    "base_url": "https://openicu.example/v1",
                    "api_key": "sk-openicu",
                    "models": {
                        "off": {"name": "Off", "_enabled": False},
                        "kept-a": {"name": "Kept A"},
                    },
                },
            },
        },
    }
    monkeypatch.setattr(
        "agentctl.lib.llm.load_split_env_config",
        lambda *args, **kwargs: env,
    )
    OpenWorkerTarget(tmp_path, force=True).init_llm([tmp_path / "config" / "rules"])
    secrets = json.loads((state / "secrets.json").read_text(encoding="utf-8"))
    assert secrets["provider:openai"]["model"] == "kept-a"
