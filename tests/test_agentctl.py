"""agentctl 测试套件。

迁移自 tests/test_init_env.py 和 tests/test_plugin_manager.py，
改为导入 scripts/lib/ 下的模块（替代直接导入旧脚本）。

测试覆盖：
- FlattenEnvConfigTests: llm.flatten_env_config 行为（迁移自 test_init_env）
- SkillsFilterTests: skills.copy_skills_safe 白名单过滤（新增）
"""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

# 将 scripts/ 加入 sys.path 以导入 lib 包
SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib import llm, skills, plugins


class FlattenEnvConfigTests(unittest.TestCase):
    """迁移自 test_init_env.py，验证 llm.flatten_env_config 行为不变。"""

    def test_vision_flat_provider_exports_default_model(self):
        env_config = {
            "vision": {
                "volcengine": {
                    "base_url": "https://example.invalid/api",
                    "api_key": "test-key",
                    "models": {
                        "doubao-seedance-2-0-fast-260128": {
                            "name": "Seedance fast"
                        }
                    },
                }
            }
        }

        flat = llm.flatten_env_config(env_config, "", [])

        self.assertEqual(
            flat["VISION_VOLCENGINE_MODEL"],
            "doubao-seedance-2-0-fast-260128",
        )


class SkillsFilterTests(unittest.TestCase):
    """新增：验证 skills.copy_skills_safe 的白名单过滤。"""

    def test_include_skills_filters_copy(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "src"
            src.mkdir()
            (src / "keep").mkdir()
            (src / "keep" / "SKILL.md").write_text("x")
            (src / "skip").mkdir()
            (src / "skip" / "SKILL.md").write_text("y")
            dst = pathlib.Path(td) / "dst"

            skills.copy_skills_safe(src, dst, "test", True, include_skills={"keep"})

            self.assertTrue((dst / "keep").exists())
            self.assertFalse((dst / "skip").exists())

    def test_include_skills_none_copies_all(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "src"
            src.mkdir()
            (src / "a").mkdir()
            (src / "a" / "SKILL.md").write_text("a")
            (src / "b").mkdir()
            (src / "b" / "SKILL.md").write_text("b")
            dst = pathlib.Path(td) / "dst"

            skills.copy_skills_safe(src, dst, "test", True, include_skills=None)

            self.assertTrue((dst / "a").exists())
            self.assertTrue((dst / "b").exists())


if __name__ == "__main__":
    unittest.main()
