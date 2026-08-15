"""默认 LLM 源校验回归测试（纯函数，不依赖网络与 config/ 真实文件）。

覆盖场景（对应事故：默认 Provider 被禁用后 sync/装插件持续报错）：
- 网关启用 + 无默认 Provider → 合法（互斥规则）
- 网关与默认 Provider 同时启用 / 都未选 → 报错（互斥规则）
- 默认 Provider 不存在 / _enabled: false → 报错（本次事故的直接原因）
- 默认 Provider 存在且启用 + 无默认模型 → 报错
- 全部合法 → 通过
"""
import unittest

from agentctl.lib.llm import validate_default_llm


def _cfg(active_provider="", active_model="", gateway=False, providers=None):
    llm: dict = {}
    if active_provider:
        llm["_active_provider"] = active_provider
    if active_model:
        llm["_active_model"] = active_model
    for name, enabled in (providers or {}).items():
        llm[name] = {"_enabled": enabled, "openai": {"base_url": "https://x", "api_key": "sk-test"}}
    return {
        "llm": llm,
        "proxy": {"gateway": {"enabled": gateway}},
    }


class TestValidateDefaultLLM(unittest.TestCase):
    def test_gateway_only_ok(self):
        self.assertIsNone(validate_default_llm(_cfg(gateway=True, active_model="m1")))

    def test_provider_only_ok(self):
        cfg = _cfg(active_provider="p1", active_model="m1", providers={"p1": True})
        self.assertIsNone(validate_default_llm(cfg))

    def test_both_selected_rejected(self):
        cfg = _cfg(active_provider="p1", active_model="m1", gateway=True, providers={"p1": True})
        err = validate_default_llm(cfg)
        self.assertIsNotNone(err)
        self.assertIn("只能选择一个", err)

    def test_neither_selected_rejected(self):
        err = validate_default_llm(_cfg())
        self.assertIsNotNone(err)
        self.assertIn("只能选择一个", err)

    def test_active_provider_disabled_rejected(self):
        """本次事故：默认 Provider 被禁用。"""
        cfg = _cfg(active_provider="volcengineAgent", active_model="Kimi-k3",
                   providers={"volcengineAgent": False})
        err = validate_default_llm(cfg)
        self.assertIsNotNone(err)
        self.assertIn("volcengineAgent", err)
        self.assertIn("未启用", err)

    def test_active_provider_missing_rejected(self):
        cfg = _cfg(active_provider="ghost", active_model="m1", providers={"p1": True})
        err = validate_default_llm(cfg)
        self.assertIsNotNone(err)
        self.assertIn("ghost", err)

    def test_no_model_rejected(self):
        cfg = _cfg(active_provider="p1", providers={"p1": True})
        err = validate_default_llm(cfg)
        self.assertIsNotNone(err)
        self.assertIn("默认模型", err)

    def test_enabled_none_treated_as_enabled(self):
        """_enabled 缺失（默认 True）不误报——只拦显式 False。"""
        cfg = _cfg(active_provider="p1", active_model="m1")
        cfg["llm"]["p1"] = {"openai": {"base_url": "https://x", "api_key": "sk-t"}}
        self.assertIsNone(validate_default_llm(cfg))

    def test_non_dict_input_safe(self):
        self.assertIsNotNone(validate_default_llm(None))
        self.assertIsNotNone(validate_default_llm({}))


if __name__ == "__main__":
    unittest.main()
