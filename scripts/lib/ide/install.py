"""IDE 安装/卸载模块。

支持两种安装方式：
- CLI：通过 brew / npm / script（curl|bash）/ manual（下载页）安装
- App：通过 brew install --cask / brew uninstall --cask，或下载 dmg

各 IDE 的安装元数据在 IDE_INSTALL_META 中定义：
    cli_install: {method: brew|npm|script|manual, package?, script_url?, url?}
    app_install: {method: cask|manual, package?, url?}
    homepage: 官方主页
"""
import shutil
import subprocess
import sys
from pathlib import Path


# ===== IDE 安装元数据 =====
# cli_install: 安装 CLI 的方式（brew/npm/manual）与包名
# app_install: 安装 App 的方式（cask/download/manual）与包名/URL
IDE_INSTALL_META = {
    "Claude": {
        "cli_install": {"method": "npm", "package": "@anthropic-ai/claude-code"},
        "app_install": {"method": "cask", "package": "claude"},
        "homepage": "https://claude.ai/download",
    },
    "Codex": {
        "cli_install": {"method": "npm", "package": "@openai/codex"},
        "app_install": {"method": "manual", "url": "https://openai.com/codex"},
        "homepage": "https://openai.com/codex",
    },
    "Cursor": {
        "cli_install": {"method": "manual", "url": "https://cursor.com"},
        "app_install": {"method": "cask", "package": "cursor"},
        "homepage": "https://cursor.com",
    },
    "Trae": {
        "cli_install": {"method": "manual", "url": "https://www.trae.ai"},
        "app_install": {"method": "cask", "package": "trae"},
        "homepage": "https://www.trae.ai",
    },
    "TraeCN": {
        "cli_install": {"method": "manual", "url": "https://www.trae.cn"},
        "app_install": {"method": "cask", "package": "trae-cn"},
        "homepage": "https://www.trae.cn",
    },
    "TraeSoloCN": {
        "cli_install": {"method": "manual", "url": "https://www.trae.cn"},
        "app_install": {"method": "manual", "url": "https://www.trae.cn/download"},
        "homepage": "https://www.trae.cn",
    },
    "OpenCode": {
        "cli_install": {"method": "brew", "package": "opencode"},
        "app_install": {"method": "manual", "url": "https://opencode.ai"},
        "homepage": "https://opencode.ai",
    },
    "Qoder": {
        "cli_install": {"method": "script", "script_url": "https://qoder.com/install"},
        "app_install": {"method": "cask", "package": "qoder"},
        "homepage": "https://qoder.com/zh/cli",
    },
    "QoderCN": {
        "cli_install": {"method": "script", "script_url": "https://qoder.com.cn/install"},
        "app_install": {"method": "manual", "url": "https://qoder.com.cn/download"},
        "homepage": "https://qoder.com.cn/cli",
    },
    "OpenClaw": {
        "cli_install": {"method": "manual", "url": "https://github.com/openclaw/openclaw"},
        "app_install": {"method": "cask", "package": "openclaw"},
        "homepage": "https://github.com/openclaw/openclaw",
    },
    "WorkBuddy": {
        "cli_install": {"method": "manual", "url": "https://github.com/workbuddy/workbuddy"},
        "app_install": {"method": "manual", "url": "https://github.com/workbuddy/workbuddy"},
        "homepage": "https://github.com/workbuddy/workbuddy",
    },
    "ZCode": {
        "cli_install": {"method": "manual", "url": "https://zcode.z.ai/cn"},
        "app_install": {"method": "manual", "url": "https://zcode.z.ai/cn"},
        "homepage": "https://zcode.z.ai/cn",
    },
    "IDEA": {
        "cli_install": {"method": "manual", "url": "https://www.jetbrains.com/idea"},
        "app_install": {"method": "cask", "package": "intellij-idea-ce"},
        "homepage": "https://www.jetbrains.com/idea",
    },
    "Agents": {
        "cli_install": {"method": "manual", "url": ""},
        "app_install": {"method": "manual", "url": ""},
        "homepage": "",
    },
}


