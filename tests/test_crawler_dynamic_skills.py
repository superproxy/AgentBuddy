"""Crawler 动态发现 skills 并聚合发布的回归测试。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import crawler  # noqa: E402
from plugin_build import PluginMeta, SkillInfo, _parse_skill_frontmatter  # noqa: E402


class TestCrawlerDynamicSkills(unittest.TestCase):
    def _meta(self) -> PluginMeta:
        return PluginMeta(
            name="source-repo",
            version="1.0.0",
            description="A source repo with useful skills for automated publishing.",
            homepage="https://github.com/acme/source-repo",
            repository="https://github.com/acme/source-repo",
            skills=[
                SkillInfo(name="alpha-skill", description="Alpha automation skill", source="acme/source-repo@alpha-skill"),
                SkillInfo(name="beta-skill", description="Beta automation skill", source="acme/source-repo@beta-skill"),
            ],
            tags=["automation"],
            source_type="github",
            source_url="https://github.com/acme/source-repo",
        )

    def test_parse_skill_frontmatter(self):
        data = _parse_skill_frontmatter("---\nname: demo-skill\ndescription: Demo skill\nversion: 1.2.3\n---\n# Demo\n")
        self.assertEqual(data["name"], "demo-skill")
        self.assertEqual(data["description"], "Demo skill")
        self.assertEqual(str(data["version"]), "1.2.3")

    def test_crawl_and_publish_dry_run_builds_aggregate_plugin(self):
        built = []

        def fake_build(_root, data):
            built.append(data["config_yaml"])
            return Path("/tmp/aggregate.zip"), {}

        with mock.patch("plugin_build.analyze_source", return_value=self._meta()), \
             mock.patch.object(crawler, "evaluate_quality", return_value=45), \
             mock.patch("plugin_build.build_plugin", side_effect=fake_build):
            result = crawler.crawl_and_publish({"name": "src", "url": "https://github.com/acme/source-repo"}, dry_run=True)

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["name"], "src-skills")
        self.assertEqual(result["items"][0]["skills"], ["alpha-skill", "beta-skill"])
        self.assertEqual(len(built), 1)
        self.assertIn("name: src-skills", built[0])
        self.assertIn("name: alpha-skill", built[0])
        self.assertIn("name: beta-skill", built[0])

    def test_source_skills_whitelist_limits_published_items(self):
        with mock.patch("plugin_build.analyze_source", return_value=self._meta()), \
             mock.patch.object(crawler, "evaluate_quality", return_value=45), \
             mock.patch("plugin_build.build_plugin", return_value=(Path("/tmp/beta.zip"), {})):
            result = crawler.crawl_and_publish(
                {"name": "src", "url": "https://github.com/acme/source-repo", "skills": ["beta-skill"]},
                dry_run=True,
            )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["name"], "src")
        self.assertEqual(result["items"][0]["skills"], ["beta-skill"])

    def test_url_source_can_use_configured_repositories_when_page_has_no_skills(self):
        article_meta = PluginMeta(
            name="wechat-article",
            description="WeChat verification page without article body.",
            homepage="https://mp.weixin.qq.com/s/example",
            source_type="url",
            source_url="https://mp.weixin.qq.com/s/example",
        )
        repo_meta = self._meta()
        built = []

        def fake_build(_root, data):
            built.append(data["config_yaml"])
            return Path("/tmp/wechat.zip"), {}

        with mock.patch("plugin_build.analyze_source", return_value=article_meta), \
             mock.patch("plugin_build.analyze_github", return_value=repo_meta), \
             mock.patch.object(crawler, "evaluate_quality", return_value=45), \
             mock.patch("plugin_build.build_plugin", side_effect=fake_build):
            result = crawler.crawl_and_publish(
                {
                    "name": "codex-game-top10",
                    "url": "https://mp.weixin.qq.com/s/example",
                    "repos": ["acme/source-repo"],
                },
                dry_run=True,
            )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["items"][0]["name"], "codex-game-top10-skills")
        self.assertEqual(result["items"][0]["skills"], ["alpha-skill", "beta-skill"])
        self.assertEqual(len(built), 1)
        self.assertIn("name: alpha-skill", built[0])
        self.assertIn("name: beta-skill", built[0])
        self.assertNotIn("WeChat verification page", built[0])
        self.assertIn("Aggregated skills from https://mp.weixin.qq.com/s/example", built[0])

    def test_remaining_quota_zero_skips_source(self):
        with mock.patch("plugin_build.analyze_source") as analyze, \
             mock.patch("plugin_build.build_plugin") as build:
            result = crawler.crawl_and_publish(
                {"name": "src", "url": "https://github.com/acme/source-repo"},
                dry_run=False,
                remaining_quota=0,
            )

        analyze.assert_not_called()
        build.assert_not_called()
        self.assertEqual(result["status"], "skip")
        self.assertEqual(result["stopped_reason"], "quota_reached")


if __name__ == "__main__":
    unittest.main()
