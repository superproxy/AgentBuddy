import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.llm import build_proxy_model_list, flatten_env_config


class CodexProxyRouteTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "llm": {
                "_active_provider": "openicu",
                "_active_protocol": "responses",
                "openicu": {
                    "responses": {
                        "base_url": "https://openrouter.icu/v1",
                        "api_key": "${OPENICU_API_KEY}",
                        "models": {"gpt-5.5": {"name": "GPT 5.5"}},
                    }
                },
            },
            "ide": {
                "codex": {
                    "model": "gpt-5.4",
                    "route": {
                        "provider": "openicu",
                        "protocol": "responses",
                        "upstream_model": "gpt-5.5",
                    },
                }
            },
            "proxy": {
                "codex": {
                    "enabled": True,
                    "base_url": "http://127.0.0.1:4000/v1",
                }
            },
        }

    def test_enabled_codex_proxy_overrides_codex_url_and_model(self):
        flat = flatten_env_config(self.config, "openicu", ["responses"])

        self.assertEqual(flat["LLM_CODEX_BASE_URL"], "http://127.0.0.1:4000/v1")
        self.assertEqual(flat["LLM_ACTIVE_BASE_URL"], "http://127.0.0.1:4000/v1")
        self.assertEqual(flat["OPENAI_MODEL"], "gpt-5.4")

    def test_route_builds_one_proxy_model_mapping(self):
        model_list = build_proxy_model_list(self.config)

        self.assertIn('model_name: "gpt-5.4"', model_list)
        self.assertIn('model: "gpt-5.5"', model_list)
        self.assertIn('api_base: "https://openrouter.icu/v1"', model_list)

    def test_proxy_codex_listen_params_default_to_localhost_4000(self):
        flat = flatten_env_config(self.config, "openicu", ["responses"])
        # proxy.codex 的监听参数应出现在 flat 中，供启动端点读取
        self.assertEqual(flat.get("PROXY_CODEX_LISTEN_HOST", "127.0.0.1"), "127.0.0.1")
        self.assertEqual(flat.get("PROXY_CODEX_LISTEN_PORT", 4000), 4000)


if __name__ == "__main__":
    unittest.main()
