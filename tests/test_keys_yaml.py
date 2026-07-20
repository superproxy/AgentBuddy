"""keys.yaml 独立密钥/环境变量文件加载测试。

覆盖场景：
- keys.yaml 存在时，load_split_env_config 应合并到 env_config["mcp"]
- keys.yaml 不存在时，回退到 mcp.yaml.mcp 段（向后兼容）
- keys.yaml 存在时，mcp.yaml.mcp 段不再被读取（迁移完成后的状态）
- 同时存在时，keys.yaml 优先（鼓励用户迁移到独立文件）
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


class LoadSplitEnvConfigKeysYamlTests(unittest.TestCase):
    """load_split_env_config 应优先读取 config/mcp/keys.yaml 作为密钥层。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = pathlib.Path(self.tmpdir)
        self.llm_dir = self.project_root / "config" / "llm"
        self.mcp_dir = self.project_root / "config" / "mcp"
        self.llm_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_dir.mkdir(parents=True, exist_ok=True)
        # 基础 llm.yaml
        (self.llm_dir / "llm.yaml").write_text(
            "llm:\n  openai:\n    enable: true\n    api_key: sk-test\n",
            encoding="utf-8",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_mcp_yaml(self, mcp_keys: dict, mcp_servers: dict | None = None):
        import yaml
        data = {"mcp": mcp_keys}
        if mcp_servers is not None:
            data["mcpServers"] = mcp_servers
        (self.mcp_dir / "mcp.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True),
            encoding="utf-8",
        )

    def _write_keys_yaml(self, keys: dict):
        import yaml
        (self.mcp_dir / "keys.yaml").write_text(
            yaml.safe_dump({"mcp": keys}, allow_unicode=True),
            encoding="utf-8",
        )

    def test_keys_yaml_present_mcp_yaml_no_mcp_section(self):
        """keys.yaml 存在 + mcp.yaml 无 mcp: 段 → 用 keys.yaml 的内容。"""
        self._write_mcp_yaml({}, {"test": {"command": "x"}})  # mcp.yaml 只有 mcpServers
        self._write_keys_yaml({"TAVILY_API_KEY": "from-keys-yaml"})

        env = llm_mod.load_split_env_config(self.project_root, silent=True)
        self.assertEqual(env["mcp"].get("TAVILY_API_KEY"), "from-keys-yaml")

    def test_keys_yaml_present_mcp_yaml_has_mcp_section_keys_yaml_wins(self):
        """keys.yaml 存在 + mcp.yaml 也有 mcp: 段 → keys.yaml 优先（mcp.yaml.mcp 被忽略）。"""
        self._write_mcp_yaml({"TAVILY_API_KEY": "from-mcp-yaml"})
        self._write_keys_yaml({"TAVILY_API_KEY": "from-keys-yaml"})

        env = llm_mod.load_split_env_config(self.project_root, silent=True)
        # keys.yaml 优先：值应为 from-keys-yaml
        self.assertEqual(env["mcp"].get("TAVILY_API_KEY"), "from-keys-yaml")

    def test_keys_yaml_absent_fallback_to_mcp_yaml(self):
        """keys.yaml 不存在 + mcp.yaml 有 mcp: 段 → 回退到 mcp.yaml.mcp（向后兼容）。"""
        self._write_mcp_yaml({"TAVILY_API_KEY": "from-mcp-yaml"})
        # 不创建 keys.yaml

        env = llm_mod.load_split_env_config(self.project_root, silent=True)
        self.assertEqual(env["mcp"].get("TAVILY_API_KEY"), "from-mcp-yaml")

    def test_keys_yaml_present_mcp_yaml_absent(self):
        """keys.yaml 存在 + mcp.yaml 不存在 → 仍能用 keys.yaml。"""
        # 不创建 mcp.yaml
        self._write_keys_yaml({"TAVILY_API_KEY": "from-keys-yaml"})

        env = llm_mod.load_split_env_config(self.project_root, silent=True)
        self.assertEqual(env["mcp"].get("TAVILY_API_KEY"), "from-keys-yaml")

    def test_keys_yaml_merges_with_mcp_yaml_distinct_keys(self):
        """keys.yaml 有 A、mcp.yaml.mcp 有 B → 合并（但同 key 时 keys.yaml 优先）。

        注：鼓励用户迁移完成后清空 mcp.yaml.mcp，但同 key 冲突时 keys.yaml 优先。
        """
        self._write_mcp_yaml({"KEY_B": "from-mcp-yaml"})
        self._write_keys_yaml({"KEY_A": "from-keys-yaml"})

        env = llm_mod.load_split_env_config(self.project_root, silent=True)
        self.assertEqual(env["mcp"].get("KEY_A"), "from-keys-yaml")
        # 不同 key 时合并：B 也可用（兼容性，便于渐进迁移）
        self.assertEqual(env["mcp"].get("KEY_B"), "from-mcp-yaml")


if __name__ == "__main__":
    unittest.main()
