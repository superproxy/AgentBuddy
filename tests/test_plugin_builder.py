"""PluginBuilder 引擎纯函数回归测试（不依赖网络与 config/ 真实文件）。

覆盖场景：
- sanitize_name：kebab-case 清洗、长度截断（≤64）、非法字符剔除
- truncate_description：长度截断（≤500）、句/词边界收尾、省略号不超限
- _parse_skill_name_text / _parse_skill_description_text：
  - 标准 YAML frontmatter
  - 未加引号的 plain scalar 含 ": "（yaml.safe_load 抛 ScannerError）→ 逐行正则兜底
- _slugify："/" "_" 空格 均作分隔符（Qwen/MM_Plugins → qwen-mm-plugins）
"""
import unittest

from agentctl.lib.plugin_builder import (
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
    _parse_skill_description_text,
    _parse_skill_name_text,
    _slugify,
    sanitize_name,
    truncate_description,
)


class TestSanitizeName(unittest.TestCase):
    def test_kebab_from_slashes_and_underscores(self):
        self.assertEqual(sanitize_name("Qwen/MM_Plugins"), "qwen-mm-plugins")

    def test_lowercase_and_spaces(self):
        self.assertEqual(sanitize_name("  Hello World!  "), "hello-world")

    def test_non_ascii_falls_back_to_plugin(self):
        self.assertEqual(sanitize_name("插件测试"), "plugin")

    def test_length_capped_at_64(self):
        self.assertEqual(len(sanitize_name("a" * 200)), MAX_NAME_LENGTH)

    def test_no_leading_trailing_hyphen(self):
        n = sanitize_name("---weird-name---")
        self.assertEqual(n, "weird-name")


class TestTruncateDescription(unittest.TestCase):
    def test_short_passthrough(self):
        self.assertEqual(truncate_description("短描述"), "短描述")

    def test_sentence_boundary_preferred(self):
        text = "第一句。第二句。" * 100
        out = truncate_description(text)
        self.assertLessEqual(len(out), MAX_DESCRIPTION_LENGTH)
        self.assertTrue(out.endswith("。"))

    def test_no_separator_still_within_limit(self):
        # 修复点：加 "…" 后曾超限到 501
        out = truncate_description("a" * 600)
        self.assertLessEqual(len(out), MAX_DESCRIPTION_LENGTH)

    def test_word_boundary_fallback(self):
        out = truncate_description("word " * 300)
        self.assertLessEqual(len(out), MAX_DESCRIPTION_LENGTH)

    def test_exactly_at_limit_unchanged(self):
        text = "c" * MAX_DESCRIPTION_LENGTH
        self.assertEqual(truncate_description(text), text)

    def test_whitespace_flattened(self):
        out = truncate_description("a\n\nb\t\tc  d")
        self.assertEqual(out, "a b c d")


class TestSkillFrontmatterParsing(unittest.TestCase):
    def test_standard_frontmatter(self):
        text = "---\nname: qwen-mm-plugins-core\ndescription: Local MCP tools.\n---\n\n# Core\n"
        self.assertEqual(_parse_skill_name_text(text), "qwen-mm-plugins-core")
        self.assertEqual(_parse_skill_description_text(text), "Local MCP tools.")

    def test_quoted_description(self):
        text = '---\nname: x\ndescription: "Cloud tools: vision, OCR"\n---\n'
        self.assertEqual(_parse_skill_description_text(text), "Cloud tools: vision, OCR")

    def test_invalid_yaml_falls_back_to_line_regex(self):
        # 真实案例：qwen-mm-plugins 的 example/video-edit SKILL.md
        # 未加引号的 description 含 ": "，yaml.safe_load 抛 ScannerError
        text = (
            "---\n"
            "name: qwen-mm-plugins-example\n"
            "description: Example capability — shows how a capability is structured: "
            "the content-return shape\n"
            "---\n"
        )
        self.assertEqual(_parse_skill_name_text(text), "qwen-mm-plugins-example")
        desc = _parse_skill_description_text(text)
        self.assertTrue(desc.startswith("Example capability"))
        self.assertIn(": ", desc)

    def test_missing_name_returns_empty(self):
        text = "---\ndescription: only desc\n---\n"
        self.assertEqual(_parse_skill_name_text(text), "")

    def test_no_frontmatter_returns_empty_name(self):
        self.assertEqual(_parse_skill_name_text("# Just a heading\nbody"), "")


class TestSlugify(unittest.TestCase):
    def test_separator_chars(self):
        self.assertEqual(_slugify("Qwen/MM_Plugins"), "qwen-mm-plugins")
        self.assertEqual(_slugify("a b_c/d"), "a-b-c-d")

    def test_collapsed_hyphens(self):
        self.assertEqual(_slugify("a---b"), "a-b")


if __name__ == "__main__":
    unittest.main()
