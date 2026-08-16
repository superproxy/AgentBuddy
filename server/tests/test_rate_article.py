"""CrawlerAgent 文章评级函数 rate_article() 单元测试。

覆盖五个评分维度 + 风控惩罚 + 阈值过滤场景：
- content_length（20 分）：>2000 满分，500-2000 线性，<500 得 0
- code_blocks（25 分）：每个代码块 5 分，上限 25
- intent_relevance（25 分）：基于 intent 信号 / 领域关键词 / 代码块的存在打分
- channel（20 分）：渠道权重（0-20）
- penalty：风控无摘要直接 0 分；风控有摘要 -15
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crawler_agent  # noqa: E402
from crawler_agent import rate_article, _intent_relevance  # noqa: E402


# 构造一段足够长的正文（>2000 字符），含代码块，命中领域关键词
_LONG_CONTENT_WITH_CODE = (
    "# Claude Code Skills 实战\n\n"
    + "本文章介绍如何使用 Claude Code skills 进行自动化开发。" * 60  # 长度 >2000
    + "\n```python\nprint('hello')\n```\n"  # 1 个代码块 = 5 分
    + "\n```yaml\nname: demo\n```\n"        # 第 2 个代码块 = 5 分
)


class TestIntentRelevance(unittest.TestCase):
    """测试 _intent_relevance(title, content, intent) 的打分梯度。"""

    def test_empty_inputs_returns_zero(self):
        self.assertEqual(_intent_relevance("", "", "trending"), 0.0)

    def test_trending_signal_in_title(self):
        # 标题含 "TOP 10" → 1.0
        self.assertEqual(
            _intent_relevance("TOP 10 Claude Code Skills 推荐", "正文", "trending"),
            1.0,
        )

    def test_trending_signal_in_content(self):
        # 标题无信号，正文含 "热门" → 0.8
        self.assertEqual(
            _intent_relevance("随便标题", "这篇文章介绍 热门 skills", "trending"),
            0.8,
        )

    def test_latest_signal_in_title(self):
        # intent=latest，标题含 "最新" → 1.0
        self.assertEqual(
            _intent_relevance("最新 Claude Code skills", "正文", "latest"),
            1.0,
        )

    def test_recommend_signal_in_title(self):
        # intent=recommend，标题含 "教程" → 1.0
        self.assertEqual(
            _intent_relevance("Claude Code skills 实战教程", "正文", "recommend"),
            1.0,
        )

    def test_domain_keyword_in_title(self):
        # 无 intent 信号，但标题含 "skill" → 0.6
        self.assertEqual(
            _intent_relevance("我的 skill 笔记", "正文无信号", "trending"),
            0.6,
        )

    def test_domain_keyword_in_content(self):
        # 无 intent 信号，但正文含 "mcp" → 0.4
        self.assertEqual(
            _intent_relevance("无关标题", "本文介绍 mcp 用法", "trending"),
            0.4,
        )

    def test_code_block_only(self):
        # 仅含代码块，无任何信号 → 0.3
        self.assertEqual(
            _intent_relevance("无关标题", "正文 ```\ncode\n```", "trending"),
            0.3,
        )

    def test_completely_irrelevant(self):
        # 无任何信号 → 0.0
        self.assertEqual(
            _intent_relevance("无关标题", "无关正文", "trending"),
            0.0,
        )

    def test_empty_intent_defaults_to_trending(self):
        # intent 为空 → 默认 trending，标题含 "推荐" → 1.0
        self.assertEqual(
            _intent_relevance("推荐 skills", "正文", ""),
            1.0,
        )


class TestRateArticle(unittest.TestCase):
    def test_blocked_no_snippet_returns_zero(self):
        """风控且无摘要 → 直接 0 分，不计算其他维度。"""
        r = rate_article(
            title="t", content="", url="https://mp.weixin.qq.com/s/x",
            intent="trending", blocked=True, has_snippet_fallback=False,
        )
        self.assertEqual(r["score"], 0)
        self.assertEqual(r["reason"], "blocked_no_snippet")
        self.assertEqual(r["breakdown"]["penalty"], -100)

    def test_blocked_with_snippet_gets_penalty(self):
        """风控但有摘要兜底 → 扣 15 分，但仍参与正常评分。"""
        r = rate_article(
            title="Claude Code skills 实战",
            content="摘要内容" * 100,  # >500 字符
            url="https://mp.weixin.qq.com/s/x",
            intent="trending",
            blocked=True, has_snippet_fallback=True,
        )
        self.assertEqual(r["reason"], "blocked_with_snippet")
        self.assertEqual(r["breakdown"]["penalty"], -15)
        # 总分不低于 0
        self.assertGreaterEqual(r["score"], 0)

    def test_long_content_with_code_scores_high(self):
        """长正文 + 代码块 + intent 信号命中 + 已知渠道 → 高分。"""
        r = rate_article(
            title="TOP 10 Claude Code skills 推荐",  # intent trending 信号 → 1.0
            content=_LONG_CONTENT_WITH_CODE,
            url="https://github.com/acme/repo",  # github weight=20
            intent="trending",
        )
        self.assertEqual(r["breakdown"]["content_length"], 20)
        self.assertEqual(r["breakdown"]["code_blocks"], 10)  # 2 个代码块 * 5
        self.assertEqual(r["breakdown"]["channel"], 20)      # github
        self.assertGreaterEqual(r["score"], 50)

    def test_short_content_scores_zero_on_length(self):
        """正文 <500 字符 → content_length 维度得 0 分。"""
        r = rate_article(
            title="短文章",
            content="太短了",
            url="https://zhihu.com/x",
            intent="trending",
        )
        self.assertEqual(r["breakdown"]["content_length"], 0)

    def test_content_length_linear(self):
        """500-2000 字符之间线性打分。"""
        # 1250 字符 → (1250-500)/1500 * 20 ≈ 10 分
        content = "x" * 1250
        r = rate_article(
            title="t", content=content,
            url="https://example.com/x", intent="trending",
        )
        self.assertEqual(r["breakdown"]["content_length"], 10)

    def test_code_blocks_capped_at_25(self):
        """代码块得分上限 25 分（6 个代码块 = 30，截断为 25）。"""
        content = "x" * 2000 + ("\n```\ncode\n```\n" * 6)
        r = rate_article(
            title="t", content=content,
            url="https://example.com/x", intent="trending",
        )
        self.assertEqual(r["breakdown"]["code_blocks"], 25)

    def test_unknown_channel_default_weight(self):
        """未匹配渠道域名 → 默认权重 10。"""
        # 清缓存以使用 mock
        with mock.patch.object(crawler_agent, "_channel_weight_cache", {}), \
             mock.patch.object(crawler_agent, "_load_channel_weights", return_value={}):
            r = rate_article(
                title="t", content="x" * 2000,
                url="https://unknown-domain-xyz.com/x", intent="trending",
            )
        self.assertEqual(r["breakdown"]["channel"], 10)

    def test_score_never_negative(self):
        """总分不会为负（max(0, ...) 兜底）。"""
        # 风控有摘要但其他维度全 0 → penalty=-15，总分应为 0
        r = rate_article(
            title="t", content="短",
            url="https://unknown-domain-xyz.com/x",
            intent="trending",
            blocked=True, has_snippet_fallback=True,
        )
        self.assertGreaterEqual(r["score"], 0)


class TestRateArticleThresholdFilter(unittest.TestCase):
    """模拟 run_task 中的阈值过滤逻辑：低于 min_rating 的文章跳过。"""

    def test_low_rating_filtered(self):
        r = rate_article(
            title="无关标题", content="短内容",
            url="https://example.com/x", intent="trending",
        )
        # 评级低 → 应被过滤
        min_rating = 40
        self.assertLess(r["score"], min_rating)

    def test_high_rating_passes(self):
        r = rate_article(
            title="TOP 10 Claude Code skills 推荐",  # intent trending 信号
            content=_LONG_CONTENT_WITH_CODE,
            url="https://github.com/acme/repo",
            intent="trending",
        )
        # 评级高 → 应通过
        min_rating = 40
        self.assertGreaterEqual(r["score"], min_rating)


if __name__ == "__main__":
    unittest.main()
