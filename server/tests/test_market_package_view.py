"""市场 zip 能解析出原文地址和技能正文。"""
import io
import unittest
import zipfile

from marketplace.package_view import inspect_zip_bytes


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


class MarketPackageViewTest(unittest.TestCase):
    def test_homepage_and_ai_extracted_source(self):
        raw = _zip({
            "demo.plugin.yaml": (
                "name: demo\n"
                "description: 从文章抽出来的技能\n"
                "homepage: https://example.com/article\n"
                "skills:\n"
                "  - name: review\n"
                "    description: 审查改动\n"
                "    source: ai-extracted:https://example.com/article\n"
                "    body: 先看 diff\n"
            ),
        })
        viewed = inspect_zip_bytes(raw)
        self.assertEqual(viewed["homepage"], "https://example.com/article")
        self.assertEqual(viewed["skills"][0]["source_url"], "https://example.com/article")
        self.assertEqual(viewed["skills"][0]["body"], "先看 diff")

    def test_skill_md_used_when_yaml_has_no_body(self):
        raw = _zip({
            "demo.plugin.yaml": (
                "name: demo\n"
                "homepage: https://example.com/post\n"
                "skills:\n"
                "  - name: review\n"
                "    description: 审查\n"
            ),
            "skills/review/SKILL.md": "---\nname: review\n---\n按清单检查\n",
        })
        viewed = inspect_zip_bytes(raw)
        self.assertIn("按清单检查", viewed["skills"][0]["body"])


if __name__ == "__main__":
    unittest.main()
