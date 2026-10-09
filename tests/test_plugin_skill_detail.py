"""插件技能明细：正文、已安装 SKILL.md 回退、原文链接。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))

from config_server import _plugin_skill_entries, _skill_source_url  # noqa: E402


class TestSkillSourceUrl(unittest.TestCase):
    def test_github_repo_and_ai_url(self):
        self.assertEqual(_skill_source_url("acme/repo@review"), "https://github.com/acme/repo")
        self.assertEqual(
            _skill_source_url("ai-extracted:https://news.example/a"),
            "https://news.example/a",
        )

    def test_homepage_fallback(self):
        self.assertEqual(
            _skill_source_url("", "https://example.com/article"),
            "https://example.com/article",
        )


class TestPluginSkillEntries(unittest.TestCase):
    def test_inline_body_kept(self):
        cfg = {
            "homepage": "https://example.com/article",
            "skills": [{
                "name": "review",
                "description": "审查代码",
                "version": "1.0.0",
                "source": "acme/repo@review",
                "body": "---\nname: review\n---\n\n# 步骤\n先读 diff。\n",
            }],
        }
        entries = _plugin_skill_entries(cfg)
        self.assertEqual(entries[0]["name"], "review")
        self.assertIn("先读 diff", entries[0]["body"])
        self.assertEqual(entries[0]["source_url"], "https://github.com/acme/repo")

    def test_reads_installed_skill_md_when_body_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "plain-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# plain-skill\n\n按描述执行。\n", encoding="utf-8")
            cfg = {"skills": [{"name": "plain-skill", "description": "无正文", "source": ""}]}
            with patch("config_server.PROJECT_SKILLS_DIR", Path(tmp)), \
                 patch("config_server.DOT_AGENTS_SKILLS", Path(tmp) / "missing-a"), \
                 patch("config_server.AGENTS_SKILLS_CACHE", Path(tmp) / "missing-b"):
                entries = _plugin_skill_entries(cfg)
            self.assertEqual(entries[0]["body"], "# plain-skill\n\n按描述执行。\n")
            self.assertEqual(entries[0]["source_url"], "")
