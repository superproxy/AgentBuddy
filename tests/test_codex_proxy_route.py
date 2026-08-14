import pathlib
import unittest

from agentctl.lib.llm import build_proxy_model_list, flatten_env_config


class GatewayRouteTests(unittest.TestCase):
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
                    },
                    "openai": {
                        "base_url": "https://openrouter.icu/v1",
                        "api_key": "sk-openai-key",
                        "models": {"gpt-5.5": {"name": "GPT 5.5"}},
                    },
                },
            },
            "proxy": {
                "gateway": {
                    "enabled": True,
                    "base_url": "http://127.0.0.1:4000/v1",
                    "routes": [
                        {
                            "enabled": True,
                            "provider": "openicu",
                            "protocol": "responses",
                            "upstream_model": "gpt-5.5",
                            "gateway_model": "gpt-5.4",
                        },
                        {
                            "enabled": True,
                            "provider": "openicu",
                            "protocol": "openai",
                            "upstream_model": "gpt-5.5",
                            "gateway_model": "gpt-5.5",
                        },
                        {
                            "enabled": False,
                            "provider": "openicu",
                            "protocol": "anthropic",
                            "upstream_model": "claude-sonnet-5",
                            "gateway_model": "claude-sonnet-5",
                        },
                    ],
                }
            },
        }

    def test_enabled_gateway_overrides_base_url(self):
        flat = flatten_env_config(self.config, "openicu", ["responses"])
        self.assertEqual(flat["LLM_ACTIVE_BASE_URL"], "http://127.0.0.1:4000/v1")
        self.assertEqual(flat["LLM_CODEX_BASE_URL"], "http://127.0.0.1:4000/v1")
        self.assertEqual(flat["LLM_ACTIVE_PROVIDER"], "agentbuddy-gateway")
        self.assertEqual(flat["OPENAI_MODEL"], "gpt-5.4")

    def test_gateway_builds_multiple_routes(self):
        model_list = build_proxy_model_list(self.config)
        # 两条启用的路由
        self.assertIn('model_name: "gpt-5.4"', model_list)
        self.assertIn('model: "gpt-5.5"', model_list)
        self.assertIn('model_name: "gpt-5.5"', model_list)
        # 禁用的路由不出现
        self.assertNotIn("claude-sonnet-5", model_list)

    def test_custom_route_with_explicit_base_url(self):
        config = {
            "llm": {},
            "proxy": {
                "gateway": {
                    "enabled": True,
                    "routes": [
                        {
                            "enabled": True,
                            "provider": "custom",
                            "protocol": "openai",
                            "upstream_model": "my-model",
                            "gateway_model": "my-model",
                            "base_url": "https://my-custom.com/v1",
                            "api_key": "sk-custom",
                        }
                    ],
                }
            },
        }
        model_list = build_proxy_model_list(config)
        self.assertIn('model_name: "my-model"', model_list)
        self.assertIn('api_base: "https://my-custom.com/v1"', model_list)
        self.assertIn('api_key: "sk-custom"', model_list)

    def test_disabled_gateway_falls_back_to_provider(self):
        config = dict(self.config)
        config["proxy"] = {"gateway": {"enabled": False, "routes": []}}
        flat = flatten_env_config(config, "openicu", ["responses"])
        self.assertNotEqual(flat.get("LLM_ACTIVE_BASE_URL"), "http://127.0.0.1:4000/v1")


if __name__ == "__main__":
    unittest.main()
