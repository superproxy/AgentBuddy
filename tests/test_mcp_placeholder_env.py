"""MCP 占位符环境变量解析单元测试。

覆盖场景：
- ${VAR} 只从 flat_config（mcp.yaml 的 mcp: 段 / keys.yaml）解析
- OS 环境变量不会成为反向数据源
- 未配置变量保留占位符（交由 prune 阶段处理）
- ${VAR:-default} 默认值语法仍然有效
"""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib import mcp as mcp_mod


class ResolvePlaceholdersEnvTests(unittest.TestCase):
    """_resolve_placeholders 只从受管 env_map 解析 ${VAR}。"""

    def test_ignores_os_env_and_uses_env_map(self):
        """OS 环境变量存在时仍使用 keys.yaml 对应的受管值。"""
        obj = {"env": {"API_KEY": "${MY_TEST_KEY}"}}
        with mock.patch.dict(os.environ, {"MY_TEST_KEY": "from-os"}, clear=False):
            resolved, count = mcp_mod._resolve_placeholders(obj, {"MY_TEST_KEY": "from-keys"})
        self.assertEqual(resolved["env"]["API_KEY"], "from-keys")
        self.assertGreaterEqual(count, 1)

    def test_fallbacks_to_env_map_when_os_env_missing(self):
        """${VAR} 不在 OS env 时用 env_map（keys.yaml）的值。"""
        obj = {"env": {"API_KEY": "${MY_TEST_KEY}"}}
        # 确保 OS env 没有此变量
        with mock.patch.dict(os.environ, {}, clear=True):
            resolved, _ = mcp_mod._resolve_placeholders(obj, {"MY_TEST_KEY": "from-keys"})
        self.assertEqual(resolved["env"]["API_KEY"], "from-keys")

    def test_keeps_placeholder_when_neither_os_nor_keys(self):
        """${VAR} 既不在 OS env 也不在 env_map 时保留字面占位符。"""
        obj = {"env": {"API_KEY": "${UNKNOWN_VAR}"}}
        with mock.patch.dict(os.environ, {}, clear=True):
            resolved, _ = mcp_mod._resolve_placeholders(obj, {})
        self.assertEqual(resolved["env"]["API_KEY"], "${UNKNOWN_VAR}")

    def test_default_value_syntax_ignores_os_env(self):
        """${VAR:-default} 不读取 OS env，env_map 缺失时使用 default。"""
        obj = {"url": "https://api.example.com/${MY_DEFAULT:-fallback}"}
        with mock.patch.dict(os.environ, {"MY_DEFAULT": "from-os"}, clear=False):
            resolved, _ = mcp_mod._resolve_placeholders(obj, {})
        self.assertEqual(resolved["url"], "https://api.example.com/fallback")

    def test_default_value_uses_env_map_when_no_os(self):
        """${VAR:-default} 无 OS env 时用 env_map。"""
        obj = {"url": "https://api.example.com/${MY_DEFAULT:-fallback}"}
        with mock.patch.dict(os.environ, {}, clear=True):
            resolved, _ = mcp_mod._resolve_placeholders(obj, {"MY_DEFAULT": "from-keys"})
        self.assertEqual(resolved["url"], "https://api.example.com/from-keys")

    def test_default_value_uses_default_when_neither(self):
        """${VAR:-default} 无 OS env 也无 env_map 时用 default。"""
        obj = {"url": "https://api.example.com/${MY_DEFAULT:-fallback}"}
        with mock.patch.dict(os.environ, {}, clear=True):
            resolved, _ = mcp_mod._resolve_placeholders(obj, {})
        self.assertEqual(resolved["url"], "https://api.example.com/fallback")


if __name__ == "__main__":
    unittest.main()
