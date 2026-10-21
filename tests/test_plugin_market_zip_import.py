"""市场/服务端 zip 导入：plugin.yaml 识别、SKILL frontmatter、默认启用。"""
import io
import pathlib
import sys
import tempfile
import unittest
import unittest.mock
import zipfile

import yaml

_DESKTOP_DIR = pathlib.Path(__file__).resolve().parents[1] / "desktop"
if str(_DESKTOP_DIR) not in sys.path:
    sys.path.insert(0, str(_DESKTOP_DIR))


class MarketZipImportTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = pathlib.Path(self.tmpdir)
        (self.project_root / "config" / "plugins").mkdir(parents=True)
        (self.project_root / "config" / "skills").mkdir(parents=True)
        (self.project_root / "config" / "skill").mkdir(parents=True)
        self.skill_yaml = self.project_root / "config" / "skill" / "skill.yaml"
        self.skill_yaml.write_text("enabled: []\n", encoding="utf-8")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _import_zip(self, zf_builder) -> tuple:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf_builder(zf)
        buf.seek(0)
        with unittest.mock.patch("config_server.PROJECT_ROOT", self.project_root), \
             unittest.mock.patch("config_server.CONFIG_PLUGINS_DIR", self.project_root / "config" / "plugins"), \
             unittest.mock.patch("config_server.PROJECT_SKILLS_DIR", self.project_root / "config" / "skills"), \
             unittest.mock.patch("config_server.SKILL_YAML", self.skill_yaml), \
             unittest.mock.patch("config_server.KEYS_FILE", self.project_root / "config" / "mcp" / "keys.yaml"), \
             unittest.mock.patch(
                 "config_server.subprocess.run",
                 return_value=unittest.mock.Mock(returncode=0, stdout="", stderr=""),
             ), \
             unittest.mock.patch("config_server._script_run_cmd", return_value=["echo"]):
            import config_server

            with config_server.app.test_request_context():
                return config_server._import_plugin_zip(buf, overwrite=True)

    def test_root_plugin_yaml_imported_as_plugin_yaml(self):
        def build(zf):
            zf.writestr(
                "plugin.yaml",
                yaml.safe_dump(
                    {"name": "crawler-demo", "version": "1.0.0", "skills": []},
                    allow_unicode=True,
                ),
            )

        resp, status = self._import_zip(build)
        self.assertEqual(status, 200)
        body = resp.get_json()
        self.assertEqual(body["plugin_count"], 1)
        out = self.project_root / "config" / "plugins" / "crawler-demo.plugin.yaml"
        self.assertTrue(out.is_file())

    def test_legacy_skill_md_gets_frontmatter_and_enabled(self):
        def build(zf):
            zf.writestr(
                "plugin.yaml",
                yaml.safe_dump({"name": "p", "version": "1.0.0"}, allow_unicode=True),
            )
            zf.writestr("skills/demo-skill/SKILL.md", "# demo-skill\n\n步骤一。\n")

        resp, status = self._import_zip(build)
        self.assertEqual(status, 200)
        md = (self.project_root / "config" / "skills" / "demo-skill" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(md.startswith("---\n"))
        self.assertIn("name: demo-skill", md)
        data = yaml.safe_load(self.skill_yaml.read_text(encoding="utf-8"))
        self.assertIn("demo-skill", data.get("enabled") or [])


if __name__ == "__main__":
    unittest.main()
