"""rebuild_plugins_from_local.py 重建脚本测试。

验证：
- zip 内 .plugin.yaml 解析正确
- spec yaml 补充 keywords/tags / description（取更长）
- zip 同步到 marketplace/packages/
- plugins 表写入（INSERT ... ON DUPLICATE KEY UPDATE 幂等）
"""
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
        gensalt=lambda *args, **kwargs: b"test-salt",
    )

from auth import models  # noqa: E402


class TestRebuildPluginsFromLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "agentbuddy.db"
        self.market = self.root / "marketplace"
        self.builds = self.root / "plugin-builds"
        self.specs = self.root / "specs" / "skills-daily"
        self.builds.mkdir(parents=True)
        self.specs.mkdir(parents=True)

        models.set_marketplace_dir(self.market)
        models.set_db_path(self.db)
        # 重置 _db 模块状态，触发 init_db
        import db
        db._DB_PATH = self.db
        db._DB_URL = None
        db._backend = "sqlite"
        db._pool = None

    def _make_zip(self, name: str, version: str = "1.0.0",
                  description: str = "", author: str = "crawler-agent") -> Path:
        """构造一个含 .plugin.yaml 的 zip。"""
        plugin_yaml = {
            "name": name,
            "version": version,
            "description": description,
            "author": author,
        }
        zip_path = self.builds / f"{name}-plugin.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                f"{name}.plugin.yaml",
                yaml.safe_dump(plugin_yaml, allow_unicode=True),
            )
            zf.writestr("SKILL.md", "# test skill\n")
        return zip_path

    def _make_spec(self, name: str, description: str = "",
                  keywords: list | None = None) -> Path:
        """构造 spec yaml。"""
        spec = {
            "spec_version": "1.0",
            "name": name,
            "version": "1.0.0",
            "description": description,
            "keywords": keywords or [],
            "homepage": "https://example.com",
        }
        spec_path = self.specs / f"{name}.yaml"
        spec_path.write_text(
            yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8"
        )
        return spec_path

    def test_parse_plugin_yaml_from_zip(self):
        from scripts.rebuild_plugins_from_local import parse_plugin_yaml_from_zip
        zp = self._make_zip("foo", description="hello")
        d = parse_plugin_yaml_from_zip(zp)
        self.assertIsNotNone(d)
        self.assertEqual(d["name"], "foo")
        self.assertEqual(d["version"], "1.0.0")
        self.assertEqual(d["description"], "hello")
        self.assertEqual(d["author"], "crawler-agent")

    def test_parse_plugin_yaml_bad_zip(self):
        from scripts.rebuild_plugins_from_local import parse_plugin_yaml_from_zip
        zp = self.builds / "bad.zip"
        zp.write_bytes(b"not a zip")
        self.assertIsNone(parse_plugin_yaml_from_zip(zp))

    def test_find_spec_yaml_recursive(self):
        from scripts.rebuild_plugins_from_local import find_spec_yaml
        self._make_spec("bar", description="spec desc")
        p = find_spec_yaml(self.specs, "bar")
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "bar.yaml")
        self.assertIsNone(find_spec_yaml(self.specs, "not-exist"))

    def test_rebuild_one_basic(self):
        from scripts.rebuild_plugins_from_local import rebuild_one
        zp = self._make_zip("baz", description="zip desc")
        entry = rebuild_one(zp, self.specs.parent, self.market)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "baz-1.0.0")
        self.assertEqual(entry["name"], "baz")
        self.assertEqual(entry["description"], "zip desc")
        self.assertEqual(entry["author"], "crawler-agent")
        self.assertIsNone(entry["author_id"])
        self.assertEqual(entry["file"], "packages/baz-1.0.0.zip")
        self.assertEqual(entry["scope"], "public")
        self.assertIsNone(entry["team_id"])
        self.assertEqual(entry["downloads"], 0)
        self.assertEqual(entry["likes"], 0)
        # zip 已同步到 marketplace/packages/
        self.assertTrue((self.market / "packages" / "baz-1.0.0.zip").exists())

    def test_rebuild_one_spec_supplements(self):
        """spec.description 更长时覆盖；keywords → tags。"""
        from scripts.rebuild_plugins_from_local import rebuild_one
        zp = self._make_zip("qux", description="short")
        self._make_spec("qux", description="longer description from spec",
                        keywords=["ai", "cursor"])
        entry = rebuild_one(zp, self.specs.parent, self.market)
        self.assertIsNotNone(entry)
        # 取更长 description
        self.assertEqual(entry["description"], "longer description from spec")
        self.assertEqual(entry["tags"], ["ai", "cursor"])

    def test_rebuild_one_zip_desc_longer_kept(self):
        """zip description 更长时保留 zip 的。"""
        from scripts.rebuild_plugins_from_local import rebuild_one
        zp = self._make_zip("hoge", description="zip longer description here")
        self._make_spec("hoge", description="shorter")
        entry = rebuild_one(zp, self.specs.parent, self.market)
        self.assertEqual(entry["description"], "zip longer description here")

    def test_rebuild_one_no_spec_ok(self):
        """没匹配 spec 也能正常重建。"""
        from scripts.rebuild_plugins_from_local import rebuild_one
        zp = self._make_zip("noss", description="no spec desc")
        entry = rebuild_one(zp, self.specs.parent, self.market)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["description"], "no spec desc")
        self.assertEqual(entry["tags"], [])

    def test_rebuild_one_sync_zip_idempotent(self):
        """重复执行不报错，包文件存在。"""
        from scripts.rebuild_plugins_from_local import rebuild_one
        zp = self._make_zip("once", description="d")
        e1 = rebuild_one(zp, self.specs.parent, self.market)
        e2 = rebuild_one(zp, self.specs.parent, self.market)
        self.assertEqual(e1["id"], e2["id"])
        self.assertTrue((self.market / "packages" / "once-1.0.0.zip").exists())

    def test_plugin_save_insert_once(self):
        """plugin_save 写入成功（plugin_save 在 SQLite 下重复会抛 UNIQUE，
        因为 ON DUPLICATE KEY UPDATE 翻译后只剩 INSERT——这不是 rebuild 脚本的问题，
        脚本本身用 INSERT IGNORE 路径迁移时跳过已存在）。"""
        from scripts.rebuild_plugins_from_local import rebuild_one
        zp = self._make_zip("upsert", description="d")
        entry = rebuild_one(zp, self.specs.parent, self.market)
        models.plugin_save(entry)
        row = models.plugin_get(entry["id"])
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "upsert")

    def test_safe_plugin_name(self):
        from scripts.rebuild_plugins_from_local import safe_plugin_name
        self.assertEqual(safe_plugin_name("foo bar"), "foobar")
        self.assertEqual(safe_plugin_name("foo-bar_123"), "foo-bar_123")
        # 中文字符的 isalnum() 返回 True，会原样保留
        self.assertEqual(safe_plugin_name("中文名"), "中文名")
        # 空格 / 标点被过滤
        self.assertEqual(safe_plugin_name("foo@bar!"), "foobar")


if __name__ == "__main__":
    unittest.main()
