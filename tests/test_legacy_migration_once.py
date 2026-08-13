"""旧品牌目录迁移只执行一次，避免每次启动覆盖用户最新配置。

测试策略：复制文件策略 —— 从真实 config/llm/llm.yaml 复制到临时目录，
在副本上测试迁移逻辑，绝不修改用户真实文件。

覆盖场景：
- 首次启动：旧 AdeBuddy 目录的 llm.yaml 迁移到新 AgentBuddy 目录
- 再次启动：标记文件存在，跳过迁移，不覆盖新目录中用户最新修改
  （如 Provider 的 _enabled 开关）
- 用户真实文件在测试前后保持不变
"""
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_mod

REAL_LLM_FILE = ROOT / "config" / "llm" / "llm.yaml"


class LegacyMigrationOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.current = pathlib.Path(self.tmpdir) / "AgentBuddy"
        # macOS 旧品牌目录：~/Library/Application Support/AdeBuddy
        self.legacy = (
            pathlib.Path(self.tmpdir) / "Library" / "Application Support" / "AdeBuddy"
        )
        self.current.mkdir(parents=True, exist_ok=True)
        self.legacy.mkdir(parents=True, exist_ok=True)
        # 记录真实文件内容，用于验证测试不修改用户文件
        self.real_llm_content = (
            REAL_LLM_FILE.read_text(encoding="utf-8") if REAL_LLM_FILE.exists() else None
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _copy_real_llm(self, root: pathlib.Path) -> pathlib.Path:
        """复制策略：把真实 llm.yaml 复制到指定目录（副本），不修改原文件。"""
        llm_dir = root / "config" / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)
        dst = llm_dir / "llm.yaml"
        shutil.copy2(REAL_LLM_FILE, dst)
        return dst

    def _write_llm(self, root: pathlib.Path, content: str) -> pathlib.Path:
        llm_dir = root / "config" / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)
        path = llm_dir / "llm.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def _run_migrate(self):
        with (
            mock.patch.object(app_mod.sys, "frozen", True, create=True),
            mock.patch.object(app_mod, "PROJECT_ROOT", self.current),
            mock.patch.object(app_mod.sys, "platform", "darwin"),
            mock.patch.object(
                app_mod.Path,
                "home",
                return_value=pathlib.Path(self.tmpdir),
            ),
        ):
            app_mod._migrate_legacy_data_dir()

    def test_first_run_migrates_legacy_llm(self):
        """首次启动：旧目录 llm.yaml 迁移到新目录（复制策略）。"""
        self._copy_real_llm(self.legacy)
        self._run_migrate()

        dst = self.current / "config" / "llm" / "llm.yaml"
        self.assertTrue(dst.exists())
        # 副本内容与真实文件一致
        self.assertEqual(
            dst.read_text(encoding="utf-8"),
            self.real_llm_content,
        )
        # 标记文件已写入
        self.assertTrue((self.current / ".migrated_from_adebuddy").exists())

    def test_second_run_does_not_overwrite_new_config(self):
        """再次启动：标记文件存在，跳过迁移，不覆盖新目录最新配置。"""
        self._copy_real_llm(self.legacy)
        # 首次迁移
        self._run_migrate()
        # 用户随后在新目录把 deepseek 改为启用
        self._write_llm(self.current, "llm:\n  deepseek:\n    _enabled: true\n")
        # 再次启动
        self._run_migrate()

        dst = self.current / "config" / "llm" / "llm.yaml"
        content = dst.read_text(encoding="utf-8")
        # 新目录的 _enabled: true 未被旧目录覆盖
        self.assertIn("_enabled: true", content)
        self.assertNotIn("_enabled: false", content)

    def test_no_legacy_dir_skips_migration(self):
        """无旧目录时跳过迁移，也不写标记。"""
        shutil.rmtree(self.legacy, ignore_errors=True)
        self._run_migrate()
        self.assertFalse((self.current / ".migrated_from_adebuddy").exists())

    def test_real_user_file_unchanged(self):
        """复制策略：测试全程不修改用户真实 llm.yaml。"""
        self._copy_real_llm(self.legacy)
        self._run_migrate()
        # 再次运行迁移（模拟多次启动）
        self._run_migrate()
        # 真实文件内容保持不变
        self.assertEqual(
            REAL_LLM_FILE.read_text(encoding="utf-8"),
            self.real_llm_content,
        )


if __name__ == "__main__":
    unittest.main()
