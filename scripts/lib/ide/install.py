"""IDE 安装/卸载模块。

支持两种安装方式：
- CLI：通过 brew / npm / script（curl|bash）/ app_cli（App 内 CLI 建软链）/ manual（下载页）安装
- App：通过 brew install --cask / brew uninstall --cask，或下载 dmg

各 IDE 的安装元数据在 IDE_INSTALL_META 中定义：
    cli_install: {method: brew|npm|script|app_cli|manual, package?, script_url?, app_path?, cli_relpath?, link_name?, url?}
    app_install: {method: cask|manual, package?, url?}
    homepage: 官方主页

app_cli method：CLI 随 App 分发（如 Cursor.app 内的 cursor 命令），通过建软链
    <link_dir>/<link_name> → <app_path>/<cli_relpath> 使其出现在 PATH 上。
    link_dir 优先 /usr/local/bin，不可写则回退 ~/.local/bin。
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
        "cli_install": {"method": "npm", "package": "@anthropic-ai/claude-code", "uninstall_cmd": "npm uninstall -g @anthropic-ai/claude-code 2>/dev/null; rm -f $(which claude) 2>/dev/null; rm -rf /opt/homebrew/lib/node_modules/@anthropic-ai/claude-code ~/.nvm/versions/node/*/lib/node_modules/@anthropic-ai/claude-code"},
        "app_install": {"method": "cask", "package": "claude"},
        "homepage": "https://claude.ai/download",
    },
    "Codex": {
        "cli_install": {"method": "npm", "package": "@openai/codex", "uninstall_cmd": "npm uninstall -g @openai/codex 2>/dev/null; rm -f $(which codex) 2>/dev/null; rm -rf /opt/homebrew/lib/node_modules/@openai/codex ~/.nvm/versions/node/*/lib/node_modules/@openai/codex"},
        "app_install": {"method": "manual", "url": "https://openai.com/codex/download"},
        "homepage": "https://openai.com/codex",
    },
    "Cursor": {
        "cli_install": {
            "method": "app_cli",
            "app_path": "/Applications/Cursor.app",
            "cli_relpath": "Contents/Resources/app/bin/cursor",
            "link_name": "cursor",
            "url": "https://cursor.com",
        },
        "app_install": {"method": "cask", "package": "cursor"},
        "homepage": "https://cursor.com",
    },
    "Trae": {
        "cli_install": {"method": "manual", "url": "https://www.trae.ai", "uninstall_cmd": "rm -f ~/.local/bin/trae-cli ~/.local/bin/traecli && rm -rf ~/.local/share/trae-cli"},
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
        "cli_install": {"method": "brew", "package": "opencode", "uninstall_cmd": "rm -f $(which opencode) 2>/dev/null; rm -rf ~/.config/opencode"},
        "app_install": {"method": "manual", "url": "https://opencode.ai/downloads"},
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
        "cli_install": {"method": "npm", "package": "openclaw", "uninstall_cmd": "npm uninstall -g openclaw 2>/dev/null; rm -f $(which openclaw) 2>/dev/null; rm -rf ~/.local/share/openclaw"},
        "app_install": {"method": "cask", "package": "openclaw"},
        "homepage": "https://github.com/openclaw/openclaw",
    },
    "Hermes": {
        "cli_install": {"method": "manual", "url": ""},
        "app_install": {"method": "manual", "url": ""},
        "homepage": "",
    },
    "WorkBuddy": {
        "cli_install": {"method": "npm", "package": "@anthropic-ai/claude-code"},
        "app_install": {"method": "manual", "url": "https://github.com/workbuddy/workbuddy/releases"},
        "homepage": "https://github.com/workbuddy/workbuddy",
    },
    "ZCode": {
        "cli_install": {"method": "manual", "url": "https://zcode.z.ai/cn"},
        "app_install": {"method": "manual", "url": "https://zcode.z.ai/cn/download"},
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


def _select_link_dir() -> Path:
    """选择可写的软链目录：优先 /usr/local/bin（标准 PATH），不可写则回退 ~/.local/bin。

    app_cli method 用它给 App 内 CLI 建软链，使其出现在 PATH 上。
    """
    candidates = [Path("/usr/local/bin"), Path.home() / ".local" / "bin"]
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".agentbuddy.write_probe"
            probe.touch()
            probe.unlink(missing_ok=True)
            return d
        except (PermissionError, OSError):
            continue
    # 兜底：~/.local/bin（即使不可写也返回，由调用方报错）
    return Path.home() / ".local" / "bin"


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

    if method == "app_cli":
        # CLI 随 App 分发（如 Cursor.app 内的 cursor 命令）：建软链到 PATH
        app_path = install_meta.get("app_path", "")
        cli_relpath = install_meta.get("cli_relpath", "")
        link_name = install_meta.get("link_name", ide_key.lower())
        fallback_url = url or meta.get("homepage", "")
        if not app_path or not cli_relpath:
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "app_cli",
                    "message": "app_cli 配置不完整（缺 app_path/cli_relpath）",
                    "cmd": "", "stdout": "", "stderr": "", "url": fallback_url}
        cli_in_app = Path(app_path) / cli_relpath
        if not cli_in_app.exists():
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "app_cli",
                    "message": f"未找到 App 内 CLI（{cli_in_app}），请先安装 App（点'安装 App'）",
                    "cmd": "", "stdout": "", "stderr": "", "url": fallback_url}
        link_dir = _select_link_dir()
        link_target = link_dir / link_name
        cmd_str = f"ln -sf {cli_in_app} {link_target}"
        try:
            # 覆盖已有软链/文件（先删再建，避免 symlink_to 覆盖文件时的行为差异）
            if link_target.is_symlink() or link_target.exists():
                link_target.unlink()
            link_target.symlink_to(cli_in_app)
            return {
                "ok": True, "ide": ide_key, "mode": mode, "method": "app_cli",
                "message": f"已创建软链: {link_target} → {cli_in_app}",
                "cmd": cmd_str, "stdout": "", "stderr": "",
            }
        except PermissionError:
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "app_cli",
                    "message": f"无权限写入 {link_dir}，请手动执行: sudo ln -sf {cli_in_app} {link_target}",
                    "cmd": f"sudo ln -sf {cli_in_app} {link_target}",
                    "stdout": "", "stderr": "PermissionError", "url": fallback_url}
        except Exception as e:
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "app_cli",
                    "message": f"创建软链失败: {e}", "cmd": cmd_str,
                    "stdout": "", "stderr": str(e), "url": fallback_url}

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
        # manual 但配了 uninstall_cmd：执行自定义卸载命令（如 trae-cli 删符号链接+目录）
        uninstall_cmd = install_meta.get("uninstall_cmd", "")
        if uninstall_cmd:
            r = _run_cmd(["bash", "-c", uninstall_cmd], timeout=120)
            return {
                "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "manual",
                "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
                "cmd": uninstall_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
            }
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
        if shutil.which("brew"):
            r = _run_cmd(["brew", "uninstall", package], timeout=300)
            if r["ok"]:
                return {
                    "ok": True, "ide": ide_key, "mode": mode, "method": "brew",
                    "message": "卸载成功", "cmd": r["cmd"],
                    "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
                }
        # brew 失败或无 brew，fallback uninstall_cmd
        uninstall_cmd = install_meta.get("uninstall_cmd", "")
        if uninstall_cmd:
            r = _run_cmd(["bash", "-c", uninstall_cmd], timeout=120)
            return {
                "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "brew",
                "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
                "cmd": uninstall_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
            }
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "brew",
                "message": "未安装 Homebrew 或 brew uninstall 失败", "cmd": "", "stdout": "", "stderr": ""}

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
        if r["ok"]:
            # npm uninstall 返回成功，但可能没真正删掉（多 npm 环境如 nvm vs homebrew）
            # 检查二进制是否还在，在则 fallback uninstall_cmd
            cli_names = IDE_INSTALL_META.get(ide_key, {}).get("cli_install", {}).get("cli_names", [])
            # 从 detect.py 的 IDE_DETECT_META 获取 cli_names
            try:
                from .detect import IDE_DETECT_META
                cli_names = IDE_DETECT_META.get(ide_key, {}).get("cli_names", cli_names)
            except Exception:
                pass
            still_exists = any(shutil.which(n) for n in cli_names) if cli_names else False
            if not still_exists:
                return {
                    "ok": True, "ide": ide_key, "mode": mode, "method": "npm",
                    "message": "卸载成功", "cmd": r["cmd"],
                    "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
                }
        # npm uninstall 失败或二进制仍在，fallback uninstall_cmd
        uninstall_cmd = install_meta.get("uninstall_cmd", "")
        if uninstall_cmd:
            r2 = _run_cmd(["bash", "-c", uninstall_cmd], timeout=120)
            return {
                "ok": r2["ok"], "ide": ide_key, "mode": mode, "method": "npm",
                "message": "卸载成功" if r2["ok"] else f"卸载失败 (exit={r2['returncode']})",
                "cmd": uninstall_cmd, "stdout": r2["stdout"][-2000:], "stderr": r2["stderr"][-2000:],
            }
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
        if cli_install.get("method") == "app_cli":
            # app_cli 依赖 macOS .app 内 CLI，非 macOS 降级为 manual
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
