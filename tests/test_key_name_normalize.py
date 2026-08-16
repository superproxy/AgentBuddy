"""密钥名归一化测试（纯函数，无文件/网络依赖）。

背景：密钥变量会 export 为 shell 环境变量，名字仅允许字母/数字/下划线
且不能以数字开头。用户常输入连字符（ARK-KEY）或中文输入法的全角字符
（＿ａ１－），视觉上无法区分，之前直接报错拒绝对用户不友好——现在
归一化（全角→半角、空格/连字符→下划线）后再校验，仍非法才报具体原因。
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))

from config_server import _normalize_key_name  # noqa: E402

VALID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TestNormalizeKeyName(unittest.TestCase):
    def test_plain_passes(self):
        self.assertEqual(_normalize_key_name("ARK_API_KEY"), "ARK_API_KEY")

    def test_hyphen_to_underscore(self):
        self.assertEqual(_normalize_key_name("ARK-KEY"), "ARK_KEY")
        self.assertEqual(_normalize_key_name("a-b-c"), "a_b_c")

    def test_space_to_underscore(self):
        self.assertEqual(_normalize_key_name("MY KEY"), "MY_KEY")
        self.assertEqual(_normalize_key_name("  x  y  "), "x_y")

    def test_fullwidth_ascii_to_halfwidth(self):
        # 中文输入法全角：ａｂｃ → abc，＿ → _，－ → -
        self.assertEqual(_normalize_key_name("ａｂｃ＿ＫＥＹ"), "abc_KEY")
        self.assertEqual(_normalize_key_name("ＡＲＫ－ＫＥＹ"), "ARK_KEY")

    def test_normalized_names_are_valid(self):
        for raw in ["ARK-KEY", "MY KEY", "ａｂｃ＿１", "a—b", "x–y"]:
            self.assertRegex(_normalize_key_name(raw), r"^[A-Za-z_][A-Za-z0-9_]*$",
                             msg=f"{raw!r} 归一化后应合法")

    def test_digit_start_still_invalid_after_normalize(self):
        self.assertFalse(VALID.match(_normalize_key_name("2FA_TOKEN")))  # 以数字开头，归一化救不了

    def test_chinese_chars_untouched(self):
        # 中文字符不在全角 ASCII 范围，保留原样（随后被校验拒绝并报具体字符）
        self.assertEqual(_normalize_key_name("密钥"), "密钥")


if __name__ == "__main__":
    unittest.main()
