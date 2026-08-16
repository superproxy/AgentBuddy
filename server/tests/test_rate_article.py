"""CrawlerAgent 文章评级函数 rate_article() 单元测试。

覆盖五个评分维度 + 风控惩罚 + 阈值过滤场景：
- content_length（20 分）：>2000 满分，500-2000 线性，<500 得 0
- code_blocks（25 分）：每个代码块 5 分，上限 25
- topic_relevance（25 分）：topic 关键词命中率 * 25
- channel（20 分）：渠道权重（0-20）
- penalty：风控无摘要直接 0 分；风控有摘要 -15
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crawler_agent  # noqa: E402
from crawler_agent import rate_article, _topic_relevance  # noqa: E402


# 构造一段足够长的正文（>2000 字符），含代码块，命中 topic 关键词
_LONG_CONTENT_WITH_CODE = (
    "# Claude Code Skills 实战\n\n"
    + "本文章介绍如何使用 Claude Code skills 进行自动化开发。" * 60  # 长度 >2000
    + "\n```python\nprint('hello')\n```\n"  # 1 个代码块 = 5 分
    + "\n```yaml\nname: demo\n```\n"        # 第 2 个代码块 = 5 分
)


class TestTopicRelevance(unittest.TestCase):
    def test_empty_topic_returns_zero(self):
        self.assertEqual(_topic_relevance("title", "content", ""), 0.0)

    def test_all_keywords_hit_returns_one(self):
        # topic 拆出 [claude, code, skills]，全部命中
        self.assertEqual(_topic_relevance("Claude Code skills", "any", "Claude Code skills"), 1.0)

    def test_partial_hit(self):
        # topic="Claude Code skills" → 3 个关键词，命中 2 个 → 2/3
        rel = _topic_relevance("Claude skills 实战", "正文", "Claude Code skills")
        self.assertAlmostEqual(rel, 2 / 3, places=2)

    def test_short_keywords_filtered(self):
        # 长度 <2 的关键词被过滤（如 "a"）
        rel = _topic_relevance("a b Claude", "正文", "a b Claude")
        # 只有 claude 算关键词，且命中 → 1.0
        self.assertEqual(rel, 1.0)


class TestRateArticle(unittest.TestCase):
    def test_blocked_no_snippet_returns_zero(self):
        """风控且无摘要 → 直接 0 分，不计算其他维度。"""
        r = rate_article(
            title="t", content="", url="https://mp.weixin.qq.com/s/x",
            topic="Claude Code skills", blocked=True, has_snippet_fallback=False,
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
            topic="Claude Code skills",
            blocked=True, has_snippet_fallback=True,
        )
        self.assertEqual(r["reason"], "blocked_with_snippet")
        self.assertEqual(r["breakdown"]["penalty"], -15)
        # 总分不低于 0
        self.assertGreaterEqual(r["score"], 0)

    def test_long_content_with_code_scores_high(self):
        """长正文 + 代码块 + topic 命中 + 已知渠道 → 高分。"""
        r = rate_article(
            title="Claude Code skills 实战",
            content=_LONG_CONTENT_WITH_CODE,
            url="https://github.com/acme/repo",  # github weight=20
            topic="Claude Code skills",
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
            topic="Claude",
        )
        self.assertEqual(r["breakdown"]["content_length"], 0)

    def test_content_length_linear(self):
        """500-2000 字符之间线性打分。"""
        # 1250 字符 → (1250-500)/1500 * 20 ≈ 10 分
        content = "x" * 1250
        r = rate_article(
            title="t", content=content,
            url="https://example.com/x", topic="t",
        )
        self.assertEqual(r["breakdown"]["content_length"], 10)

    def test_code_blocks_capped_at_25(self):
        """代码块得分上限 25 分（6 个代码块 = 30，截断为 25）。"""
        content = "x" * 2000 + ("\n```\ncode\n```\n" * 6)
        r = rate_article(
            title="t", content=content,
            url="https://example.com/x", topic="t",
        )
        self.assertEqual(r["breakdown"]["code_blocks"], 25)

    def test_unknown_channel_default_weight(self):
        """未匹配渠道域名 → 默认权重 10。"""
        # 清缓存以使用 mock
        with mock.patch.object(crawler_agent, "_channel_weight_cache", {}), \
             mock.patch.object(crawler_agent, "_load_channel_weights", return_value={}):
            r = rate_article(
                title="t", content="x" * 2000,
                url="https://unknown-domain-xyz.com/x", topic="t",
            )
        self.assertEqual(r["breakdown"]["channel"], 10)

    def test_score_never_negative(self):
        """总分不会为负（max(0, ...) 兜底）。"""
        # 风控有摘要但其他维度全 0 → penalty=-15，总分应为 0
        r = rate_article(
            title="t", content="短",
            url="https://unknown-domain-xyz.com/x",
            topic="t",
            blocked=True, has_snippet_fallback=True,
        )
        self.assertGreaterEqual(r["score"], 0)


class TestRateArticleThresholdFilter(unittest.TestCase):
    """模拟 run_task 中的阈值过滤逻辑：低于 min_rating 的文章跳过。"""

    def test_low_rating_filtered(self):
        r = rate_article(
            title="无关标题", content="短内容",
            url="https://example.com/x", topic="完全无关的话题 xyz",
        )
        # 评级低 → 应被过滤
        min_rating = 40
        self.assertLess(r["score"], min_rating)

    def test_high_rating_passes(self):
        r = rate_article(
            title="Claude Code skills 实战",
            content=_LONG_CONTENT_WITH_CODE,
            url="https://github.com/acme/repo",
            topic="Claude Code skills",
        )
        # 评级高 → 应通过
        min_rating = 40
        self.assertGreaterEqual(r["score"], min_rating)


if __name__ == "__main__":
    unittest.main()
