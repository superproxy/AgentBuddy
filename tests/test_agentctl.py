"""agentctl 测试套件。

迁移自 tests/test_init_env.py 和 tests/test_plugin_manager.py，
改为导入 scripts/lib/ 下的模块（替代直接导入旧脚本）。

测试覆盖：
- FlattenEnvConfigTests: llm.flatten_env_config 行为（迁移自 test_init_env）
- SkillsFilterTests: skills.copy_skills_safe 白名单过滤（新增）
"""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

# 将 scripts/ 加入 sys.path 以导入 lib 包
SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib import llm, skills, plugins
from lib import provider_catalog


class FlattenEnvConfigTests(unittest.TestCase):
    """迁移自 test_init_env.py，验证 llm.flatten_env_config 行为不变。"""

    def test_vision_flat_provider_exports_default_model(self):
        env_config = {
            "vision": {
                "volcengine": {
                    "base_url": "https://example.invalid/api",
                    "api_key": "test-key",
                    "models": {
                        "doubao-seedance-2-0-fast-260128": {
                            "name": "Seedance fast"
                        }
                    },
                }
            }
        }

        flat = llm.flatten_env_config(env_config, "", [])

        self.assertEqual(
            flat["VISION_VOLCENGINE_MODEL"],
            "doubao-seedance-2-0-fast-260128",
        )


