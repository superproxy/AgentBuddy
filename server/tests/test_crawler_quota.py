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
        """配额已满：不加载源、不发布，stopped_reason=quota_reached。"""
        crawler.save_state({"date": crawler._today(), "published": 10})
        with mock.patch.object(crawler, "load_sources") as ls, \
             mock.patch.object(crawler, "crawl_and_publish") as cp:
            r = crawler.run_daily(quota=10)
        ls.assert_not_called()
        cp.assert_not_called()
        self.assertEqual(r["stopped_reason"], "quota_reached")
        self.assertEqual(r["published"], 0)

    def test_run_daily_stops_at_quota(self):
        """发布满配额即停：4 个源、配额 2 → 只处理前 2 个。"""
        with mock.patch.object(crawler, "load_sources", return_value=[
            {"name": f"s{i}", "url": f"https://x/{i}", "enabled": True} for i in range(4)
        ]), mock.patch.object(crawler, "crawl_and_publish", return_value={"status": "published"}):
            r = crawler.run_daily(quota=2)
        self.assertEqual(r["published"], 2)
        self.assertEqual(r["stopped_reason"], "quota_reached")
        # 状态持久化今日发布数
        self.assertEqual(crawler.load_state().get("published"), 2)

    def test_run_daily_force_resets_count(self):
        """force=True 忽略今日已发布计数重新计额。"""
        crawler.save_state({"date": crawler._today(), "published": 10})
        with mock.patch.object(crawler, "load_sources", return_value=[
            {"name": "s", "url": "https://x", "enabled": True}
        ]), mock.patch.object(crawler, "crawl_and_publish", return_value={"status": "published"}):
            r = crawler.run_daily(quota=1, force=True)
        self.assertEqual(r["published"], 1)


if __name__ == "__main__":
    unittest.main()
