"""插件 envVars 导入时初始化到 keys.yaml 的测试。

覆盖场景：
- plugin.yaml 含 envVars → 导入 zip 后 keys.yaml.mcp 应包含这些变量（默认值或空）
- keys.yaml 已有同名变量 → 保留原值，不覆盖
- envVars 缺少 default → 写入空字符串
- 导入多次 → 幂等，不会重复添加
"""
import io
import os
import pathlib
import sys
import tempfile
import unittest
import unittest.mock
import zipfile

import yaml

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
TOOLS_DIR = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TOOLS_DIR))


class PluginEnvVarsImportTests(unittest.TestCase):
    """插件 zip 导入时应把 envVars 初始化到 config/mcp/keys.yaml。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = pathlib.Path(self.tmpdir)
        # 必要的子目录
        (self.project_root / "config" / "mcp").mkdir(parents=True, exist_ok=True)
        (self.project_root / "config" / "llm").mkdir(parents=True, exist_ok=True)
        (self.project_root / "config" / "plugins").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_zip(self, plugin_yaml: dict) -> bytes:
        """构造一个仅含 plugin.yaml 的 zip 包。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "test-plugin.plugin.yaml",
                yaml.safe_dump(plugin_yaml, allow_unicode=True),
            )
        return buf.getvalue()

    def _import(self, zip_bytes: bytes, overwrite: bool = False):
        """直接调用 _import_plugin_zip（绕过 Flask 上下文）。"""
        # config_server 依赖全局 PROJECT_ROOT，需要 patch
        with unittest.mock.patch("config_server.PROJECT_ROOT", self.project_root), \
             unittest.mock.patch("config_server.CONFIG_PLUGINS_DIR",
                                 self.project_root / "config" / "plugins"), \
             unittest.mock.patch("config_server.KEYS_FILE",
                                 self.project_root / "config" / "mcp" / "keys.yaml"), \
             unittest.mock.patch("config_server.LLM_FILE",
                                 self.project_root / "config" / "llm" / "llm.yaml"), \
             unittest.mock.patch("config_server.MCP_CONFIG_FILE",
                                 self.project_root / "config" / "mcp" / "mcp.yaml"):
            import config_server
            buf = io.BytesIO(zip_bytes)
            # _import_plugin_zip 内部用了 jsonify，需要 Flask 请求上下文
            with config_server.app.test_request_context():
                return config_server._import_plugin_zip(buf, overwrite)

    def _read_keys(self) -> dict:
        path = self.project_root / "config" / "mcp" / "keys.yaml"
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def test_envvars_with_default_initialized_to_keys(self):
        """envVars 含 default → keys.yaml 中应写入默认值。"""
        plugin = {
            "name": "test-plugin",
            "version": "1.0.0",
            "envVars": {
                "TAVILY_API_KEY": {
                    "description": "Tavily API 密钥",
                    "default": "tvly-default-xxx",
                    "required": True,
                },
            },
        }
        zip_bytes = self._make_zip(plugin)
        resp, status = self._import(zip_bytes, overwrite=True)
        self.assertEqual(status, 200)
        keys = self._read_keys()
        self.assertEqual(keys.get("mcp", {}).get("TAVILY_API_KEY"), "tvly-default-xxx")

    def test_envvars_without_default_initialized_to_empty(self):
        """envVars 缺少 default → keys.yaml 中写入空字符串。"""
        plugin = {
            "name": "test-plugin",
            "version": "1.0.0",
            "envVars": {
                "OPENAI_API_KEY": {
                    "description": "OpenAI API Key",
                    "required": True,
                },
            },
        }
        zip_bytes = self._make_zip(plugin)
        resp, status = self._import(zip_bytes, overwrite=True)
        self.assertEqual(status, 200)
        keys = self._read_keys()
        self.assertEqual(keys.get("mcp", {}).get("OPENAI_API_KEY"), "")

    def test_existing_keys_not_overwritten(self):
        """keys.yaml 已有同名变量 → 保留原值，不覆盖。"""
        # 预置已有 key
        keys_path = self.project_root / "config" / "mcp" / "keys.yaml"
        keys_path.write_text(
            yaml.safe_dump({"mcp": {"TAVILY_API_KEY": "user-configured-value"}}, allow_unicode=True),
            encoding="utf-8",
        )

        plugin = {
            "name": "test-plugin",
            "version": "1.0.0",
            "envVars": {
                "TAVILY_API_KEY": {
                    "default": "should-not-overwrite",
                },
            },
        }
        zip_bytes = self._make_zip(plugin)
        resp, status = self._import(zip_bytes, overwrite=True)
        self.assertEqual(status, 200)
        keys = self._read_keys()
        self.assertEqual(keys.get("mcp", {}).get("TAVILY_API_KEY"), "user-configured-value")

    def test_import_idempotent(self):
        """同一插件导入两次 → 不会重复添加，值不覆盖。"""
        plugin = {
            "name": "test-plugin",
            "version": "1.0.0",
            "envVars": {
                "FIRST_KEY": {"default": "first"},
                "SECOND_KEY": {"default": "second"},
            },
        }
        zip_bytes = self._make_zip(plugin)
        # 第一次导入
        self._import(zip_bytes, overwrite=True)
        # 用户修改了 FIRST_KEY 的值
        keys_path = self.project_root / "config" / "mcp" / "keys.yaml"
        keys_path.write_text(
            yaml.safe_dump({"mcp": {"FIRST_KEY": "user-modified", "SECOND_KEY": "second"}}, allow_unicode=True),
            encoding="utf-8",
        )
        # 第二次导入（幂等）
        self._import(zip_bytes, overwrite=True)
        keys = self._read_keys()
        # 用户修改的值应保留
        self.assertEqual(keys.get("mcp", {}).get("FIRST_KEY"), "user-modified")
        self.assertEqual(keys.get("mcp", {}).get("SECOND_KEY"), "second")

    def test_no_envvars_does_not_touch_keys(self):
        """plugin.yaml 没有 envVars → keys.yaml 不应被创建或修改。"""
        plugin = {
            "name": "test-plugin",
            "version": "1.0.0",
        }
        zip_bytes = self._make_zip(plugin)
        resp, status = self._import(zip_bytes, overwrite=True)
        self.assertEqual(status, 200)
        # keys.yaml 不应被创建
        self.assertFalse((self.project_root / "config" / "mcp" / "keys.yaml").exists())


if __name__ == "__main__":
    unittest.main()