def _run_cmd(cmd: list[str], timeout: int = 300) -> dict:
    """运行命令并返回结果。

    Returns:
        {ok: bool, returncode: int, stdout: str, stderr: str, cmd: str}
    """
    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=timeout,
        )
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "cmd": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": "timeout",
                "cmd": " ".join(cmd)}
    except Exception as e:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(e),
                "cmd": " ".join(cmd)}


def install_ide(ide_key: str, mode: str = "cli") -> dict:
    """安装 IDE。

    Args:
        ide_key: IDE 标识（如 "OpenCode"）
        mode: "cli" 或 "app"

    Returns:
        {ok: bool, ide: str, mode: str, method: str, message: str, cmd: str, stdout: str, stderr: str}
    """
    meta = IDE_INSTALL_META.get(ide_key)
    if not meta:
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "",
                "message": f"Unknown IDE: {ide_key}", "cmd": "", "stdout": "", "stderr": ""}

    if mode == "cli":
        install_meta = meta.get("cli_install", {})
    elif mode == "app":
        install_meta = meta.get("app_install", {})
    else:
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "",
                "message": f"Invalid mode: {mode}", "cmd": "", "stdout": "", "stderr": ""}

    method = install_meta.get("method", "manual")
    package = install_meta.get("package", "")
    url = install_meta.get("url", "")
    script_url = install_meta.get("script_url", "")

    if method == "manual":
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "manual",
            "message": f"需手动安装，请访问: {url or meta.get('homepage', '')}",
            "cmd": "", "stdout": "", "stderr": "",
            "url": url or meta.get("homepage", ""),
        }

    if method == "script":
        # curl -fsSL <script_url> | bash
        if not shutil.which("curl"):
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "script",
                    "message": "未安装 curl", "cmd": "", "stdout": "", "stderr": ""}
        if not script_url:
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "script",
                    "message": "未配置 script_url", "cmd": "", "stdout": "", "stderr": ""}
        shell_cmd = f"curl -fsSL {script_url} | bash"
        r = _run_cmd(["bash", "-c", shell_cmd], timeout=600)
        return {
            "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "script",
            "message": "安装成功" if r["ok"] else f"安装失败 (exit={r['returncode']})",
            "cmd": shell_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }

    if method == "brew":
        if not shutil.which("brew"):
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "brew",
                    "message": "未安装 Homebrew，请先安装: https://brew.sh",
                    "cmd": "", "stdout": "", "stderr": ""}
        cmd = ["brew", "install", package]
        r = _run_cmd(cmd, timeout=600)
        return {
            "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "brew",
            "message": "安装成功" if r["ok"] else f"安装失败 (exit={r['returncode']})",
            "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }

    if method == "cask":
        if not shutil.which("brew"):
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "cask",
                    "message": "未安装 Homebrew，请先安装: https://brew.sh",
                    "cmd": "", "stdout": "", "stderr": ""}
        cmd = ["brew", "install", "--cask", package]
        r = _run_cmd(cmd, timeout=600)
        return {
            "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "cask",
            "message": "安装成功" if r["ok"] else f"安装失败 (exit={r['returncode']})",
            "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }

    if method == "npm":
        if not shutil.which("npm"):
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "npm",
                    "message": "未安装 npm，请先安装 Node.js",
                    "cmd": "", "stdout": "", "stderr": ""}
        cmd = ["npm", "install", "-g", package]
        r = _run_cmd(cmd, timeout=600)
        return {
            "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "npm",
            "message": "安装成功" if r["ok"] else f"安装失败 (exit={r['returncode']})",
            "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }

    return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
            "message": f"Unsupported method: {method}", "cmd": "", "stdout": "", "stderr": ""}


