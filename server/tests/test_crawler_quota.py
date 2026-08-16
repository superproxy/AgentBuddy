"""Crawler 每日配额逻辑测试（临时目录，不依赖网络与真实状态文件）。

覆盖：
- 当日无状态 → 全额配额
- 当日已发布 N → 剩余 quota-N
- 跨天 → 状态自动重置
- 状态文件读写 round-trip
- run_daily 配额已满时直接跳过（不触达源）
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import PluginMarketWorker as crawler  # noqa: E402


class TestDailyQuota(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp.name) / "crawler-state.json"
        patcher = mock.patch.object(crawler, "STATE_FILE", self.state_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_day_full_quota(self):
        p = crawler.get_daily_progress()
        self.assertEqual(p["published"], 0)
        self.assertEqual(p["remaining"], 10)
        self.assertEqual(p["quota"], 10)

    def test_partial_progress(self):
        crawler.save_state({"date": crawler._today(), "published": 4})
        p = crawler.get_daily_progress()
        self.assertEqual(p["published"], 4)
        self.assertEqual(p["remaining"], 6)

    def test_over_quota_clamped(self):
        crawler.save_state({"date": crawler._today(), "published": 12})
        p = crawler.get_daily_progress()
        self.assertEqual(p["remaining"], 0)

    def test_state_roundtrip(self):
        state = {"date": "2026-08-16", "published": 7, "last_run": "x"}
        crawler.save_state(state)
        self.assertEqual(crawler.load_state(), state)

    def test_corrupt_state_treated_as_empty(self):
        self.state_file.write_text("{not json", encoding="utf-8")
        self.assertEqual(crawler.load_state(), {})

    def test_run_daily_quota_full_skips(self):
        """配额已满：不触达 CrawlerAgent/BuildAgent，stopped_reason=quota_reached。"""
        crawler.save_state({"date": crawler._today(), "published": 10})
        with mock.patch("crawler_agent.run_task") as ct, \
             mock.patch("build_agent.run") as br:
            r = crawler.run_daily(quota=10)
        ct.assert_not_called()
        br.assert_not_called()
        self.assertEqual(r["stopped_reason"], "quota_reached")
        self.assertEqual(r["published"], 0)

    def test_run_daily_stops_at_quota(self):
        """发布满配额即停：CrawlerAgent 产出 spec，BuildAgent 受 max_publish 限流。

        新架构：run_daily 串联 CrawlerAgent + BuildAgent，BuildAgent 收到
        max_publish=今日剩余配额，发布满即停。这里 mock 两个智能体，验证
        传递给 BuildAgent 的 max_publish 与状态持久化。
        """
        from build_agent import BuildResult
        from crawler_agent import CrawlResult

        # CrawlerAgent 产出 4 个 spec（模拟 4 篇文章）
        fake_crawl = [CrawlResult(url=f"https://x/{i}", title=f"t{i}",
                                  status="spec", rating=60) for i in range(4)]
        # BuildAgent 发布满 max_publish 个即停（max_publish=2 → 发布 2 个）
        fake_build = [BuildResult(spec_path=f"/tmp/s{i}.yaml", plugin_name=f"p{i}",
                                  status="published") for i in range(2)]

        with mock.patch.object(crawler, "load_tasks", return_value=[
                {"name": "t", "topic": "x", "enabled": True, "channels": ["wechat"]}
             ]), \
             mock.patch.object(crawler, "load_channels", return_value=[
                {"id": "wechat", "domain": "mp.weixin.qq.com", "weight": 5}
             ]), \
             mock.patch("crawler_agent.require_env"), \
             mock.patch("crawler_agent.run_task", return_value=fake_crawl), \
             mock.patch("build_agent.run", return_value=fake_build) as br:
            r = crawler.run_daily(quota=2)

        self.assertEqual(r["published"], 2)
        self.assertEqual(r["stopped_reason"], "quota_reached")
        # 传递给 BuildAgent 的 max_publish 应等于剩余配额 2
        _, kwargs = br.call_args
        self.assertEqual(kwargs.get("max_publish"), 2)
        # 状态持久化今日发布数
        self.assertEqual(crawler.load_state().get("published"), 2)

    def test_run_daily_force_resets_count(self):
        """force=True 忽略今日已发布计数重新计额。"""
        from build_agent import BuildResult
        from crawler_agent import CrawlResult

        crawler.save_state({"date": crawler._today(), "published": 10})
        fake_crawl = [CrawlResult(url="https://x/0", title="t0", status="spec", rating=60)]
        fake_build = [BuildResult(spec_path="/tmp/s0.yaml", plugin_name="p0",
                                  status="published")]

        with mock.patch.object(crawler, "load_tasks", return_value=[
                {"name": "t", "topic": "x", "enabled": True, "channels": ["wechat"]}
             ]), \
             mock.patch.object(crawler, "load_channels", return_value=[
                {"id": "wechat", "domain": "mp.weixin.qq.com", "weight": 5}
             ]), \
             mock.patch("crawler_agent.require_env"), \
             mock.patch("crawler_agent.run_task", return_value=fake_crawl), \
             mock.patch("build_agent.run", return_value=fake_build):
            r = crawler.run_daily(quota=1, force=True)
        self.assertEqual(r["published"], 1)
        # force 后状态重置为 0 再累加本次发布数
        self.assertEqual(crawler.load_state().get("published"), 1)


if __name__ == "__main__":
    unittest.main()
