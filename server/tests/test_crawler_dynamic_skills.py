"""CrawlerAgent 文章抓取与 skill 抽取回归测试。

注：旧的 sources 段（已知 URL 抓取 + crawl_and_publish）已废弃，
统一为渠道搜索架构（CrawlerAgent + BuildAgent）。本文件保留：
- skill frontmatter 解析
- 微信公众号文章抓取（移动端 UA + cgiDataNew 元数据提取）
- 直配 LLM 兜底（analyze_source 透传 llm_config）

旧的 crawl_and_publish / evaluate_quality / load_sources 相关测试已删除，
对应能力由 crawler_agent.run_task + build_agent.run 覆盖（见
test_rate_article.py 与 test_crawler_quota.py）。
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


class TestSkillFrontmatter(unittest.TestCase):
    def test_parse_skill_frontmatter(self):
        data = _parse_skill_frontmatter("---\nname: demo-skill\ndescription: Demo skill\nversion: 1.2.3\n---\n# Demo\n")
        self.assertEqual(data["name"], "demo-skill")
        self.assertEqual(data["description"], "Demo skill")
        self.assertEqual(str(data["version"]), "1.2.3")


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
    """直配 LLM 兜底：analyze_source 透传 llm_config + 候选 skills 生成。"""

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


if __name__ == "__main__":
    unittest.main()
