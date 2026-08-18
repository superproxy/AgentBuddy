"""IDE 安装/卸载模块。

支持两种安装方式：
- CLI：通过 brew / npm / script（curl|bash）/ powershell_script / app_cli（App 内 CLI 建软链）/ manual（下载页）安装
- App：通过 system_uninstall（系统级卸载 + 强删兜底）/ manual（仅给下载页）安装

================================================================
IDE 安装元数据规范（IDE_INSTALL_META Schema）
================================================================
为避免新增 IDE 时漏配字段，每个 IDE 条目必须包含以下完整结构：

    "<IdeKey>": {
        # —— 标识与版本元信息 ——
        "label":          str,   # 显示名（与 detect.py 的 label 一致）
        "version":        str,   # 最新已知版本号（用于展示，非运行时校验）
        "release_date":   str,   # 版本发布日期 YYYY-MM-DD（用于判断是否过期）
        "homepage":       str,   # 官方主页
        "docs_url":       str,   # 官方文档/安装说明页
        "release_url":    str,   # GitHub Releases 或 changelog 页

        # —— CLI 安装配置 ——
        "cli_install": {
            "method":          "brew" | "npm" | "script" | "powershell_script" | "app_cli" | "manual",
            # brew / npm 用：
            "package":         str,    # 包名（如 "@openai/codex"）
            # script / powershell_script 用：
            "script_url":      str,    # macOS/Linux 安装脚本 URL
            "script_url_win":  str,    # Windows PowerShell 脚本 URL（仅 script/powershell_script）
            # app_cli 用（CLI 随 App 分发，需建软链）：
            "app_path":        str,    # App 绝对路径（如 /Applications/Cursor.app）
            "cli_relpath":     str,    # App 内 CLI 相对路径（如 Contents/Resources/app/bin/cursor）
            "link_name":       str,    # 软链名称（默认取 IDE key 小写）
            # 通用：
            "url":             str,    # 安装说明页（manual 时给下载页）
            "uninstall_cmd_mac": str,  # macOS 卸载命令（bash -c 执行）
            "uninstall_cmd_win": str,  # Windows 卸载命令（cmd /c 执行）
            "uninstall_cmd":   str,    # 通用卸载命令（仅 macOS/Linux 用 bash 执行）
        },

        # —— App 安装配置 ——
        "app_install": {
            "method":          "system_uninstall" | "cask" | "manual",
            # cask 用：
            "package":         str,    # brew cask 包名
            # 通用：
            "url":             str,    # 下载页 URL（manual / system_uninstall 都要有）
            "uninstall_cmd_mac": str,
            "uninstall_cmd_win": str,
            "uninstall_cmd":   str,
        },

        # —— 直达下载地址（按平台/架构）——
        # 用于"打开下载页"按钮的直链，缺失时回退 app_install.url 或 homepage
        "download_urls": {
            "macos_arm64":     str,    # Apple Silicon dmg/zip
            "macos_x64":       str,    # Intel dmg/zip
            "windows_x64":     str,    # x64 exe/msi
            "windows_arm64":   str,    # ARM64 exe/msi
            "linux_x64":       str,    # x64 deb/rpm/AppImage
            "linux_arm64":     str,    # ARM64 deb/rpm/AppImage
        },

        # —— 该 IDE 支持的所有安装方式（用于 UI 展示）——
        "install_methods": ["script", "npm", "brew", ...],
    }

校验：调用 validate_ide_meta() 会检查每个 IDE 是否齐备必要字段，
缺失会在启动 config_server 时打印警告，避免"每次都漏很多"。

app_cli method：CLI 随 App 分发（如 Cursor.app 内的 cursor 命令），通过建软链
    <link_dir>/<link_name> → <app_path>/<cli_relpath> 使其出现在 PATH 上。
    link_dir 优先 /usr/local/bin，不可写则回退 ~/.local/bin。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ===== IDE 安装元数据（从 ide.yaml 加载） =====
# 配置数据源：scripts/lib/ide/ide.yaml（install_meta 段）
# 代码只负责调用执行，新增/修改 IDE 请编辑 ide.yaml
from ._meta import get_install_meta as _get_install_meta
# 复用 detect 的兜底 which（GUI 进程 PATH 受限，需补搜 nvm/homebrew 等用户 bin 目录）
from .detect import _which as _which_with_fallback

IDE_INSTALL_META = _get_install_meta()


def _find_npm() -> str | None:
    """查找 npm 可执行文件绝对路径。

    GUI 进程（pywebview/PyInstaller 打包）不继承 .zshrc/.zprofile，
    PATH 仅含 /usr/bin:/bin 等，nvm 安装的 npm 检测不到，
    导致"实际已安装 Node.js 却提示未安装"。先用 shutil.which，
    失败后补搜 ~/.nvm/versions/node/*/bin、homebrew 等目录。
    """
    found = shutil.which("npm")
    if found:
        return found
    return _which_with_fallback("npm")



# ===== Schema 校验 =====
# 必填字段（顶层）
_REQUIRED_TOP_FIELDS = ["label", "version", "release_date", "homepage", "cli_install", "app_install"]
# 必填字段（cli_install / app_install）
_REQUIRED_INSTALL_FIELDS = ["method"]
# 各 method 的额外必填字段
_REQUIRED_FIELDS_BY_METHOD = {
    "brew": ["package"],
    "npm": ["package"],
    "script": ["url"],  # script_url 在 Windows 缺失时回退 manual，可接受
    "powershell_script": ["script_url"],
    "app_cli": ["app_path", "cli_relpath"],
    "system_uninstall": ["url"],
    "cask": ["package"],
    "manual": [],  # manual 仅需 url（可空）
}


def validate_ide_meta() -> list[str]:
    """校验 IDE_INSTALL_META 是否符合 Schema 规范，返回警告列表（空列表表示通过）。

    启动时调用此函数可在新增 IDE 漏配字段时立即发现，避免"每次都漏很多"。

    检查项：
    1. 每个 IDE 必填顶层字段：label/version/release_date/homepage/cli_install/app_install
    2. cli_install / app_install 必填 method
    3. vscode_install / idea_install / acp_install（若存在）必填 method + url
    4. 各 method 的额外必填字段（如 brew/npm 必须有 package）
    5. install_methods 列表必须存在（可空）
    6. forms 列表必须存在（用于 UI 分组）
    """
    warnings: list[str] = []
    for ide_key, meta in IDE_INSTALL_META.items():
        # 1. 顶层字段
        for field in _REQUIRED_TOP_FIELDS:
            if field not in meta:
                warnings.append(f"[{ide_key}] 缺少顶层字段: {field}")
        # 2. install 块的 method（cli/app 必填，vscode/idea/acp 可选）
        required_blocks = ("cli_install", "app_install")
        optional_blocks = ("vscode_install", "idea_install", "acp_install")
        for install_type in required_blocks:
            block = meta.get(install_type, {})
            if not isinstance(block, dict):
                warnings.append(f"[{ide_key}] {install_type} 必须是 dict")
                continue
            for field in _REQUIRED_INSTALL_FIELDS:
                if field not in block:
                    warnings.append(f"[{ide_key}] {install_type} 缺少字段: {field}")
            # 3. method 特定字段
            method = block.get("method", "")
            for field in _REQUIRED_FIELDS_BY_METHOD.get(method, []):
                if not block.get(field):
                    warnings.append(f"[{ide_key}] {install_type} method={method} 缺少字段: {field}")
        # 可选扩展块：vscode/idea/acp（若存在则校验 method + url）
        for install_type in optional_blocks:
            block = meta.get(install_type)
            if block is None:
                continue
            if not isinstance(block, dict):
                warnings.append(f"[{ide_key}] {install_type} 必须是 dict")
                continue
            if "method" not in block:
                warnings.append(f"[{ide_key}] {install_type} 缺少字段: method")
            # url 缺失时回退 homepage，可接受，不强制
        # 4. install_methods 列表
        if "install_methods" not in meta:
            warnings.append(f"[{ide_key}] 缺少 install_methods 列表（即使为空也需声明）")
        elif not isinstance(meta["install_methods"], list):
            warnings.append(f"[{ide_key}] install_methods 必须是 list")
        # 5. forms 列表（用于 UI 分组）
        if "forms" not in meta:
            warnings.append(f"[{ide_key}] 缺少 forms 列表（即使为空也需声明）")
        elif not isinstance(meta["forms"], list):
            warnings.append(f"[{ide_key}] forms 必须是 list")
    return warnings


def _fix_windows_cli_install(ide_key: str) -> str:
    """Windows 下修复安装脚本未完成的步骤。

    部分官方安装脚本（如 Cursor）在 Windows 上可能因 Rename-Item 冲突、
    Copy-Item 权限等原因未完整执行，导致 CLI 文件未复制到 PATH 目录。
    此函数在安装后补完这些步骤。

    Returns: 修复信息字符串（空字符串表示无需修复）。
    """
    if sys.platform != "win32":
        return ""
    localappdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))

    # Cursor: 官方安装脚本可能未完整执行，导致：
    # 1. versions 下只有 dist-package（非版本号格式），cursor-agent.ps1 找不到版本目录
    #    （cursor-agent.ps1 用正则 ^\d{4}\.\d{1,2}\.\d{1,2}... 匹配，dist-package 不匹配）
    # 2. 根目录虽有 cursor-agent.ps1，但调用时报 "No version directories found"
    #
    # 修复策略：生成一个独立的 agent.cmd/agent.ps1，直接调用 dist-package（或最新版本目录）
    # 里的 node.exe + index.js，绕过 cursor-agent.ps1 的版本目录查找逻辑。
    if ide_key == "Cursor":
        agent_dir = Path(localappdata) / "cursor-agent"
        if not agent_dir.is_dir():
            return ""
        import shutil as _shutil
        import re as _re
        fixed: list[str] = []
        versions_dir = agent_dir / "versions"

        # 找到包含 node.exe 的源目录（优先版本号目录，其次 dist-package）
        src_dir = None
        if versions_dir.is_dir():
            ver_pattern = _re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}(-\d{2}-\d{2}-\d{2})?-[a-f0-9]+$")
            # 先找合法版本目录
            legal = [d for d in versions_dir.iterdir()
                     if d.is_dir() and ver_pattern.match(d.name) and (d / "node.exe").exists()]
            if legal:
                src_dir = sorted(legal, reverse=True)[0]
            else:
                # 回退到 dist-package
                dist_pkg = versions_dir / "dist-package"
                if dist_pkg.is_dir() and (dist_pkg / "node.exe").exists():
                    src_dir = dist_pkg

        if not src_dir:
            return ""  # 无可用源目录，无法修复

        # 生成独立的 agent.cmd（直接调用 node.exe index.js，不走 cursor-agent.ps1）
        agent_cmd = agent_dir / "agent.cmd"
        node_exe = src_dir / "node.exe"
        index_js = src_dir / "index.js"
        if not index_js.exists():
            # 尝试找其他 *.js 入口
            js_files = list(src_dir.glob("*.js"))
            if js_files:
                index_js = js_files[0]
            else:
                return ""  # 无 JS 入口文件

        # agent.cmd：直接调用 node.exe + index.js，传递所有参数
        agent_cmd_content = f"""@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "CURSOR_INVOKED_AS=agent.cmd"
if not defined NODE_COMPILE_CACHE set "NODE_COMPILE_CACHE=%LOCALAPPDATA%\\cursor-compile-cache"
"%SCRIPT_DIR%versions\\{src_dir.name}\\node.exe" "%SCRIPT_DIR%versions\\{src_dir.name}\\{index_js.name}" %*
exit /b %ERRORLEVEL%
"""
        agent_ps1_content = f"""$env:CURSOR_INVOKED_AS = 'agent.ps1'
if (-not $env:NODE_COMPILE_CACHE) {{
    $env:NODE_COMPILE_CACHE = "$env:LOCALAPPDATA\\cursor-compile-cache"
}}
$scriptPath = Split-Path -parent $MyInvocation.MyCommand.Definition
& "$scriptPath\\versions\\{src_dir.name}\\node.exe" "$scriptPath\\versions\\{src_dir.name}\\{index_js.name}" $args
exit $LASTEXITCODE
"""
        try:
            agent_cmd.write_text(agent_cmd_content, encoding="utf-8")
            fixed.append("agent.cmd")
        except Exception:
            pass
        try:
            (agent_dir / "agent.ps1").write_text(agent_ps1_content, encoding="utf-8")
            fixed.append("agent.ps1")
        except Exception:
            pass

        if fixed:
            return f"已修复 Cursor CLI（生成独立启动器，源: {src_dir.name}）: {', '.join(fixed)}"
        return ""

    return ""


def _run_cmd(cmd: list[str], timeout: int = 300, extra_path: list[str] | None = None) -> dict:
    """运行命令并返回结果。

    Args:
        cmd: 命令及参数列表
        timeout: 超时秒数
        extra_path: 需注入子进程 PATH 的目录（如 nvm 的 node bin 目录），
            供用绝对路径执行 npm 时让其内部能找到 node。

    Returns:
        {ok: bool, returncode: int, stdout: str, stderr: str, cmd: str}
    """
    env = None
    if extra_path:
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join(extra_path) + os.pathsep + env.get("PATH", "")
    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=timeout,
            env=env,
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


def _find_jetbrains_launcher() -> str | None:
    """查找系统中的 JetBrains IDE 可执行文件（用于命令行安装插件）。

    按优先级查找：IntelliJ IDEA > PyCharm > WebStorm > GoLand > PhpStorm >
                  RubyMine > CLion > Android Studio > Rider > 其他

    来源: https://www.jetbrains.com.cn/help/idea/install-plugins-from-the-command-line.html
    语法: <ide>.exe installPlugins <plugin-id> [repository-url]
          <ide> installPlugins <plugin-id> [repository-url]   (macOS)
          <ide>.sh installPlugins <plugin-id> [repository-url] (Linux)

    Returns:
        可执行文件路径（字符串），或 None（未找到）。
    """
    if sys.platform == "win32":
        # Windows: 优先 idea64.exe（IntelliJ IDEA），回退到其他 IDE
        candidates = [
            "idea64.exe", "idea.exe",
            "pycharm64.exe", "pycharm.exe",
            "webstorm64.exe", "webstorm.exe",
            "goland64.exe", "goland.exe",
            "phpstorm64.exe", "phpstorm.exe",
        ]
        # 检查 PATH
        for name in candidates:
            path = shutil.which(name)
            if path:
                return path
        # 检查常见安装目录
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        install_dirs = [
            Path(program_files) / "JetBrains",
            Path(local_appdata) / "Programs" / "JetBrains" if local_appdata else None,
        ]
        for base in install_dirs:
            if not base or not base.exists():
                continue
            for ide_dir in base.iterdir():
                if not ide_dir.is_dir():
                    continue
                bin_dir = ide_dir / "bin"
                if not bin_dir.exists():
                    continue
                for name in candidates:
                    exe = bin_dir / name
                    if exe.exists():
                        return str(exe)
        return None

    elif sys.platform == "darwin":
        # macOS: 优先 /Applications/IntelliJ IDEA.app/Contents/MacOS/idea
        apps = [
            ("IntelliJ IDEA.app", "idea"),
            ("IntelliJ IDEA CE.app", "idea"),
            ("IntelliJ IDEA Ultimate.app", "idea"),
            ("PyCharm.app", "pycharm"),
            ("PyCharm CE.app", "pycharm"),
            ("PyCharm Professional.app", "pycharm"),
            ("WebStorm.app", "webstorm"),
            ("GoLand.app", "goland"),
            ("PhpStorm.app", "phpstorm"),
            ("RubyMine.app", "rubymine"),
            ("CLion.app", "clion"),
            ("Android Studio.app", "studio"),
        ]
        for app_name, launcher in apps:
            exe = Path("/Applications") / app_name / "Contents" / "MacOS" / launcher
            if exe.exists():
                return str(exe)
        # 检查 PATH（用户可能配置了命令行启动器）
        for launcher in ["idea", "pycharm", "webstorm", "goland", "phpstorm", "clion"]:
            path = shutil.which(launcher)
            if path:
                return path
        return None

    else:
        # Linux: 优先 ~/.local/share/JetBrains/Toolbox/apps/<IDE>/bin/<ide>.sh
        home = Path.home()
        toolbox_apps = home / ".local" / "share" / "JetBrains" / "Toolbox" / "apps"
        if toolbox_apps.exists():
            for app_dir in toolbox_apps.iterdir():
                if not app_dir.is_dir():
                    continue
                bin_dir = app_dir / "bin"
                if not bin_dir.exists():
                    continue
                for sh in bin_dir.glob("*.sh"):
                    return str(sh)
        # 检查 PATH
        for launcher in ["idea", "pycharm", "webstorm", "goland", "phpstorm", "clion"]:
            path = shutil.which(launcher)
            if path:
                return path
        # 检查 /opt/jetbrains 等常见目录
        opt_dirs = [Path("/opt/jetbrains"), Path("/usr/local/jetbrains")]
        for base in opt_dirs:
            if not base.exists():
                continue
            for ide_dir in base.iterdir():
                if not ide_dir.is_dir():
                    continue
                bin_dir = ide_dir / "bin"
                if not bin_dir.exists():
                    continue
                for sh in bin_dir.glob("*.sh"):
                    return str(sh)
        return None


def _find_jetbrains_plugin_dir() -> Path | None:
    """查找 JetBrains 插件目录（用于 zip 下载安装）。

    插件目录路径（参考 JetBrains 官方文档）：
      macOS:   ~/Library/Application Support/JetBrains/<Product><Version>/plugins/
      Windows: %APPDATA%\\JetBrains\\<Product><Version>\\plugins\\
      Linux:   ~/.local/share/JetBrains/<Product><Version>/plugins/

    如果存在多个版本目录，选择最新的（按名称排序）。
    如果目录不存在则创建（返回第一个匹配的 base 目录下的 plugins/）。

    Returns:
        插件目录 Path，或 None（未找到 JetBrains 安装）。
    """
    home = Path.home()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        base = Path(appdata) / "JetBrains"
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "JetBrains"
    else:
        base = home / ".local" / "share" / "JetBrains"

    if not base.exists():
        return None

    # 查找所有 <Product><Version> 目录（如 IntelliJIdea2024.1, PyCharm2024.1）
    product_dirs = [d for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if not product_dirs:
        return None

    # 按名称排序，选最新的
    product_dirs.sort(reverse=True)
    for pd in product_dirs:
        plugins_dir = pd / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        return plugins_dir

    return None


def install_ide(ide_key: str, mode: str = "cli") -> dict:
    """安装 IDE。

    Args:
        ide_key: IDE 标识（如 "OpenCode"）
        mode: "cli" / "app" / "vscode" / "idea" / "acp"

    Returns:
        {ok: bool, ide: str, mode: str, method: str, message: str, cmd: str, stdout: str, stderr: str, url?}
    """
    meta = IDE_INSTALL_META.get(ide_key)
    if not meta:
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "",
                "message": f"Unknown IDE: {ide_key}", "cmd": "", "stdout": "", "stderr": ""}

    # 扩展安装维度（vscode/idea/acp）
    # - vscode/acp：仅返回 URL/命令，由前端通过 open-url 接口打开或用户手动运行
    # - idea + method=jetbrains_cli：实际执行 <ide> installPlugins <plugin_id>
    #   参考文档：https://www.jetbrains.com.cn/help/idea/install-plugins-from-the-command-line.html
    if mode in ("vscode", "idea", "acp"):
        install_meta_key = f"{mode}_install"
        ext_meta = meta.get(install_meta_key, {})
        if not ext_meta:
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "",
                    "message": f"{ide_key} 未配置 {install_meta_key}", "cmd": "", "stdout": "", "stderr": ""}
        url = ext_meta.get("url", "") or meta.get("homepage", "")
        method = ext_meta.get("method", "manual")
        note = ext_meta.get("note", "")
        cmd = ext_meta.get("cmd", "")  # ACP 类型的运行命令（如 "codex acp"）

        # —— JetBrains 插件命令行安装 ——
        # 语法: <ide> installPlugins <plugin-id> [repository-url ...]
        # 需要先关闭 IDE 再执行，安装完成后重启 IDE 生效
        if mode == "idea" and method == "jetbrains_cli":
            plugin_id = ext_meta.get("plugin_id", "")
            if not plugin_id:
                return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
                        "message": "jetbrains_cli 配置缺 plugin_id",
                        "cmd": "", "stdout": "", "stderr": "", "url": url}
            launcher = _find_jetbrains_launcher()
            if not launcher:
                msg = (f"未找到 JetBrains IDE 可执行文件（idea/pycharm/webstorm 等），"
                       f"请先安装任意 JetBrains IDE 并加入 PATH，或手动从市场安装：{url}")
                return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
                        "message": msg, "cmd": "", "stdout": "", "stderr": "",
                        "url": url}
            install_cmd = [launcher, "installPlugins", plugin_id]
            result = _run_cmd(install_cmd, timeout=120)
            ok = result["ok"]
            message_parts = [f"插件 {plugin_id} 安装{'成功' if ok else '失败'}"]
            message_parts.append(f"命令: {' '.join(install_cmd)}")
            if not ok and result["stderr"]:
                # 常见错误：IDE 未关闭
                if "running" in result["stderr"].lower() or "process" in result["stderr"].lower():
                    message_parts.append("提示：请先关闭所有 JetBrains IDE 进程再执行安装")
                else:
                    message_parts.append(f"错误: {result['stderr'][:200]}")
            return {
                "ok": ok, "ide": ide_key, "mode": mode, "method": method,
                "message": " | ".join(message_parts),
                "cmd": " ".join(install_cmd),
                "stdout": result["stdout"], "stderr": result["stderr"],
                "url": url,
            }

        # —— JetBrains 插件 zip 下载安装 ——
        # 适用于不在 Marketplace 上的插件（如 QoderCN）
        # 下载 zip → 解压到 JetBrains 插件目录
        if mode == "idea" and method == "zip_download":
            zip_url = ext_meta.get("url", "")
            if not zip_url or not zip_url.endswith(".zip"):
                return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
                        "message": "zip_download 配置缺 url 或 url 非 .zip",
                        "cmd": "", "stdout": "", "stderr": "", "url": url}
            import tempfile
            import zipfile
            import urllib.request
            # 查找 JetBrains 插件目录
            plugin_dir = _find_jetbrains_plugin_dir()
            if not plugin_dir:
                msg = ("未找到 JetBrains 插件目录，请先安装任意 JetBrains IDE，"
                       f"或手动下载 zip 安装：{zip_url}")
                return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
                        "message": msg, "cmd": "", "stdout": "", "stderr": "",
                        "url": zip_url}
            # 下载 zip
            try:
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    req = urllib.request.Request(zip_url, headers={"User-Agent": "AgentBuddy-Installer/1.0"})
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        tmp.write(resp.read())
                    tmp_path = tmp.name
            except Exception as e:
                return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
                        "message": f"下载 zip 失败: {e}",
                        "cmd": "", "stdout": "", "stderr": "", "url": zip_url}
            # 解压到插件目录
            try:
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    zf.extractall(str(plugin_dir))
                plugin_dir_str = str(plugin_dir)
            except Exception as e:
                return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
                        "message": f"解压 zip 失败: {e}",
                        "cmd": "", "stdout": "", "stderr": "", "url": zip_url}
            finally:
                import os as _os
                _os.unlink(tmp_path)
            return {
                "ok": True, "ide": ide_key, "mode": mode, "method": method,
                "message": f"插件已下载安装到 {plugin_dir_str}，重启 JetBrains IDE 生效",
                "cmd": f"download {zip_url} → {plugin_dir_str}",
                "stdout": "", "stderr": "",
                "url": zip_url,
            }

        # —— 默认：返回 URL/命令，由前端或用户处理 ——
        message = note or f"需手动安装，请访问: {url}"
        if cmd:
            message = f"{message}（运行命令: {cmd}）" if note else f"运行命令: {cmd}"
        return {
            "ok": False,  # 扩展安装不自动完成，需用户在 IDE 中操作
            "ide": ide_key, "mode": mode, "method": method,
            "message": message,
            "cmd": cmd, "stdout": "", "stderr": "",
            "url": url,
        }

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

    if method == "system_uninstall":
        # App 的 system_uninstall 仅用于卸载阶段；安装阶段降级为 manual
        # 提示用户去 url 下载 dmg/exe 手动安装
        fallback_url = url or meta.get("homepage", "")
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "manual",
            "message": f"App 需手动下载安装，请访问: {fallback_url}",
            "cmd": "", "stdout": "", "stderr": "",
            "url": fallback_url,
            "download_urls": meta.get("download_urls", {}),
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
        # macOS/Linux: curl -fsSL <script_url> | bash
        # Windows: irm <script_url_win> | iex（若配了 script_url_win，否则回退 manual）
        if sys.platform == "win32":
            script_url_win = install_meta.get("script_url_win", "")
            if not script_url_win:
                return {"ok": False, "ide": ide_key, "mode": mode, "method": "manual",
                        "message": f"需手动安装，请访问: {url or meta.get('homepage', '')}",
                        "cmd": "", "stdout": "", "stderr": "",
                        "url": url or meta.get("homepage", "")}
            # 使用 -ExecutionPolicy ByPass 避免被 PowerShell 执行策略拦截
            # （官方文档推荐此写法，见 openai/codex README）
            shell_cmd = f"irm {script_url_win} | iex"
            r = _run_cmd(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "ByPass", "-Command", shell_cmd],
                timeout=600,
            )
            # Windows 下安装脚本可能未完整执行（Rename/Copy 失败），补完 CLI 文件
            fix_msg = ""
            if r["ok"]:
                fix_msg = _fix_windows_cli_install(ide_key)
            msg = "安装成功" if r["ok"] else f"安装失败 (exit={r['returncode']})"
            if fix_msg:
                msg += f"；{fix_msg}"
            return {
                "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "script",
                "message": msg,
                "cmd": shell_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
            }
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

    if method == "powershell_script":
        # Windows PowerShell: irm <script_url> | iex
        # 非 Windows 平台回退 manual（PowerShell 脚本仅 Windows 适用）
        if sys.platform != "win32":
            return {
                "ok": False, "ide": ide_key, "mode": mode, "method": "manual",
                "message": f"需手动安装，请访问: {url or meta.get('homepage', '')}",
                "cmd": "", "stdout": "", "stderr": "",
                "url": url or meta.get("homepage", ""),
            }
        if not script_url:
            return {"ok": False, "ide": ide_key, "mode": mode, "method": "powershell_script",
                    "message": "未配置 script_url", "cmd": "", "stdout": "", "stderr": ""}
        shell_cmd = f"irm {script_url} | iex"
        r = _run_cmd(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "ByPass", "-Command", shell_cmd],
            timeout=600,
        )
        return {
            "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "powershell_script",
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
        npm_path = _find_npm()
        if not npm_path:
            # npm 不可用，尝试 script 回退（若配置了 script_url）
            script_url_fallback = install_meta.get("script_url", "")
            script_url_win_fallback = install_meta.get("script_url_win", "")
            if script_url_fallback or script_url_win_fallback:
                fallback_msg = "npm 不可用，回退到脚本安装"
            else:
                return {"ok": False, "ide": ide_key, "mode": mode, "method": "npm",
                        "message": "未安装 npm，请先安装 Node.js",
                        "cmd": "", "stdout": "", "stderr": ""}
        else:
            # 用绝对路径执行（GUI 进程 PATH 可能找不到 npm），
            # 并把 npm 所在目录注入子进程 PATH（npm 脚本内部需找到 node）
            # 用 os.path.dirname 而非 Path().parent：后者在 Windows 会把
            # POSIX 风格路径（如 /opt/...）反斜杠化，导致注入的 PATH 目录不一致
            npm_dir = os.path.dirname(npm_path)
            npm_flags = install_meta.get("npm_flags", "")
            if npm_flags:
                cmd = [npm_path, "install", "-g", package] + npm_flags.split()
            else:
                cmd = [npm_path, "install", "-g", package]
            r = _run_cmd(cmd, timeout=600, extra_path=[npm_dir])
            if r["ok"]:
                return {
                    "ok": True, "ide": ide_key, "mode": mode, "method": "npm",
                    "message": "安装成功",
                    "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
                }
            # npm 安装失败，尝试 --ignore-scripts（解决 sharp 等原生模块编译失败）
            r2 = None
            if "--ignore-scripts" not in npm_flags:
                r2 = _run_cmd([npm_path, "install", "-g", package, "--ignore-scripts"],
                              timeout=600, extra_path=[npm_dir])
            if r2 and r2["ok"]:
                return {
                    "ok": True, "ide": ide_key, "mode": mode, "method": "npm",
                    "message": "安装成功（使用 --ignore-scripts 跳过原生模块编译）",
                    "cmd": r2["cmd"], "stdout": r2["stdout"][-2000:], "stderr": r2["stderr"][-2000:],
                }
            # npm 仍失败，尝试 script 回退（若配置了 script_url）
            script_url_fallback = install_meta.get("script_url", "")
            script_url_win_fallback = install_meta.get("script_url_win", "")
            fallback_msg = f"npm 安装失败 (exit={r['returncode']}), 回退到脚本安装"

        # script 回退：npm 失败或 npm 不可用时，使用官方安装脚本
        if script_url_fallback or script_url_win_fallback:
            if sys.platform == "win32" and script_url_win_fallback:
                shell_cmd = f"irm {script_url_win_fallback} | iex"
                r = _run_cmd(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "ByPass", "-Command", shell_cmd],
                    timeout=600,
                )
                return {
                    "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "script",
                    "message": (f"{fallback_msg}成功" if r["ok"] else f"{fallback_msg}失败 (exit={r['returncode']})"),
                    "cmd": shell_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
                }
            elif script_url_fallback:
                if sys.platform == "win32":
                    # Windows 无 bash，用 PowerShell 执行 curl 管道
                    shell_cmd = f"curl -fsSL {script_url_fallback} | bash"
                    r = _run_cmd(["bash", "-c", shell_cmd], timeout=600)
                else:
                    shell_cmd = f"curl -fsSL {script_url_fallback} | bash"
                    r = _run_cmd(["bash", "-c", shell_cmd], timeout=600)
                return {
                    "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "script",
                    "message": (f"{fallback_msg}成功" if r["ok"] else f"{fallback_msg}失败 (exit={r['returncode']})"),
                    "cmd": shell_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
                }

        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "npm",
            "message": f"安装失败 (exit={r['returncode']})",
            "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }

    return {"ok": False, "ide": ide_key, "mode": mode, "method": method,
            "message": f"Unsupported method: {method}", "cmd": "", "stdout": "", "stderr": ""}


def _get_uninstall_cmd(install_meta: dict) -> str:
    """按平台选择卸载命令。

    支持的字段（按优先级）：
      1. uninstall_cmd_mac / uninstall_cmd_win — 平台专用
      2. uninstall_cmd — 通用（仅 macOS/Linux 下使用 bash 执行）
    """
    is_win = sys.platform == "win32"
    if is_win:
        cmd = install_meta.get("uninstall_cmd_win", "")
        if cmd:
            return cmd
    else:
        cmd = install_meta.get("uninstall_cmd_mac", "")
        if cmd:
            return cmd
    return install_meta.get("uninstall_cmd", "")


def _run_uninstall_cmd(cmd: str) -> dict:
    """执行卸载命令（按平台选择 shell）。

    macOS/Linux: bash -c '<cmd>'
    Windows:     cmd /c '<cmd>'
    """
    if sys.platform == "win32":
        return _run_cmd(["cmd", "/c", cmd], timeout=120)
    return _run_cmd(["bash", "-c", cmd], timeout=120)


def _do_windows_system_uninstall(ide_key: str, mode: str) -> dict | None:
    """Windows 系统级卸载：从注册表查 UninstallString 并执行产品自带卸载程序。

    Returns:
        卸载结果 dict，未找到卸载命令返回 None（由调用方回退）。
    """
    if sys.platform != "win32":
        return None
    try:
        from .detect import lookup_windows_uninstall_cmd, IDE_DETECT_META
    except Exception:
        return None
    # 用 IDE label 反查注册表卸载命令
    label = IDE_DETECT_META.get(ide_key, {}).get("label", ide_key)
    sys_cmd = lookup_windows_uninstall_cmd(label)
    if not sys_cmd:
        return None
    r = _run_uninstall_cmd(sys_cmd)
    return {
        "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "system_uninstall",
        "message": "已调用系统卸载程序" if r["ok"] else f"系统卸载失败 (exit={r['returncode']})",
        "cmd": sys_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
    }


def _do_system_uninstall(ide_key: str, mode: str, install_meta: dict, meta: dict, force: bool = False) -> dict:
    """系统级卸载（跨平台）。

    - Windows：优先注册表 UninstallString（产品自带卸载程序），失败回退 uninstall_cmd 强删
    - macOS：删 .app 目录 + uninstall_cmd
    - Linux：回退 uninstall_cmd
    - force=True：跳过系统卸载程序，直接 uninstall_cmd 强删（GUI 卸载器卡死/超时/需交互时用）
    """
    # Windows：优先系统卸载程序（force 模式跳过，直接走强删）
    if sys.platform == "win32" and not force:
        sys_result = _do_windows_system_uninstall(ide_key, mode)
        # 仅当系统卸载程序明确成功才返回；失败（GUI 卡死/超时/非零退出）则 fallback 强删
        if sys_result and sys_result.get("ok"):
            return sys_result
    # 回退/强制：配置的 uninstall_cmd（rmdir 强删目录）
    uninstall_cmd = _get_uninstall_cmd(install_meta)
    if uninstall_cmd:
        r = _run_uninstall_cmd(uninstall_cmd)
        ok = r["ok"]
        # exit=0 不代表目录真删掉（Windows `exit /b 0` / macOS `; true` 都会强制返回 0），
        # 需跨平台校验安装目录是否还在
        if ok:
            ok = not _app_dir_exists(ide_key, meta)
        msg_prefix = "强制卸载成功" if force else "卸载成功"
        msg_fail = "强制卸载失败" if force else "卸载失败"
        message = msg_prefix if ok else f"{msg_fail} (exit={r['returncode']}，目录可能被占用，请关闭进程后重试或手动删除)"
        return {
            "ok": ok, "ide": ide_key, "mode": mode, "method": "system_uninstall",
            "message": message,
            "cmd": uninstall_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
        }
    return {
        "ok": False, "ide": ide_key, "mode": mode, "method": "system_uninstall",
        "message": "未找到系统卸载程序，需手动卸载",
        "cmd": "", "stdout": "", "stderr": "",
        "url": meta.get("homepage", ""),
    }


def _app_dir_exists(ide_key: str, meta: dict) -> bool:
    """校验 IDE 安装目录是否仍存在（强删后校验用，跨平台）。

    - macOS：检查 macos_apps 路径（.app 是否还在）
    - Windows：检查 windows_apps 模板的父目录是否还在
    - Linux：无固定 GUI app 目录概念，返回 False（信任 uninstall_cmd 返回码）
    """
    try:
        from .detect import IDE_DETECT_META, _expand_windows_path
    except Exception:
        return False
    detect_meta = IDE_DETECT_META.get(ide_key, {})
    if sys.platform == "darwin":
        for ap in detect_meta.get("macos_apps", []):
            if Path(ap).exists():
                return True
        return False
    if sys.platform == "win32":
        for tmpl in detect_meta.get("windows_apps", []):
            p = _expand_windows_path(tmpl)
            if p.parent.exists():
                return True
    # Linux 等：无 GUI app 目录，不校验
    return False


def uninstall_ide(ide_key: str, mode: str = "cli", force: bool = False) -> dict:
    """卸载 IDE。

    Args:
        ide_key: IDE 标识
        mode: "cli" / "app" / "vscode" / "idea" / "acp"
        force: 强制卸载——跳过系统卸载程序，直接按 uninstall_cmd 强删目录。
               用于 GUI 卸载器卡死/超时/需交互弹窗的场景（如 Trae/Cursor app）。

    Returns:
        {ok: bool, ide: str, mode: str, method: str, message: str, cmd: str, stdout: str, stderr: str}
    """
    meta = IDE_INSTALL_META.get(ide_key)
    if not meta:
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "",
                "message": f"Unknown IDE: {ide_key}", "cmd": "", "stdout": "", "stderr": ""}

    # 扩展维度（vscode/idea/acp）：无自动卸载，提示用户在 IDE 中手动卸载
    if mode in ("vscode", "idea", "acp"):
        ext_meta = meta.get(f"{mode}_install", {})
        note = ext_meta.get("note", "")
        message = note or f"请在 IDE 中手动卸载 {ide_key} 的 {mode.upper()} 扩展"
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "manual",
            "message": message, "cmd": "", "stdout": "", "stderr": "",
            "url": ext_meta.get("url", "") or meta.get("homepage", ""),
        }

    if mode == "cli":
        install_meta = meta.get("cli_install", {})
    elif mode == "app":
        install_meta = meta.get("app_install", {})
    else:
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "",
                "message": f"Invalid mode: {mode}", "cmd": "", "stdout": "", "stderr": ""}

    method = install_meta.get("method", "manual")
    package = install_meta.get("package", "")

    if method == "system_uninstall":
        # 系统级卸载：Windows 优先调注册表 UninstallString（产品自带卸载程序），
        # macOS 删 .app，回退到 uninstall_cmd；force=True 跳过系统卸载程序直接强删
        return _do_system_uninstall(ide_key, mode, install_meta, meta, force=force)

    if method == "manual":
        # manual 但配了 uninstall_cmd：按平台选择卸载命令
        uninstall_cmd = _get_uninstall_cmd(install_meta)
        if uninstall_cmd:
            r = _run_uninstall_cmd(uninstall_cmd)
            return {
                "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "manual",
                "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
                "cmd": uninstall_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
            }
        # manual 无 uninstall_cmd：Windows 下尝试系统卸载（注册表 UninstallString）
        if sys.platform == "win32":
            sys_result = _do_windows_system_uninstall(ide_key, mode)
            if sys_result:
                return sys_result
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "manual",
            "message": "需手动卸载", "cmd": "", "stdout": "", "stderr": "",
        }

    if method == "script":
        # script 安装：按平台选择卸载命令（若配置），否则提示手动卸载
        uninstall_cmd = _get_uninstall_cmd(install_meta)
        if uninstall_cmd:
            r = _run_uninstall_cmd(uninstall_cmd)
            return {
                "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "script",
                "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
                "cmd": uninstall_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
            }
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "script",
            "message": "script 安装方式需手动卸载（请参考官方文档）",
            "cmd": "", "stdout": "", "stderr": "",
            "url": meta.get("homepage", ""),
        }

    if method == "powershell_script":
        # powershell_script 安装：按平台选择卸载命令（若配置），否则提示手动卸载
        uninstall_cmd = _get_uninstall_cmd(install_meta)
        if uninstall_cmd:
            r = _run_uninstall_cmd(uninstall_cmd)
            return {
                "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "powershell_script",
                "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
                "cmd": uninstall_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
            }
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "powershell_script",
            "message": "powershell_script 安装方式需手动卸载（请参考官方文档）",
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
        uninstall_cmd = _get_uninstall_cmd(install_meta)
        if uninstall_cmd:
            r = _run_uninstall_cmd(uninstall_cmd)
            return {
                "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "brew",
                "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
                "cmd": uninstall_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
            }
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "brew",
                "message": "未安装 Homebrew 或 brew uninstall 失败", "cmd": "", "stdout": "", "stderr": ""}

    if method == "cask":
        if shutil.which("brew"):
            cmd = ["brew", "uninstall", "--cask", package]
            r = _run_cmd(cmd, timeout=300)
            if r["ok"]:
                return {
                    "ok": True, "ide": ide_key, "mode": mode, "method": "cask",
                    "message": "卸载成功", "cmd": r["cmd"],
                    "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
                }
        # cask 失败或无 brew（Windows/Linux），fallback uninstall_cmd
        uninstall_cmd = _get_uninstall_cmd(install_meta)
        if uninstall_cmd:
            r = _run_uninstall_cmd(uninstall_cmd)
            return {
                "ok": r["ok"], "ide": ide_key, "mode": mode, "method": "cask",
                "message": "卸载成功" if r["ok"] else f"卸载失败 (exit={r['returncode']})",
                "cmd": uninstall_cmd, "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
            }
        return {"ok": False, "ide": ide_key, "mode": mode, "method": "cask",
                "message": "未安装 Homebrew 或 brew uninstall 失败", "cmd": "", "stdout": "", "stderr": ""}

    if method == "npm":
        # 获取 cli_names 用于校验二进制是否真正删除
        cli_names = IDE_INSTALL_META.get(ide_key, {}).get("cli_install", {}).get("cli_names", [])
        try:
            from .detect import IDE_DETECT_META
            cli_names = IDE_DETECT_META.get(ide_key, {}).get("cli_names", cli_names)
        except Exception:
            pass

        if not force:
            npm_path = _find_npm()
            if not npm_path:
                return {"ok": False, "ide": ide_key, "mode": mode, "method": "npm",
                        "message": "未安装 npm", "cmd": "", "stdout": "", "stderr": ""}
            cmd = [npm_path, "uninstall", "-g", package]
            # 用 os.path.dirname 而非 Path().parent：后者在 Windows 会把
            # POSIX 风格路径（如 /opt/...）反斜杠化，导致注入的 PATH 目录不一致
            r = _run_cmd(cmd, timeout=300, extra_path=[os.path.dirname(npm_path)])
            if r["ok"]:
                # npm uninstall 返回成功，但可能没真正删掉（多 npm 环境如 nvm vs homebrew）
                # 检查二进制是否还在，在则 fallback uninstall_cmd
                still_exists = any(shutil.which(n) for n in cli_names) if cli_names else False
                if not still_exists:
                    return {
                        "ok": True, "ide": ide_key, "mode": mode, "method": "npm",
                        "message": "卸载成功", "cmd": r["cmd"],
                        "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
                    }
        # force 模式 或 npm uninstall 失败/二进制仍在 → fallback uninstall_cmd 强删
        # 按平台选 shell：Windows 用 cmd /c，macOS/Linux 用 bash -c
        uninstall_cmd = _get_uninstall_cmd(install_meta)
        if uninstall_cmd:
            r2 = _run_uninstall_cmd(uninstall_cmd)
            ok = r2["ok"]
            # exit=0 不代表真删掉（Windows exit /b 0 / macOS ; true 都强制返回 0）
            # 校验 cli 二进制是否还在
            if ok and cli_names:
                ok = not any(shutil.which(n) for n in cli_names)
            msg_prefix = "强制卸载成功" if force else "卸载成功"
            msg_fail = "强制卸载失败" if force else "卸载失败"
            message = msg_prefix if ok else f"{msg_fail} (exit={r2['returncode']}，二进制可能被占用或 PATH 缓存，请重启终端后重试)"
            return {
                "ok": ok, "ide": ide_key, "mode": mode, "method": "npm",
                "message": message,
                "cmd": uninstall_cmd, "stdout": r2["stdout"][-2000:], "stderr": r2["stderr"][-2000:],
            }
        return {
            "ok": False, "ide": ide_key, "mode": mode, "method": "npm",
            "message": "卸载失败 (无 fallback uninstall_cmd)", "cmd": "", "stdout": "", "stderr": "",
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
    vscode_install = dict(meta.get("vscode_install", {}))
    idea_install = dict(meta.get("idea_install", {}))
    acp_install = dict(meta.get("acp_install", {}))
    web_install = dict(meta.get("web_install", {}))
    homepage = meta.get("homepage", "")

    # 非 macOS 平台：cask/brew/app_cli 降级为 manual + homepage，保留 uninstall_cmd
    if sys.platform != "darwin":
        if cli_install.get("method") in ("cask", "brew", "app_cli"):
            cli_install = {**cli_install, "method": "manual", "url": homepage}
        if app_install.get("method") == "cask":
            app_install = {**app_install, "method": "manual", "url": homepage}

    # 非 Windows 平台：powershell_script 降级为 manual（PowerShell 脚本仅 Windows 适用）
    if sys.platform != "win32" and cli_install.get("method") == "powershell_script":
        cli_install = {"method": "manual", "url": homepage}

    return {
        "ide": ide_key,
        "available": True,
        "label": meta.get("label", ide_key),
        "version": meta.get("version", ""),
        "release_date": meta.get("release_date", ""),
        "homepage": homepage,
        "docs_url": meta.get("docs_url", ""),
        "release_url": meta.get("release_url", ""),
        "download_urls": meta.get("download_urls", {}),
        "install_methods": meta.get("install_methods", []),
        # 新分类字段：品牌 + 顶层 Code/Work + 形式子集
        # 用于 AIDE 管理页按品牌分组卡片化展示（每个品牌一张大卡片，
        # 卡片内按 Code/Work 顶层分组，再按 cli/app/vscode/idea 子形式分行）
        "brand": meta.get("brand") or "",
        "category": meta.get("category") or "",
        "forms": meta.get("forms") or [],
        # 兼容字段：旧 categories（app/cli/vscode/jetbrains 平铺列表）
        # 从新 forms 字段派生，保证旧前端代码不破坏
        "categories": meta.get("categories") or meta.get("forms") or _infer_categories(meta),
        "cli": cli_install,
        "app": app_install,
        "vscode": vscode_install,
        "idea": idea_install,
        "acp": acp_install,
        "web": web_install,
    }


def _infer_categories(meta: dict) -> list[str]:
    """根据 cli_install/app_install 推断 categories（向后兼容旧 IDE 配置）。

    缺省规则：
    - 有 app_install 且 method != manual-only → 'app'
    - 有 cli_install 且 method != manual-only → 'cli'
    都没有则返回空列表（如 Agents 占位符）。
    """
    cats: list[str] = []
    cli_install = meta.get("cli_install", {})
    app_install = meta.get("app_install", {})
    # app：必须有 method 且不是纯 manual（manual 仅给下载页，不算 App 安装能力）
    if app_install.get("method") and app_install.get("method") != "manual":
        cats.append("app")
    elif app_install.get("method") == "manual" and meta.get("download_urls"):
        # manual + 有下载地址也算 App（如 KimiWork 桌面应用）
        cats.append("app")
    if cli_install.get("method") and cli_install.get("method") != "manual":
        cats.append("cli")
    elif cli_install.get("method") == "manual" and meta.get("download_urls"):
        cats.append("cli")
    return cats


__all__ = ["IDE_INSTALL_META", "install_ide", "uninstall_ide", "reinstall_ide",
           "get_install_info", "validate_ide_meta"]
