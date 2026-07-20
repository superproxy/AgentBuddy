"""llm.yaml 中的 ${VAR} 占位符应被批量解析。

覆盖场景：
- llm.yaml 字段值含 ${VAR}，生成 flat_config 时应解析为实际值
- 解析优先级：OS env > keys.yaml > 保留字面
- ${VAR:-default} 默认值语法
- 批量：一个 llm.yaml 里多个字段都引用变量时全部被解析
"""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib import llm as llm_mod


class FlattenEnvConfigPlaceholderTests(unittest.TestCase):
    """flatten_env_config 应对返回的 flat 里所有字符串值应用 ${VAR} 解析。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = pathlib.Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_llm(self, content: str):
        llm_dir = self.project_root / "config" / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)
        (llm_dir / "llm.yaml").write_text(content, encoding="utf-8")

    def _write_keys(self, keys: dict):
        mcp_dir = self.project_root / "config" / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        import yaml
        (mcp_dir / "keys.yaml").write_text(
            yaml.safe_dump({"mcp": keys}, allow_unicode=True),
            encoding="utf-8",
        )

    def test_llm_field_resolves_from_os_env(self):
        """llm.yaml 中 api_key: ${MY_TEST_SECRET} 应从 OS env 解析。"""
        self._write_llm(
            "llm:\n  openai:\n    enable: true\n    api_key: ${MY_TEST_SECRET}\n"
        )
        with mock.patch.dict(os.environ, {"MY_TEST_SECRET": "sk-real-from-os"}, clear=False):
            env = llm_mod.load_split_env_config(self.project_root, silent=True)
            flat = llm_mod.flatten_env_config(env, "openai", ["openai"])
        self.assertEqual(flat.get("OPEN_AI_API_KEY"), "sk-real-from-os")

    def test_llm_field_resolves_from_keys_yaml_when_no_os_env(self):
        """OS env 没有时，从 keys.yaml 解析。"""
        self._write_llm(
            "llm:\n  openai:\n    enable: true\n    api_key: ${MY_TEST_SECRET}\n"
        )
        self._write_keys({"MY_TEST_SECRET": "sk-from-keys-yaml"})
        with mock.patch.dict(os.environ, {}, clear=True):
            env = llm_mod.load_split_env_config(self.project_root, silent=True)
            flat = llm_mod.flatten_env_config(env, "openai", ["openai"])
        self.assertEqual(flat.get("OPEN_AI_API_KEY"), "sk-from-keys-yaml")

    def test_llm_field_default_value_syntax(self):
        """${VAR:-default} 默认值语法。"""
        self._write_llm(
            "llm:\n  openai:\n    enable: true\n    base_url: ${MY_BASE:-https://default.example.com}\n"
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            env = llm_mod.load_split_env_config(self.project_root, silent=True)
            flat = llm_mod.flatten_env_config(env, "openai", ["openai"])
        self.assertEqual(flat.get("OPEN_AI_API_BASE_URL"), "https://default.example.com")

    def test_llm_field_keeps_placeholder_when_unresolved(self):
        """${VAR} 既不在 OS env 也不在 keys.yaml 时保留字面占位符。"""
        self._write_llm(
            "llm:\n  openai:\n    enable: true\n    api_key: ${TOTALLY_UNKNOWN_SECRET}\n"
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            env = llm_mod.load_split_env_config(self.project_root, silent=True)
            flat = llm_mod.flatten_env_config(env, "openai", ["openai"])
        self.assertEqual(flat.get("OPEN_AI_API_KEY"), "${TOTALLY_UNKNOWN_SECRET}")

    def test_multiple_fields_resolved_in_batch(self):
        """一个 llm.yaml 里多个字段都引用变量时全部被解析（批量）。"""
        self._write_llm(
            "llm:\n"
            "  openai:\n"
            "    enable: true\n"
            "    api_key: ${OPENAI_KEY}\n"
            "    base_url: ${OPENAI_BASE}\n"
            "    model: ${OPENAI_MODEL}\n"
        )
        self._write_keys({
            "OPENAI_KEY": "sk-batch-key",
            "OPENAI_BASE": "https://batch.example.com",
            "OPENAI_MODEL": "gpt-4-batch",
        })
        with mock.patch.dict(os.environ, {}, clear=True):
            env = llm_mod.load_split_env_config(self.project_root, silent=True)
            flat = llm_mod.flatten_env_config(env, "openai", ["openai"])
        self.assertEqual(flat.get("OPEN_AI_API_KEY"), "sk-batch-key")
        self.assertEqual(flat.get("OPEN_AI_API_BASE_URL"), "https://batch.example.com")
        # model 字段 → OPENAI_MODEL
        self.assertEqual(flat.get("OPENAI_MODEL"), "gpt-4-batch")


if __name__ == "__main__":
    unittest.main()
