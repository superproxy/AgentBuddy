"""npm 安装检测兜底：GUI 进程 PATH 受限时仍能找到 nvm 下的 npm。

问题背景：桌面端（pywebview/PyInstaller 打包）GUI 进程不继承 .zshrc/.zprofile，
PATH 仅含 /usr/bin:/bin 等，nvm 安装的 node/npm 检测不到，
导致"实际已安装 Node.js 却提示未安装 npm"。

修复：install.py 的 npm 检测改用 _find_npm()（shutil.which 失败后补搜
~/.nvm/versions/node/*/bin、homebrew 等目录），执行时用绝对路径
并把 npm 所在目录注入子进程 PATH（npm 脚本内部需找到 node）。

测试策略：全 mock，不真实安装任何包，不依赖本机 node 环境
（CI 无 node 也能跑）。
"""
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.lib.ide import install as install_mod


def _npm_meta() -> dict:
    """构造一个走 npm 安装的最小 IDE 元数据。"""
    return {
        "label": "FakeIDE",
        "version": "1.0.0",
        "release_date": "2026-01-01",
        "homepage": "https://example.com",
        "cli_install": {
            "method": "npm",
            "package": "@fake/ide",
        },
        "app_install": {"method": "manual", "url": ""},
        "install_methods": ["npm"],
    }


class FakeRunCmd:
    """记录调用的 _run_cmd，可编程返回值。"""

    def __init__(self, ok=True):
        self.calls = []
        self.ok = ok

    def __call__(self, cmd, timeout=300, extra_path=None):
        self.calls.append({"cmd": cmd, "timeout": timeout, "extra_path": extra_path})
        return {
            "ok": self.ok,
            "returncode": 0 if self.ok else 1,
            "stdout": "",
            "stderr": "" if self.ok else "boom",
            "cmd": " ".join(cmd),
        }


class FindNpmFallbackTests(unittest.TestCase):
    """_find_npm：shutil.which 找不到时走 detect._which 兜底。"""

    def test_which_hit_returns_directly(self):
        with mock.patch.object(install_mod.shutil, "which", return_value="/usr/bin/npm"):
            self.assertEqual(install_mod._find_npm(), "/usr/bin/npm")

    def test_which_miss_falls_back_to_detect(self):
        with mock.patch.object(install_mod.shutil, "which", return_value=None), \
             mock.patch.object(install_mod, "_which_with_fallback",
                               return_value="/home/u/.nvm/versions/node/v24.1.0/bin/npm") as fb:
            found = install_mod._find_npm()
        self.assertEqual(found, "/home/u/.nvm/versions/node/v24.1.0/bin/npm")
        fb.assert_called_once_with("npm")

    def test_all_miss_returns_none(self):
        with mock.patch.object(install_mod.shutil, "which", return_value=None), \
             mock.patch.object(install_mod, "_which_with_fallback", return_value=None):
            self.assertIsNone(install_mod._find_npm())


class InstallNpmAbsolutePathTests(unittest.TestCase):
    """install_ide(npm)：PATH 找不到 npm 时仍用绝对路径安装（回归：误报未安装 Node.js）。"""

    def _install(self, runner):
        meta = {"FakeIDE": _npm_meta()}
        with mock.patch.object(install_mod, "IDE_INSTALL_META", meta), \
             mock.patch.object(install_mod.shutil, "which", return_value=None), \
             mock.patch.object(install_mod, "_which_with_fallback",
                               return_value="/opt/fake-nvm/bin/npm"), \
             mock.patch.object(install_mod, "_run_cmd", runner):
            return install_mod.install_ide("FakeIDE", mode="cli")

    def test_uses_absolute_npm_path_and_injects_path(self):
        runner = FakeRunCmd(ok=True)
        result = self._install(runner)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(runner.calls), 1)
        call = runner.calls[0]
        # 用绝对路径执行 npm，而非依赖 PATH 解析命令名
        self.assertEqual(call["cmd"][0], "/opt/fake-nvm/bin/npm")
        self.assertEqual(call["cmd"][1:4], ["install", "-g", "@fake/ide"])
        # npm 所在目录注入子进程 PATH（npm 内部需找到 node）
        self.assertEqual(call["extra_path"], ["/opt/fake-nvm/bin"])

    def test_npm_not_found_reports_missing_node(self):
        meta = {"FakeIDE": _npm_meta()}
        with mock.patch.object(install_mod, "IDE_INSTALL_META", meta), \
             mock.patch.object(install_mod.shutil, "which", return_value=None), \
             mock.patch.object(install_mod, "_which_with_fallback", return_value=None):
            result = install_mod.install_ide("FakeIDE", mode="cli")
        self.assertFalse(result["ok"])
        self.assertIn("未安装 npm", result["message"])


class UninstallNpmAbsolutePathTests(unittest.TestCase):
    """uninstall_ide(npm)：同样用兜底检测 + 绝对路径。"""

    def test_uses_absolute_npm_path(self):
        meta = {"FakeIDE": _npm_meta()}
        runner = FakeRunCmd(ok=True)
        with mock.patch.object(install_mod, "IDE_INSTALL_META", meta), \
             mock.patch.object(install_mod.shutil, "which", return_value=None), \
             mock.patch.object(install_mod, "_which_with_fallback",
                               return_value="/opt/fake-nvm/bin/npm"), \
             mock.patch.object(install_mod, "_run_cmd", runner):
            result = install_mod.uninstall_ide("FakeIDE", mode="cli")
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(runner.calls), 1)
        call = runner.calls[0]
        self.assertEqual(call["cmd"][0], "/opt/fake-nvm/bin/npm")
        self.assertEqual(call["cmd"][1:4], ["uninstall", "-g", "@fake/ide"])
        self.assertEqual(call["extra_path"], ["/opt/fake-nvm/bin"])


if __name__ == "__main__":
    unittest.main()
