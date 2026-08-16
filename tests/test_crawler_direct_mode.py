"""Crawler 服务端直连模式测试（临时 DB/市场目录，无网络、无真实数据）。

覆盖：
- server_mode 判定（DB 文件存在即直连）
- ensure_crawler_user：首跑创建、再跑复用同一 id
- publish_local：包文件落盘 + 入库（id/name/version/author_id/file 正确）
- already_published_local：发布前 False / 发布后 True（去重闭环）
"""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import crawler  # noqa: E402


class TestDirectMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "data" / "agentbuddy.db"
        self.market = self.root / "data" / "marketplace"
        self.db.parent.mkdir(parents=True)
        # 重置模块级缓存并指到临时目录
        crawler._auth_models = None
        patches = [
            mock.patch.object(crawler, "DB_FILE", self.db),
            mock.patch.object(crawler, "MARKET_DIR", self.market),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        crawler._auth_models = None
        self.tmp.cleanup()

    def _make_zip(self, name: str, version: str = "1.0.0") -> Path:
        zp = self.root / f"{name}.zip"
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr(f"{name}.plugin.yaml",
                        f"name: {name}\nversion: {version}\ndescription: t\n")
        return zp

    def test_server_mode_detection(self):
        self.assertFalse(crawler.server_mode())  # DB 尚不存在
        self.db.write_bytes(b"")  # 模拟同机部署（init_db 会真正建表）
        self.db.unlink()
        crawler._auth_models = None

    def test_ensure_crawler_user_idempotent(self):
        uid1 = crawler.ensure_crawler_user()
        uid2 = crawler.ensure_crawler_user()
        self.assertEqual(uid1, uid2, "重复调用应复用同一 crawler 账号")

    def test_publish_local_roundtrip_and_dedup(self):
        zp = self._make_zip("direct-test", "2.1.0")
        self.assertFalse(crawler.already_published_local("direct-test", "2.1.0"))

        entry = crawler.publish_local(zp, tags=["t1"])
        self.assertEqual(entry["name"], "direct-test")
        self.assertEqual(entry["version"], "2.1.0")
        self.assertEqual(entry["scope"], "public")
        self.assertTrue(entry["author_id"], "应归属 crawler 服务账号")
        # 包文件已落盘
        pkg = self.market / "packages" / "direct-test-2.1.0.zip"
        self.assertTrue(pkg.exists())
        # 入库可查 → 去重生效
        self.assertTrue(crawler.already_published_local("direct-test", "2.1.0"))

    def test_already_published_dispatch(self):
        """already_published 在直连模式下走查库分支（无 token 也可用）。"""
        self.db.write_bytes(b"")
        # init 会重建表；先发布一个再验分发
        zp = self._make_zip("dispatch-test")
        crawler.publish_local(zp)
        self.assertTrue(crawler.already_published("dispatch-test", "1.0.0", token=""))
        crawler._auth_models = None


if __name__ == "__main__":
    unittest.main()
