"""Crawler 动态发现 skills 并聚合发布的回归测试。"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import crawler  # noqa: E402
from plugin_build import (  # noqa: E402
    PluginMeta,
    SkillInfo,
    _parse_skill_frontmatter,
    analyze_source,
    analyze_url_simple,
    _extract_wechat_cgi_data,
    _looks_like_wechat_block_page,
    _wechat_headers,
    generate_plugin_with_direct_llm,
)


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


class TestWeChatExtraction(unittest.TestCase):
    """微信公众号文章抓取：移动端 UA + cgiDataNew 元数据提取。"""

    def _wechat_html(self, title: str, desc: str) -> str:
        # 模拟微信公众号页面包含 window.cgiDataNew 和 og 元数据
        return (
            f"<html><head>"
            f"<meta property='og:title' content='{title}' />"
            f"<meta property='og:description' content='{desc}' />"
            f"</head><body>"
            f"<script>window.cgiDataNew = {{title: '{title}', desc: '{desc}'}};</script>"
            f"<div>环境异常 完成验证后即可继续访问</div>"
            f"</body></html>"
        )

    def test_wechat_block_page_detection(self):
        self.assertTrue(_looks_like_wechat_block_page("环境异常 完成验证"))
        self.assertTrue(_looks_like_wechat_block_page("微信扫一扫可打开此内容"))
        self.assertFalse(_looks_like_wechat_block_page("正常文章内容"))

    def test_wechat_headers_has_mobile_ua(self):
        headers = _wechat_headers()
        self.assertIn("MicroMessenger", headers["User-Agent"])
        self.assertEqual(headers["Referer"], "https://mp.weixin.qq.com/")

    def test_extract_wechat_cgi_data(self):
        html = self._wechat_html("Codex游戏开发Skill TOP10", "整理了热度TOP10的游戏开发类Skill")
        title, desc = _extract_wechat_cgi_data(html)
        self.assertEqual(title, "Codex游戏开发Skill TOP10")
        self.assertEqual(desc, "整理了热度TOP10的游戏开发类Skill")

    def test_analyze_url_simple_extracts_wechat_metadata(self):
        html = self._wechat_html("Codex游戏开发Skill TOP10", "整理了热度TOP10的游戏开发类Skill")
        calls: list[dict] = []

        def fake_get(url, timeout=20, headers=None):
            calls.append({"url": url, "headers": headers})
            # 第一次（默认 UA）返回风控页；第二次（微信 UA）返回正文
            if headers and "MicroMessenger" in (headers.get("User-Agent") or ""):
                return html
            return "环境异常 完成验证后即可继续访问"

        with mock.patch("plugin_build._http_get_text", side_effect=fake_get):
            meta = analyze_url_simple("https://mp.weixin.qq.com/s/example")

        # 应触发微信 UA 重试
        self.assertGreaterEqual(len(calls), 2)
        self.assertIn("MicroMessenger", calls[1]["headers"]["User-Agent"])
        # _slugify 会剥离中文字符，只保留 codex + skill + top10
        self.assertEqual(meta.name, "codexskill-top10")
        self.assertIn("整理了热度TOP10的游戏开发类Skill", meta.description)


class TestDirectLLMFallback(unittest.TestCase):
    """crawler 直配 LLM 兜底：source.llm 透传 + 候选 skills 生成。"""

    def test_analyze_source_passes_llm_config_when_ai(self):
        captured: dict = {}

        def fake_analyze_url(url):
            return PluginMeta(
                name="wechat-article",
                description="整理了热度TOP10的游戏开发类Skill",
                homepage="https://mp.weixin.qq.com/s/example",
                source_type="url",
                source_url="https://mp.weixin.qq.com/s/example",
            )

        def fake_llm(prompt, llm_config):
            captured["llm_config"] = llm_config
            return (
                "name: codex-game-skills\n"
                "version: '1.0.0'\n"
                "description: 基于文章摘要生成的 Codex 游戏 skills 聚合插件\n"
                "skills:\n"
                "  - name: game-prototype-gen\n"
                "    description: 玩法原型生成 skill\n"
                "    version: '1.0.0'\n"
                "    source: ai-extracted:https://mp.weixin.qq.com/s/example\n"
                "  - name: game-engine-arch\n"
                "    description: 引擎架构搭建 skill\n"
                "    version: '1.0.0'\n"
                "    source: ai-extracted:https://mp.weixin.qq.com/s/example\n"
            )

        llm_cfg = {"base_url": "https://api.example.com/v1", "api_key": "sk-test", "model": "gpt-4o-mini"}
        with mock.patch("plugin_build.analyze_url_simple", side_effect=fake_analyze_url), \
             mock.patch("plugin_build.generate_plugin_with_direct_llm", side_effect=fake_llm):
            meta = analyze_source(Path("/tmp"), "https://mp.weixin.qq.com/s/example", ai=True, llm_config=llm_cfg)

        self.assertEqual(captured["llm_config"]["model"], "gpt-4o-mini")
        self.assertEqual(meta.name, "codex-game-skills")
        self.assertEqual(len(meta.skills), 2)
        self.assertTrue(all(s.source.startswith("ai-extracted:") for s in meta.skills))

    def test_generate_plugin_with_direct_llm_requires_all_fields(self):
        with self.assertRaises(ValueError):
            generate_plugin_with_direct_llm("prompt", {"base_url": "", "api_key": "", "model": ""})

    def test_crawler_passes_source_llm_to_analyze_source(self):
        built = []

        def fake_build(_root, data):
            built.append(data["config_yaml"])
            return Path("/tmp/llm.zip"), {}

        ai_meta = PluginMeta(
            name="codex-game-skills",
            description="基于文章摘要生成的 Codex 游戏 skills 聚合插件",
            source_type="url",
            source_url="https://mp.weixin.qq.com/s/example",
            skills=[SkillInfo(name="game-prototype-gen", source="ai-extracted:https://mp.weixin.qq.com/s/example")],
        )

        source = {
            "name": "codex-game-top10",
            "url": "https://mp.weixin.qq.com/s/example",
            "ai": True,
            "llm": {"base_url": "https://api.example.com/v1", "api_key": "sk-test", "model": "gpt-4o-mini"},
            "tags": ["codex", "game"],
        }

        with mock.patch("plugin_build.analyze_source", return_value=ai_meta) as analyze, \
             mock.patch.object(crawler, "evaluate_quality", return_value=45), \
             mock.patch("plugin_build.build_plugin", side_effect=fake_build):
            result = crawler.crawl_and_publish(source, dry_run=True)

        analyze.assert_called_once()
        _, kwargs = analyze.call_args
        self.assertEqual(kwargs["ai"], True)
        self.assertEqual(kwargs["llm_config"]["model"], "gpt-4o-mini")
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["items"][0]["skills"], ["game-prototype-gen"])


if __name__ == "__main__":
    unittest.main()