class SkillsFilterTests(unittest.TestCase):
    """新增：验证 skills.copy_skills_safe 的白名单过滤。"""

    def test_include_skills_filters_copy(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "src"
            src.mkdir()
            (src / "keep").mkdir()
            (src / "keep" / "SKILL.md").write_text("x")
            (src / "skip").mkdir()
            (src / "skip" / "SKILL.md").write_text("y")
            dst = pathlib.Path(td) / "dst"

            skills.copy_skills_safe(src, dst, "test", True, include_skills={"keep"})

            self.assertTrue((dst / "keep").exists())
            self.assertFalse((dst / "skip").exists())

    def test_include_skills_none_copies_all(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "src"
            src.mkdir()
            (src / "a").mkdir()
            (src / "a" / "SKILL.md").write_text("a")
            (src / "b").mkdir()
            (src / "b" / "SKILL.md").write_text("b")
            dst = pathlib.Path(td) / "dst"

            skills.copy_skills_safe(src, dst, "test", True, include_skills=None)

            self.assertTrue((dst / "a").exists())
            self.assertTrue((dst / "b").exists())


class ProviderCatalogTests(unittest.TestCase):
    """Provider Catalog / Detect / Apply 管道。"""

    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        cls.example = root / "template" / "llm" / "llm-env-example.yaml"
        cls.catalog = provider_catalog.load_provider_catalog(cls.example)

    def test_catalog_loads_known_providers(self):
        names = {c["provider"] for c in self.catalog}
        self.assertIn("bigmodel", names)
        self.assertIn("bigmodelCoding", names)
        self.assertIn("openrouter", names)
        self.assertIn("anthropic", names)
        big = next(c for c in self.catalog if c["provider"] == "bigmodel")
        self.assertIn("openai", big["protocols"])
        self.assertTrue(big["protocols"]["openai"]["base_url"])

    def test_fingerprint_openai_proj(self):
        fp = provider_catalog.classify_api_key("sk-proj-" + "A" * 40)
        self.assertEqual(fp["id"], "openai_proj")
        self.assertTrue(fp["unique"])

    def test_fingerprint_anthropic_api03(self):
        fp = provider_catalog.classify_api_key("sk-ant-api03-" + "A" * 40)
        self.assertEqual(fp["id"], "anthropic")

    def test_fingerprint_openrouter(self):
        fp = provider_catalog.classify_api_key("sk-or-v1-" + "abc123def456")
        self.assertEqual(fp["id"], "openrouter")

    def test_fingerprint_zhipu(self):
        fp = provider_catalog.classify_api_key("a" * 32 + "." + "B" * 16)
        self.assertEqual(fp["id"], "zhipu_zai")
        self.assertFalse(fp["unique"])

    def test_fingerprint_dashscope_coding(self):
        fp = provider_catalog.classify_api_key("sk-sp-abcdef123456")
        self.assertEqual(fp["id"], "dashscope_coding")

    def test_detect_sk_ant_unique(self):
        key = "sk-ant-api03-" + "x" * 40
        hits = provider_catalog.detect_providers(key, catalog=self.catalog, probe=False)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["provider"], "anthropic")
        self.assertEqual(hits[0]["detected_protocol"], "anthropic")

    def test_detect_sk_or_unique(self):
        hits = provider_catalog.detect_providers(
            "sk-or-v1-abcdef123456", catalog=self.catalog, probe=False,
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["provider"], "openrouter")

    def test_detect_sk_proj_unique(self):
        hits = provider_catalog.detect_providers(
            "sk-proj-" + "A" * 40, catalog=self.catalog, probe=False,
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["provider"], "openai")

    def test_detect_zhipu_family_without_probe(self):
        key = "a" * 32 + "." + "B" * 16
        hits = provider_catalog.detect_providers(key, catalog=self.catalog, probe=False)
        names = {h["provider"] for h in hits}
        self.assertTrue(names & {"bigmodel", "zai", "bigmodelCoding", "zaiCoding"})
        self.assertNotIn("openai", names)
        self.assertNotIn("openrouter", names)

    def test_detect_bigmodel_coding_url(self):
        hits = provider_catalog.detect_providers(
            "sk-xxx",
            "https://open.bigmodel.cn/api/coding/paas/v4",
            catalog=self.catalog,
            probe=False,
        )
        self.assertEqual(hits[0]["provider"], "bigmodelCoding")

    def test_detect_volcengine_exact_endpoint(self):
        """精确匹配 catalog 端点时直接锁定，不再展开家族。"""
        hits = provider_catalog.detect_providers(
            "sk-xxx",
            "https://ark.cn-beijing.volces.com/api/v3",
            catalog=self.catalog,
            probe=False,
        )
        self.assertEqual(hits[0]["provider"], "volcengine")
        self.assertEqual(hits[0]["detected_protocol"], "openai")
        self.assertEqual(len(hits), 1)

    def test_detect_volcengine_family_ambiguous(self):
        """URL 仅命中域名、未精确到 catalog 端点时展开家族。"""
        hits = provider_catalog.detect_providers(
            "sk-xxx",
            "https://ark.cn-beijing.volces.com/",
            catalog=self.catalog,
            probe=False,
        )
        names = [h["provider"] for h in hits]
        self.assertIn("volcengine", names)
        self.assertGreaterEqual(len(hits), 2)

    def test_detect_generic_sk_limited_candidates(self):
        """通用 sk- 不再甩全量厂商列表，候选应精简。"""
        hits = provider_catalog.detect_providers(
            "sk-generic-key-abcdefgh", catalog=self.catalog, probe=False,
        )
        self.assertGreaterEqual(len(hits), 1)
        self.assertLessEqual(len(hits), 6)
        names = {h["provider"] for h in hits}
        self.assertNotIn("anthropic", names)  # 有专属指纹，不应混入

    def test_apply_writes_key_and_active(self):
        env = {"llm": {}}
        cand = next(c for c in self.catalog if c["provider"] == "deepseek")
        cand = {**cand, "score": 100, "reason": "test", "detected_protocol": "openai"}
        applied = provider_catalog.apply_provider_to_env(env, cand, "sk-test")
        self.assertEqual(applied["provider"], "deepseek")
        self.assertEqual(env["llm"]["_active_provider"], "deepseek")
        self.assertEqual(env["llm"]["_active_protocol"], "openai")
        self.assertEqual(env["llm"]["deepseek"]["openai"]["api_key"], "sk-test")
        self.assertTrue(env["llm"]["deepseek"]["openai"]["base_url"])

    def test_detect_protocol_from_anthropic_url(self):
        hits = provider_catalog.detect_providers(
            "sk-xxx",
            "https://open.bigmodel.cn/api/anthropic",
            catalog=self.catalog,
            probe=False,
        )
        self.assertEqual(hits[0]["provider"], "bigmodel")
        self.assertEqual(hits[0]["detected_protocol"], "anthropic")
        self.assertEqual(hits[0]["active_protocol"], "anthropic")

    def test_detect_protocol_from_sk_ant(self):
        key = "sk-ant-api03-" + "y" * 40
        hits = provider_catalog.detect_providers(key, catalog=self.catalog, probe=False)
        self.assertEqual(hits[0]["detected_protocol"], "anthropic")

    def test_detect_protocol_from_openai_path(self):
        hits = provider_catalog.detect_providers(
            "sk-xxx",
            "https://open.bigmodel.cn/api/paas/v4",
            catalog=self.catalog,
            probe=False,
        )
        self.assertEqual(hits[0]["provider"], "bigmodel")
        self.assertEqual(hits[0]["detected_protocol"], "openai")

    def test_detect_endpoint_exact_match(self):
        hits = provider_catalog.detect_providers(
            "sk-xxx",
            "https://api.z.ai/api/coding/paas/v4",
            catalog=self.catalog,
            probe=False,
        )
        self.assertEqual(hits[0]["provider"], "zaiCoding")
        self.assertEqual(hits[0]["detected_protocol"], "openai")

    def test_infer_protocol_openrouter_anthropic_path(self):
        proto, _ = provider_catalog.infer_protocol(
            "sk-or-xxx",
            "https://openrouter.ai/api",
            {"openai": {}, "anthropic": {}},
        )
        self.assertEqual(proto, "anthropic")

    def test_key_only_auto_fills_base_url(self):
        """只输 Key 时，候选应带上 catalog 默认 Base URL。"""
        key = "sk-ant-api03-" + "z" * 40
        hits = provider_catalog.detect_providers(key, catalog=self.catalog, probe=False)
        self.assertEqual(hits[0]["provider"], "anthropic")
        url = hits[0]["protocols"]["anthropic"]["base_url"]
        self.assertTrue(url, "catalog 应提供默认 base_url")
        env = {"llm": {}}
        applied = provider_catalog.apply_provider_to_env(env, hits[0], key)
        self.assertEqual(applied["base_url"], url)
        self.assertEqual(env["llm"]["anthropic"]["anthropic"]["base_url"], url)

    def test_apply_without_override_keeps_catalog_url(self):
        env = {"llm": {}}
        cand = next(c for c in self.catalog if c["provider"] == "openrouter")
        cand = {**cand, "detected_protocol": "openai", "score": 100, "reason": "test"}
        catalog_url = cand["protocols"]["openai"]["base_url"]
        applied = provider_catalog.apply_provider_to_env(
            env, cand, "sk-or-test", base_url_override="",
        )
        self.assertEqual(applied["base_url"], catalog_url)
        self.assertEqual(env["llm"]["openrouter"]["openai"]["base_url"], catalog_url)

    def test_catalog_official_base_urls(self):
        """官方厂商 catalog URL 必须是可探测的权威域名。"""
        openai = next(c for c in self.catalog if c["provider"] == "openai")
        self.assertIn("api.openai.com", openai["protocols"]["openai"]["base_url"])
        anthropic = next(c for c in self.catalog if c["provider"] == "anthropic")
        self.assertIn("api.anthropic.com", anthropic["protocols"]["anthropic"]["base_url"])
        deepseek = next(c for c in self.catalog if c["provider"] == "deepseek")
        self.assertIn("api.deepseek.com", deepseek["protocols"]["openai"]["base_url"])

    def test_probe_endpoints_prefer_authoritative_urls(self):
        openai_urls = provider_catalog._probe_urls_for_provider("openai")
        self.assertEqual(openai_urls[0][0], "https://api.openai.com/v1")
        moon_urls = [u for u, _ in provider_catalog._probe_urls_for_provider("moonshot")]
        self.assertIn("https://api.moonshot.ai/v1", moon_urls)
        self.assertIn("https://api.moonshot.cn/v1", moon_urls)

    def test_fingerprint_deepseek_hex_exact_32(self):
        fp = provider_catalog.classify_api_key("sk-" + "a" * 32)
        self.assertEqual(fp["id"], "deepseek_hex")
        # 超过 32 hex → 走 generic_sk，避免误锁 DeepSeek
        fp_long = provider_catalog.classify_api_key("sk-" + "a" * 40)
        self.assertEqual(fp_long["id"], "generic_sk")
        fp_alnum = provider_catalog.classify_api_key("sk-abcdefABCDEF1234567890xy")
        self.assertEqual(fp_alnum["id"], "generic_sk")

    def test_score_model_signature(self):
        self.assertEqual(
            provider_catalog.score_model_signature("deepseek", ["deepseek-chat"]), 15,
        )
        self.assertEqual(
            provider_catalog.score_model_signature("openai", ["gpt-4o-mini"]), 15,
        )
        self.assertEqual(
            provider_catalog.score_model_signature("deepseek", ["gpt-4o"]), -5,
        )
        self.assertEqual(
            provider_catalog.score_model_signature("openai", []), 0,
        )

    def test_rank_probe_hits_unique_lock(self):
        locked = provider_catalog.rank_probe_hits([
            ("deepseek", "openai", 100),
            ("openai", "openai", 85),
            ("moonshot", "openai", 85),
        ])
        self.assertEqual(len(locked), 1)
        self.assertEqual(locked[0][0], "deepseek")
        # 分差不足 → 保留多候选
        multi = provider_catalog.rank_probe_hits([
            ("deepseek", "openai", 100),
            ("openai", "openai", 98),
        ])
        self.assertEqual(len(multi), 2)

    def test_needs_choice_threshold(self):
        self.assertFalse(provider_catalog.needs_choice_for_candidates([{"score": 100}]))
        self.assertFalse(provider_catalog.needs_choice_for_candidates([
            {"score": 100}, {"score": 85},
        ]))
        self.assertTrue(provider_catalog.needs_choice_for_candidates([
            {"score": 100}, {"score": 98},
        ]))
        self.assertTrue(provider_catalog.needs_choice_for_candidates([
            {"score": 85}, {"score": 55},
        ]))

    def test_host_match_no_path_false_positive(self):
        """path 含厂商关键词不应误匹配；host 才算。"""
        self.assertFalse(provider_catalog._host_matches("example.com", "moonshot"))
        self.assertTrue(provider_catalog._host_matches("api.moonshot.ai", "moonshot"))
        self.assertTrue(provider_catalog._host_matches("api.moonshot.cn", "moonshot"))
        rule = next(r for r in provider_catalog.DETECT_RULES if r["provider"] == "moonshot")
        self.assertFalse(
            provider_catalog._url_match("https://example.com/docs/moonshot-api", rule),
        )
        self.assertTrue(
            provider_catalog._url_match("https://api.moonshot.cn/v1", rule),
        )

    def test_probe_signature_locks_deepseek(self):
        """鉴权 200 + 模型签名命中 → 唯一锁定 deepseek。"""
        def fake_probe(api_key, base_url, protocol="openai"):
            if "deepseek.com" in base_url:
                return {
                    "ok": True, "status": 200,
                    "model_ids": ["deepseek-chat", "deepseek-reasoner"],
                }
            return {"ok": False, "status": 401, "error": "auth_failed", "model_ids": []}

        key = "sk-" + "b" * 32
        with mock.patch.object(provider_catalog, "probe_endpoint", side_effect=fake_probe):
            hits = provider_catalog.detect_providers(key, catalog=self.catalog, probe=True)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["provider"], "deepseek")
        self.assertGreaterEqual(hits[0]["score"], 95)
        self.assertFalse(provider_catalog.needs_choice_for_candidates(hits))

    def test_probe_signature_locks_openai(self):
        def fake_probe(api_key, base_url, protocol="openai"):
            if "api.openai.com" in base_url:
                return {"ok": True, "status": 200, "model_ids": ["gpt-4o", "o1-mini"]}
            return {"ok": False, "status": 401, "error": "auth_failed", "model_ids": []}

        key = "sk-generic-openai-key-abcdefgh"
        with mock.patch.object(provider_catalog, "probe_endpoint", side_effect=fake_probe):
            hits = provider_catalog.detect_providers(key, catalog=self.catalog, probe=True)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["provider"], "openai")

    def test_probe_dual_success_ranks_by_signature(self):
        """双端点都 200 时，签名命中者排前并可唯一锁定。"""
        def fake_probe(api_key, base_url, protocol="openai"):
            if "deepseek.com" in base_url:
                return {"ok": True, "status": 200, "model_ids": ["deepseek-chat"]}
            if "api.openai.com" in base_url:
                # 鉴权通但无 OpenAI 签名模型（空列表 → 基分 85）
                return {"ok": True, "status": 200, "model_ids": []}
            return {"ok": False, "status": 403, "error": "auth_failed", "model_ids": []}

        key = "sk-" + "c" * 32
        with mock.patch.object(provider_catalog, "probe_endpoint", side_effect=fake_probe):
            hits = provider_catalog.detect_providers(key, catalog=self.catalog, probe=True)
        self.assertEqual(hits[0]["provider"], "deepseek")
        self.assertEqual(len(hits), 1)


if __name__ == "__main__":
    unittest.main()
