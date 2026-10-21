"""LLM 获取模型：api_key 解析与 HTTP 头编码校验。"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))

from config_server import _header_safe_secret, _resolve_api_key  # noqa: E402


class LlmVerifyApiKeyTests(unittest.TestCase):
    def test_header_safe_rejects_chinese(self):
        value, err = _header_safe_secret("密钥说明文字")
        self.assertIsNone(value)
        self.assertIn("非 ASCII", err or "")

    def test_header_safe_accepts_sk_key(self):
        value, err = _header_safe_secret("sk-test-123")
        self.assertEqual(value, "sk-test-123")
        self.assertIsNone(err)

    def test_resolve_from_keys_yaml(self):
        env = {
            "llm": {},
            "mcp": {"DEMO_KEY": {"value": "sk-from-keys"}},
        }
        with patch("agentctl.lib.llm.load_split_env_config", return_value=env):
            self.assertEqual(_resolve_api_key("${DEMO_KEY}"), "sk-from-keys")

    def test_resolve_chinese_default_is_detected_before_request(self):
        env = {"llm": {}, "mcp": {}}
        with patch("agentctl.lib.llm.load_split_env_config", return_value=env):
            resolved = _resolve_api_key("${MISSING:-中文默认值}")
        self.assertEqual(resolved, "中文默认值")
        value, err = _header_safe_secret(resolved)
        self.assertIsNone(value)
        self.assertIn("非 ASCII", err or "")

    def test_resolve_os_env_fallback(self):
        env = {"llm": {}, "mcp": {}}
        with patch("agentctl.lib.llm.load_split_env_config", return_value=env):
            with patch.dict(os.environ, {"FALLBACK_LLM_KEY": "sk-env"}, clear=False):
                self.assertEqual(_resolve_api_key("${FALLBACK_LLM_KEY}"), "sk-env")


if __name__ == "__main__":
    unittest.main()