def uninstall_ide(ide_key: str, mode: str = "cli") -> dict:
    """卸载 IDE。

    Args:
        ide_key: IDE 标识
        mode: "cli" 或 "app"

    Returns:
        {ok: bool, ide: str, mode: str, method: str, message: str, cmd: str, stdout: str, stderr: str}
    """
    meta = IDE_INSTALL_META.get(ide_key)
    if not meta:
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "",
                "message": f"Unknown IDE: {ide_key}", "cmd": "", "stdout": "", "stderr": ""}

    if mode == "cli":
        install_meta = meta.get("cli_install", {})
    elif mode == "app":
        install_meta = meta.get("app_install", {})
    else:
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "",
                "message": f"Invalid mode: {mode}", "cmd": "", "stdout": "", "stderr": ""}

    method = install_meta.get("method", "manual")
    package = install_meta.get("package", "")

    if method == "manual":
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "manual",
            "message": "需手动卸载", "cmd": "", "stdout": "", "stderr": "",
        }

    if method == "script":
        # script 安装方式无标准卸载命令，提示手动卸载
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "script",
            "message": "script 安装方式需手动卸载（请参考官方文档）",
            "cmd": "", "stdout": "", "stderr": "",
            "url": meta.get("homepage", ""),
        }

    if method == "brew":
        if not shutil.which("brew"):
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "brew",
                    "message": "未安装 Homebrew", "cmd": "", "stdout": "", "stderr": ""}
        cmd = ["brew", "uninstall", package]
        r = _run_cmd(cmd, timeout=300)
        return {
            "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "brew",
            "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
            "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }

    if method == "cask":
        if not shutil.which("brew"):
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "cask",
                    "message": "未安装 Homebrew", "cmd": "", "stdout": "", "stderr": ""}
        cmd = ["brew", "uninstall", "--cask", package]
        r = _run_cmd(cmd, timeout=300)
        return {
            "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "cask",
            "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
            "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }

    if method == "npm":
        if not shutil.which("npm"):
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "npm",
                    "message": "未安装 npm", "cmd": "", "stdout": "", "stderr": ""}
        cmd = ["npm", "uninstall", "-g", package]
        r = _run_cmd(cmd, timeout=300)
        return {
            "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "npm",
            "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
            "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }

    return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
            "message": f"Unsupported method: {method}", "cmd": "", "stdout": "", "stderr": ""}


def reinstall_ide(ide_key: str, mode: str = "cli") -> dict:
    """重装 IDE（先卸载再安装）。

    Args:
        ide_key: IDE 标识
        mode: "cli" 或 "app"

    Returns:
        {ok: bool, ide, mode, method, message, cmd, stdout, stderr, uninstall_result?}
    """
    # 1. 先卸载（忽略卸载失败，继续安装）
    uninst = uninstall_ide(ide_key, mode)
    # 2. 再安装
    inst = install_ide(ide_key, mode)
    inst["reinstall"] = True
    inst["uninstall_result"] = {
        "ok": uninst.get("ok", False),
        "message": uninst.get("message", ""),
    }
    # 综合判断：安装成功即视为重装成功
    inst["message"] = f"重装成功（卸载: {uninst.get('message','')} → 安装: {inst.get('message','')}）" if inst["ok"] \
        else f"重装失败（卸载: {uninst.get('message','')} → 安装: {inst.get('message','')}）"
    return inst


def get_install_info(ide_key: str) -> dict:
    """获取 IDE 的安装元信息（不执行安装）。

    平台适配：
    - macOS：cask 方式有效（brew install --cask）
    - Windows/Linux：cask 不可用，自动降级为 manual + homepage URL
    """
    meta = IDE_INSTALL_META.get(ide_key)
    if not meta:
        return {"ide": ide_key, "available": False}
    cli_install = dict(meta.get("cli_install", {}))
    app_install = dict(meta.get("app_install", {}))
    homepage = meta.get("homepage", "")

    # 非 macOS 平台：cask 降级为 manual + homepage
    if sys.platform != "darwin":
        if cli_install.get("method") == "cask":
            cli_install = {"method": "manual", "url": homepage}
        if cli_install.get("method") == "brew":
            cli_install = {"method": "manual", "url": homepage}
        if app_install.get("method") == "cask":
            app_install = {"method": "manual", "url": homepage}

    return {
        "ide": ide_key,
        "available": True,
        "cli": cli_install,
        "app": app_install,
        "homepage": homepage,
    }


__all__ = ["IDE_INSTALL_META", "install_ide", "uninstall_ide", "reinstall_ide", "get_install_info"]
