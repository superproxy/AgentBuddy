"""frozen 启动引导自愈清理测试（不依赖网络与真实数据目录）。

背景事故：旧版应用曾把整个 desktop/（含 config_server.py）复制到数据目录；
launcher 把 PROJECT_ROOT/desktop 插到 sys.path[0]，数据目录里的旧
config_server.py 遮蔽 bundle 内的新后端 —— 应用升级到新版后 API 仍 404
（如 /api/plugin/analyze），且永远无法通过升级自愈。

测试策略：mock sys.frozen + sys._MEIPASS 指向临时目录，在临时 PROJECT_ROOT
里预置旧版残留（desktop/config_server.py、tools/、scripts/ 等），调用
launcher._bootstrap_from_bundle()，断言残留被清理、bundle 资源被同步、
用户数据（config/）不受影响。
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))

import launcher as app_mod  # noqa: E402


class TestBootstrapPurgeLegacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # 假 bundle（_MEIPASS）：含 cli/ template/ desktop/dist-ui/ AGENTS.md
        self.meipass = self.root / "bundle"
        (self.meipass / "cli").mkdir(parents=True)
        (self.meipass / "cli" / "agentctl.py").write_text("# new cli")
        (self.meipass / "template").mkdir(parents=True)
        (self.meipass / "desktop" / "dist-ui").mkdir(parents=True)
        (self.meipass / "desktop" / "dist-ui" / "index.html").write_text("<html>new</html>")
        (self.meipass / "AGENTS.md").write_text("# new agents")

        # 假数据目录（PROJECT_ROOT）：预置旧版残留 + 用户数据
        self.data = self.root / "data"
        self.data.mkdir()
        # 旧版整目录复制残留（遮蔽元凶）
        (self.data / "desktop").mkdir()
        (self.data / "desktop" / "config_server.py").write_text("# STALE backend")
        (self.data / "desktop" / "launcher.py").write_text("# STALE launcher")
        (self.data / "desktop" / "frontend").mkdir(parents=True)
        (self.data / "desktop" / "frontend" / "pkg.json").write_text("{}")
        # 更早布局残留
        (self.data / "tools").mkdir()
        (self.data / "tools" / "config_server.py").write_text("# STALE tools backend")
        (self.data / "scripts").mkdir()
        (self.data / "scripts" / "agentctl.py").write_text("# STALE scripts")
        # 用户数据（必须保留）
        (self.data / "config" / "llm").mkdir(parents=True)
        (self.data / "config" / "llm" / "llm.yaml").write_text("llm: {}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_purges_stale_shadow_and_syncs_bundle(self):
        with mock.patch.object(app_mod.sys, "frozen", True, create=True), \
             mock.patch.object(app_mod.sys, "_MEIPASS", str(self.meipass), create=True), \
             mock.patch.object(app_mod, "PROJECT_ROOT", self.data):
            app_mod._bootstrap_from_bundle()

        # 遮蔽元凶被清理
        self.assertFalse((self.data / "desktop" / "config_server.py").exists())
        self.assertFalse((self.data / "desktop" / "launcher.py").exists())
        self.assertFalse((self.data / "desktop" / "frontend").exists())
        # 旧布局目录被清理
        self.assertFalse((self.data / "tools").exists())
        self.assertFalse((self.data / "scripts").exists())
        # bundle 资源已同步
        self.assertTrue((self.data / "desktop" / "dist-ui" / "index.html").exists())
        self.assertEqual((self.data / "cli" / "agentctl.py").read_text(), "# new cli")
        # 用户数据不受影响
        self.assertTrue((self.data / "config" / "llm" / "llm.yaml").exists())
        # 标记文件写入
        self.assertTrue((self.data / ".bundle_bootstrapped").exists())

    def test_dev_mode_noop(self):
        """dev 模式（非 frozen）不执行任何同步/清理。"""
        with mock.patch.object(app_mod.sys, "frozen", False, create=True), \
             mock.patch.object(app_mod, "PROJECT_ROOT", self.data):
            app_mod._bootstrap_from_bundle()
        # 残留原样保留（dev 模式不碰数据目录）
        self.assertTrue((self.data / "desktop" / "config_server.py").exists())
        self.assertTrue((self.data / "tools").exists())


if __name__ == "__main__":
    unittest.main()
