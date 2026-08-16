"""服务端插件构建/发布核心能力测试。"""
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT))

try:
    import bcrypt  # noqa: F401
except ModuleNotFoundError:
    sys.modules["bcrypt"] = types.SimpleNamespace(
        hashpw=lambda password, salt: b"test-hash",
        gensalt=lambda: b"test-salt",
    )

from auth import models  # noqa: E402
from plugin_build import publish_local  # noqa: E402


class TestServerPluginBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "agentbuddy.db"
        self.market = self.root / "marketplace"
        models.set_marketplace_dir(self.market)
        models.set_db_path(self.db)
        conn = models.get_db()
        conn.execute(
            "INSERT INTO users (id, username, password, email, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (42, "alice", "x", "", "member", models.now_iso()),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _zip(self, name="server-built", version="1.2.3") -> Path:
        path = self.root / "built.zip"
        data = {
            "name": name,
            "version": version,
            "description": "service build",
            "author": "yaml-author",
        }
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(f"{name}.plugin.yaml", yaml.dump(data, sort_keys=False))
        return path

    def test_publish_local_writes_package_and_db_entry_for_user(self):
        zip_path = self._zip()
        entry = publish_local(
            zip_path,
            self.market,
            tags=["service"],
            user={"id": 42, "username": "alice"},
        )

        self.assertEqual(entry["name"], "server-built")
        self.assertEqual(entry["version"], "1.2.3")
        self.assertEqual(entry["author_id"], 42)
        self.assertEqual(entry["tags"], ["service"])
        self.assertTrue((self.market / "packages" / "server-built-1.2.3.zip").exists())

        loaded = models.plugin_get("server-built-1.2.3")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "server-built")


if __name__ == "__main__":
    unittest.main()
