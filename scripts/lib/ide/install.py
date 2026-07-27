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


# ===== IDE 安装元数据（按上述 Schema 规范配置） =====
# 更新日期：2026-07-19
# 数据来源：各 IDE 官网/官方文档/GitHub Releases（详见各条目注释）
IDE_INSTALL_META = {
    "Claude": {
        # Anthropic 官方 Claude Code
        # 最新版本：v2.1.150（2026-05-23）—— native installer 自动更新，无需手动升级
        # 来源：https://code.claude.com/docs/en/setup + https://www.npmjs.com/package/@anthropic-ai/claude-code
        "label": "Claude Code",
        "version": "2.1.150",
        "release_date": "2026-05-23",
        "homepage": "https://claude.ai/download",
        "docs_url": "https://code.claude.com/docs/en/setup",
        "release_url": "https://github.com/anthropics/claude-code/releases",
        "cli_install": {
            # npm 安装更可靠（script 方式依赖 claude.ai，国内可能不可达）
            "method": "npm",
            "package": "@anthropic-ai/claude-code",
            "url": "https://claude.ai/download",
            "script_url": "https://claude.ai/install.sh",
            "script_url_win": "https://claude.ai/install.ps1",
            # 卸载：覆盖 native（~/.local/bin+share）+ npm + legacy（~/.claude/local）+ 配置（~/.claude+~/.claude.json）
            "uninstall_cmd_mac": "rm -f ~/.local/bin/claude; rm -rf ~/.local/share/claude ~/.claude/local ~/.claude; rm -f ~/.claude.json; npm uninstall -g @anthropic-ai/claude-code 2>/dev/null; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\claude.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.local\\share\\claude\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.claude\\local\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.claude\" 2>nul & del /q \"%USERPROFILE%\\.claude.json\" 2>nul & npm uninstall -g @anthropic-ai/claude-code 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://claude.ai/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/Claude.app' ~/.claude 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\claude\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.claude\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://claude.ai/api/desktop/darwin/arm64/dmg/latest/redirect",
            "macos_x64": "https://claude.ai/api/desktop/darwin/x64/dmg/latest/redirect",
            "windows_x64": "https://claude.ai/download",
            "windows_arm64": "https://claude.ai/download",
        },
        # Claude Code ACP：通过 ACP 协议接入 JetBrains IDE
        # 来源：https://www.jetbrains.com/acp/（ACP Registry）
        # 安装适配器：npm install -g @anthropic-ai/claude-code，运行 claude acp
        "acp_install": {
            "method": "manual",
            "url": "https://www.jetbrains.com/acp/",
            "cmd": "claude acp",
            "note": "在 JetBrains IDE AI Assistant 中配置 ACP 智能体，运行 claude acp 后连接",
        },
        "install_methods": ["script", "npm", "brew", "winget", "acp"],
        # 品牌：Anthropic 旗下 Claude 品牌
        "brand": "Claude",
        # 顶层分类：code（编程）/ work（办公）
        "category": "code",
        # forms：Code 下的形式子集（cli/app/vscode/jetbrains/acp），Work 类一般仅 app
        "forms": ["cli", "app", "acp"],
    },
    "Codex": {
        # OpenAI Codex CLI + Desktop App
        # 最新版本：v0.144.5（2026-07-17）
        # 来源：https://www.npmjs.com/package/@openai/codex + https://developers.openai.com/codex
        "label": "Codex",
        "version": "0.144.5",
        "release_date": "2026-07-17",
        "homepage": "https://openai.com/codex",
        "docs_url": "https://developers.openai.com/codex/cli",
        "release_url": "https://github.com/openai/codex/releases",
        "cli_install": {
            # npm 安装更可靠（script 方式依赖 chatgpt.com，国内可能不可达）
            "method": "npm",
            "package": "@openai/codex",
            "url": "https://developers.openai.com/codex/cli",
            "script_url": "https://chatgpt.com/codex/install.sh",
            "script_url_win": "https://chatgpt.com/codex/install.ps1",
            "uninstall_cmd_mac": "rm -f ~/.local/bin/codex; rm -rf ~/.local/share/codex ~/.codex; npm uninstall -g @openai/codex 2>/dev/null; rm -rf /opt/homebrew/lib/node_modules/@openai/codex ~/.nvm/versions/node/*/lib/node_modules/@openai/codex; true",
            "uninstall_cmd_win": "rmdir /s /q \"%APPDATA%\\npm\\node_modules\\@openai\\codex\" 2>nul & del /q \"%APPDATA%\\npm\\codex\" \"%APPDATA%\\npm\\codex.cmd\" \"%APPDATA%\\npm\\codex.ps1\" 2>nul & del /q \"%USERPROFILE%\\.local\\bin\\codex.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.local\\share\\codex\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.codex\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://developers.openai.com/codex/app",
            "uninstall_cmd_mac": "rm -rf '/Applications/Codex.app' ~/.codex 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\codex\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.codex\" 2>nul & exit /b 0",
        },
        "download_urls": {
            # 来源：https://developers.openai.com/codex/app
            "macos_arm64": "https://persistent.oaistatic.com/codex-app-prod/Codex.dmg",
            "macos_x64": "https://persistent.oaistatic.com/codex-app-prod/Codex-latest-x64.dmg",
            "windows_x64": "https://get.microsoft.com/installer/download/9PLM9XGG6VKS?cid=website_cta_psi",
        },
        # Codex VSCode 扩展：openai.chatgpt（发布者 openai）
        # 来源：https://marketplace.visualstudio.com/items?itemName=openai.chatgpt
        "vscode_install": {
            "method": "manual",
            "url": "https://marketplace.visualstudio.com/items?itemName=openai.chatgpt",
            "note": "在 VS Code 扩展市场搜索 ChatGPT（扩展 ID: openai.chatgpt）安装",
        },
        # Codex JetBrains：2025.3+ 原生集成（无需插件）
        # 来源：https://developers.openai.com/codex/app
        "jetbrains_install": {
            "method": "manual",
            "url": "https://developers.openai.com/codex/app",
            "note": "JetBrains 2025.3+ 原生集成 Codex（IntelliJ IDEA/PyCharm/WebStorm 等），无需安装插件",
        },
        # Codex ACP：通过 ACP 协议接入 JetBrains IDE
        # 来源：https://www.jetbrains.com/acp/（ACP Registry）
        "acp_install": {
            "method": "manual",
            "url": "https://www.jetbrains.com/acp/",
            "cmd": "codex acp",
            "note": "在 JetBrains IDE AI Assistant 中配置 ACP 智能体，运行 codex acp 后连接",
        },
        "install_methods": ["script", "npm", "brew", "app", "vscode", "jetbrains", "acp"],
        "categories": ["cli", "app", "vscode", "jetbrains", "acp"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Codex", "category": "code", "forms": ['cli', 'app', 'vscode', 'jetbrains', 'acp'],
    },
    "Cursor": {
        # Cursor IDE（基于 VS Code 的 AI 编辑器）+ agent CLI
        # 最新版本：v3.2.16（2026-04-29）
        # 来源：https://www.cursor.com/downloads + https://cursor.com/cn/docs/cli/installation
        "label": "Cursor",
        "version": "3.2.16",
        "release_date": "2026-04-29",
        "homepage": "https://cursor.com",
        "docs_url": "https://cursor.com/cn/docs/cli/installation",
        "release_url": "https://www.cursor.com/changelog",
        "cli_install": {
            # 官方 CLI 安装脚本（跨平台），命令名为 agent
            "method": "script",
            "script_url": "https://cursor.com/install",
            "script_url_win": "https://cursor.com/install?win32=true",
            "url": "https://cursor.com/cn/docs/cli/installation",
            # 卸载：删除 native binary（agent）+ 配置目录
            "uninstall_cmd_mac": "rm -f ~/.local/bin/agent; rm -rf ~/.cursor; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\agent.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.cursor\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://www.cursor.com/downloads",
            "uninstall_cmd_mac": "rm -rf '/Applications/Cursor.app' ~/.cursor 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\cursor\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.cursor\" 2>nul & exit /b 0",
        },
        # Cursor 基于 VS Code 内核（App 即 VSCode 体验），无需单独 VSCode 扩展
        "vscode_install": {
            "method": "manual",
            "url": "https://marketplace.visualstudio.com/search?term=cursor",
            "note": "Cursor 桌面版基于 VS Code 内核，安装 App 即可获得 VSCode 体验。如需在 VS Code 中使用 Cursor，可在扩展市场搜索",
        },
        # Cursor JetBrains：通过 ACP（Agent Client Protocol）协议支持
        # 文档：https://cursor.com/cn/docs/cli/installation
        "jetbrains_install": {
            "method": "manual",
            "url": "https://plugins.jetbrains.com/search?search=cursor+acp",
            "note": "在 JetBrains IDE 插件市场搜索 Cursor ACP 安装（支持 IntelliJ IDEA/PyCharm/WebStorm 等）",
        },
        "download_urls": {
            # Cursor 官方下载页提供按平台/架构的稳定直链（universal 包同时支持 arm64/x64）
            "macos_arm64": "https://download.todesktop.com/230313mzl4w4u92/Cursor-darwin-arm64.dmg",
            "macos_x64": "https://download.todesktop.com/230313mzl4w4u92/Cursor-darwin-x64.dmg",
            "windows_x64": "https://download.todesktop.com/230313mzl4w4u92/win32-x64/CursorSetup.exe",
            "windows_arm64": "https://download.todesktop.com/230313mzl4w4u92/win32-arm64/CursorSetup.exe",
            "linux_x64": "https://download.todesktop.com/230313mzl4w4u92/linux-x64/Cursor.AppImage",
        },
        "install_methods": ["script", "app", "jetbrains"],
        "categories": ["app", "cli", "vscode", "jetbrains"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        # Cursor ACP：通过 ACP 协议接入 JetBrains IDE
        # 来源：https://www.jetbrains.com/acp/（ACP Registry）
        # 运行 cursor agent acp，在 JetBrains AI chat 中连接
        "acp_install": {
            "method": "manual",
            "url": "https://www.jetbrains.com/acp/",
            "cmd": "cursor agent acp",
            "note": "在 JetBrains IDE AI Assistant 中配置 ACP 智能体，运行 cursor agent acp 后连接",
        },
        "brand": "Cursor", "category": "code", "forms": ['app', 'cli', 'vscode', 'jetbrains', 'acp'],
    },
    "Trae": {
        # 字节跳动 Trae 国际版（无独立 CLI，仅 App）
        # 最新版本：v3.3.62（2026-07-18）
        # 来源：https://www.trae.ai/
        "label": "Trae",
        "version": "3.3.62",
        "release_date": "2026-07-18",
        "homepage": "https://www.trae.ai",
        "docs_url": "https://docs.trae.ai/",
        "release_url": "https://www.trae.ai/changelog",
        "cli_install": {"method": "manual", "url": "https://www.trae.ai"},
        "app_install": {
            "method": "system_uninstall",
            "url": "https://www.trae.ai/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/Trae.app' ~/.trae 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\Trae\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.trae\" 2>nul & exit /b 0",
        },
        "download_urls": {
            # Trae 国际版官网提供按平台/架构的下载入口（页面动态生成签名链接，故用下载页）
            "macos_arm64": "https://www.trae.ai/download",
            "macos_x64": "https://www.trae.ai/download",
            "windows_x64": "https://www.trae.ai/download",
            "linux_x64": "https://www.trae.ai/download",
        },
        "install_methods": ["app"],
        "categories": ["app"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Trae", "category": "code", "forms": ['app'],
    },
    "TraeCN": {
        # 字节跳动 Trae 国内版（含 trae-cli TUI + App）
        # 最新版本：v3.3.62（2026-07-18）
        # 来源：https://www.trae.cn/
        # CLI 文档：https://docs.trae.cn/cli_get-started-with-trae-cli
        "label": "Trae CN",
        "version": "3.3.62",
        "release_date": "2026-07-18",
        "homepage": "https://www.trae.cn",
        "docs_url": "https://docs.trae.cn/cli_get-started-with-trae-cli",
        "release_url": "https://www.trae.cn/changelog",
        "cli_install": {
            # 官方安装脚本：
            #   macOS/Linux: sh -c "$(curl -L https://trae.cn/trae-cli/install.sh)"
            #   Windows:     irm https://trae.cn/trae-cli/install.ps1 | iex
            # 用 script method（跨平台），script_url 走 .sh，script_url_win 走 .ps1
            "method": "script",
            "script_url": "https://trae.cn/trae-cli/install.sh",
            "script_url_win": "https://trae.cn/trae-cli/install.ps1",
            "url": "https://docs.trae.cn/cli_get-started-with-trae-cli",
            "uninstall_cmd_mac": "rm -f ~/.local/bin/trae-cli ~/.local/bin/traecli && rm -rf ~/.local/share/trae-cli",
            "uninstall_cmd_win": "powershell -NoProfile -Command \"Remove-Item -Recurse -Force $env:USERPROFILE\\.trae-cli -ErrorAction SilentlyContinue; Remove-Item -Force $env:USERPROFILE\\.local\\bin\\trae-cli.exe -ErrorAction SilentlyContinue; Remove-Item -Force $env:USERPROFILE\\.local\\bin\\traecli.exe -ErrorAction SilentlyContinue\"",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://www.trae.cn/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/Trae CN.app' ~/.trae-cn ~/.traecn 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\Trae CN\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.trae-cn\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.traecn\" 2>nul & exit /b 0",
        },
        # Trae CN 本身基于 VS Code（App 形式即 VSCode 体验），另有 JetBrains 插件
        # TRAE AI 插件支持 VSCode 1.93+ 和 JetBrains 2022.1+
        # 来源：https://www.trae.cn/plugin
        # VSCode 扩展 ID: MarsCode.marscode-extension
        # 安装方式：vscode:extension/ 协议直接打开 VSCode 扩展安装页
        "vscode_install": {
            "method": "extension",
            "url": "vscode:extension/MarsCode.marscode-extension",
            "extension_id": "MarsCode.marscode-extension",
            "note": "点击安装将在 VS Code 中打开扩展页面（需 VS Code 1.93+）",
        },
        "jetbrains_install": {
            "method": "extension",
            "url": "jetbrains://plugin/24326",
            "extension_id": "24326",
            "note": "点击安装将在 JetBrains IDE 中打开插件安装页面（需 JetBrains 2022.1+）",
        },
        "download_urls": {
            # 国内版提供按平台/架构的下载入口（动态签名链接，故用下载页）
            "macos_arm64": "https://www.trae.cn/download",
            "macos_x64": "https://www.trae.cn/download",
            "windows_x64": "https://www.trae.cn/download",
            "linux_x64": "https://www.trae.cn/download",
            "linux_arm64": "https://www.trae.cn/download",
        },
        "install_methods": ["script", "app", "jetbrains"],
        "categories": ["app", "cli", "vscode", "jetbrains"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Trae CN", "category": "code", "forms": ['app', 'cli', 'vscode', 'jetbrains'],
    },
    "TraeSoloCN": {
        # 字节跳动 Trae Solo CN（独立 Solo 模式国内版）
        # 最新版本：随 Trae CN 同步发布
        # 来源：https://www.trae.cn/
        "label": "Trae Solo CN",
        "version": "3.3.62",
        "release_date": "2026-07-18",
        "homepage": "https://www.trae.cn",
        "docs_url": "https://www.trae.cn/docs/solo",
        "release_url": "https://www.trae.cn/changelog",
        "cli_install": {
            "method": "manual",
            "url": "https://www.trae.cn",
            "uninstall_cmd_mac": "rm -rf ~/.trae-solo-cn ~/.traesolocn 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%USERPROFILE%\\.trae-solo-cn\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.traesolocn\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://www.trae.cn/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/Trae Solo CN.app' ~/.trae-solo-cn ~/.traesolocn 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\Trae Solo CN\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.trae-solo-cn\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.traesolocn\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://www.trae.cn/download",
            "macos_x64": "https://www.trae.cn/download",
            "windows_x64": "https://www.trae.cn/download",
        },
        "install_methods": ["app"],
        "categories": ["app"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Trae Work", "category": "work", "forms": ['app'],
    },
    "OpenCode": {
        # OpenCode（开源 AI 编码代理，anomalyco 维护）
        # 来源：https://opencode.ai/docs/  (截至 2026-07-19)
        # 官方推荐 curl -fsSL https://opencode.ai/install | bash（仅 macOS/Linux）
        # Windows 官方无 PowerShell 脚本（/install.ps1 返回 404），使用 Chocolatey/Scoop/NPM
        # Homebrew 推荐 tap：anomalyco/tap/opencode（更新及时），brew install opencode 是官方 formula（更新慢）
        # 无独立 Desktop App 下载页（/downloads 返回 404），App 安装走 GitHub Releases
        "label": "OpenCode",
        "version": "latest",
        "release_date": "2026-07-19",
        "homepage": "https://opencode.ai",
        "docs_url": "https://opencode.ai/docs/",
        "release_url": "https://github.com/anomalyco/opencode/releases",
        "cli_install": {
            # npm 安装更可靠（script 方式仅 macOS/Linux，Windows 无 PowerShell 脚本）
            "method": "npm",
            "package": "opencode-ai",
            "url": "https://opencode.ai/docs/",
            "script_url": "https://opencode.ai/install",
            "uninstall_cmd_mac": "rm -f ~/.local/bin/opencode; rm -rf ~/.config/opencode ~/.local/share/opencode; npm uninstall -g opencode-ai 2>/dev/null; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\opencode.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.config\\opencode\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.local\\share\\opencode\" 2>nul & npm uninstall -g opencode-ai 2>nul & exit /b 0",
        },
        "app_install": {
            # OpenCode 无独立 Desktop App 下载页，走 GitHub Releases 手动下载二进制
            "method": "manual",
            "url": "https://github.com/anomalyco/opencode/releases/latest",
            "uninstall_cmd_mac": "rm -rf '/Applications/OpenCode.app' ~/.config/opencode ~/.local/share/opencode 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\opencode\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.config\\opencode\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://github.com/anomalyco/opencode/releases/latest",
            "macos_x64": "https://github.com/anomalyco/opencode/releases/latest",
            "windows_x64": "https://github.com/anomalyco/opencode/releases/latest",
            "windows_arm64": "https://github.com/anomalyco/opencode/releases/latest",
            "linux_x64": "https://github.com/anomalyco/opencode/releases/latest",
            "linux_arm64": "https://github.com/anomalyco/opencode/releases/latest",
        },
        # 官方支持的安装方式（按平台分组）：
        #  - macOS/Linux: script / npm / brew (tap) / mise / docker / arch (pacman/paru)
        #  - Windows: choco / scoop / npm / mise / docker
        #  - 跨平台: bun / pnpm / yarn（基于 npm 包 opencode-ai）
        "install_methods": ["script", "npm", "brew", "choco", "scoop", "mise", "docker", "arch", "bun", "pnpm", "yarn"],
        "categories": ["cli"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        # OpenCode ACP：通过 ACP 协议接入 JetBrains IDE
        # 来源：https://www.jetbrains.com/acp/（ACP Registry）
        "acp_install": {
            "method": "manual",
            "url": "https://www.jetbrains.com/acp/",
            "cmd": "opencode acp",
            "note": "在 JetBrains IDE AI Assistant 中配置 ACP 智能体，运行 opencode acp 后连接",
        },
        "brand": "OpenCode", "category": "code", "forms": ['cli', 'acp'],
    },
    "Qoder": {
        # Qoder 国际版（阿里云通义灵码升级版）
        # 最新版本：v1.4.1（2026-06）
        # 来源：https://qoder.com/zh/download
        "label": "Qoder",
        "version": "1.4.1",
        "release_date": "2026-06-28",
        "homepage": "https://qoder.com",
        "docs_url": "https://qoder.com/zh/docs",
        "release_url": "https://qoder.com/zh/changelog",
        "cli_install": {
            "method": "script",
            "script_url": "https://qoder.com/install",
            "script_url_win": "https://qoder.com/install.ps1",
            "url": "https://qoder.com/zh/cli",
            "uninstall_cmd_mac": "rm -f ~/.local/bin/qoder; rm -rf ~/.qoder; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\qoder.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.qoder\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://qoder.com/zh/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/Qoder.app' ~/.qoder 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\Qoder\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.qoder\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://qoder.com/zh/download",
            "macos_x64": "https://qoder.com/zh/download",
            "windows_x64": "https://qoder.com/zh/download",
            "linux_x64": "https://qoder.com/zh/download",
        },
        "install_methods": ["script", "app"],
        "categories": ["app", "cli"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Qoder", "category": "code", "forms": ['app', 'cli'],
    },
    "QoderCN": {
        # Qoder 国内版（阿里云通义灵码升级版，国内合规）
        # 最新版本：v1.4.1（2026-06）
        # 来源：https://qoder.com.cn/download + https://qoder.com.cn/cli
        "label": "Qoder CN",
        "version": "1.4.1",
        "release_date": "2026-06-28",
        "homepage": "https://qoder.com.cn",
        "docs_url": "https://help.aliyun.com/zh/lingma/qoder-cn/user-guide/installation-guide",
        "release_url": "https://qoder.com.cn/changelog",
        "cli_install": {
            "method": "script",
            "script_url": "https://qoder.com.cn/install",
            "script_url_win": "https://qoder.com.cn/install.ps1",
            "url": "https://qoder.com.cn/cli",
            "uninstall_cmd_mac": "rm -f ~/.local/bin/qoderclicn ~/.local/bin/qoder-cn; rm -rf ~/.qoder-cn ~/.qodercn; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\qoderclicn.exe\" \"%USERPROFILE%\\.local\\bin\\qoder-cn.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.qoder-cn\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.qodercn\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://qoder.com.cn/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/Qoder CN.app' ~/.qoder-cn ~/.qodercn 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\Qoder CN\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.qoder-cn\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.qodercn\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://qoder.com.cn/download",
            "macos_x64": "https://qoder.com.cn/download",
            "windows_x64": "https://qoder.com.cn/download",
            "linux_x64": "https://qoder.com.cn/download",
        },
        "install_methods": ["script", "app"],
        "categories": ["app", "cli"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Qoder CN", "category": "code", "forms": ['app', 'cli'],
    },
    "OpenClaw": {
        # OpenClaw（开源个人 AI 助手平台 / Agent 调度框架）
        # 官网：https://openclaw.ai
        # 文档：https://docs.openclaw.ai
        # GitHub：https://github.com/openclaw/openclaw
        # 安装方式（按优先级）：
        #   1. npm: npm install -g openclaw@latest（跨平台，需 Node.js >= 22.14.0）
        #   2. 脚本: macOS/Linux: curl -fsSL https://openclaw.ai/install.sh | bash
        #            Windows:     iwr -useb https://openclaw.ai/install.ps1 | iex
        # 配置目录：~/.openclaw/（openclaw.json 主配置）
        # CLI 命令：openclaw（TUI 交互式 + gateway 服务管理）
        "label": "OpenClaw",
        "version": "latest",
        "release_date": "2026-07-01",
        "homepage": "https://openclaw.ai",
        "docs_url": "https://docs.openclaw.ai",
        "release_url": "https://github.com/openclaw/openclaw/releases",
        "cli_install": {
            # npm 安装（跨平台首选），失败时可回退到 script 方式
            "method": "npm",
            "package": "openclaw",
            "url": "https://openclaw.ai",
            "script_url": "https://openclaw.ai/install.sh",
            "script_url_win": "https://openclaw.ai/install.ps1",
            "uninstall_cmd_mac": "npm uninstall -g openclaw 2>/dev/null; rm -f $(which openclaw) 2>/dev/null; rm -rf ~/.openclaw ~/.local/share/openclaw; true",
            "uninstall_cmd_win": "npm uninstall -g openclaw 2>nul & rmdir /s /q \"%APPDATA%\\npm\\node_modules\\openclaw\" 2>nul & del /q \"%APPDATA%\\npm\\openclaw\" \"%APPDATA%\\npm\\openclaw.cmd\" \"%APPDATA%\\npm\\openclaw.ps1\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.openclaw\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "manual",
            "url": "https://openclaw.ai",
        },
        "download_urls": {
            "macos_arm64": "https://openclaw.ai",
            "macos_x64": "https://openclaw.ai",
            "windows_x64": "https://openclaw.ai",
            "linux_x64": "https://openclaw.ai",
        },
        "install_methods": ["npm", "script"],
        "categories": ["cli"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "OpenClaw", "category": "code", "forms": ['cli'],
    },
    "Hermes": {
        # Hermes Agent（内部 Agent 平台，暂无公开下载）
        "label": "Hermes Agent",
        "version": "",
        "release_date": "",
        "homepage": "",
        "docs_url": "",
        "release_url": "",
        "cli_install": {"method": "manual", "url": ""},
        "app_install": {"method": "manual", "url": ""},
        "download_urls": {},
        "install_methods": [],
        "categories": ["cli"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Hermes", "category": "code", "forms": ['cli'],
    },
    "WorkBuddy": {
        # WorkBuddy（腾讯 CodeBuddy 团队 AI 智能体桌面工作台）
        # 官网：https://www.workbuddy.cn
        # 安装文档：https://cloud.tencent.com/document/product/1831/134387
        "label": "WorkBuddy",
        "version": "latest",
        "release_date": "2026-06-01",
        "homepage": "https://www.workbuddy.cn",
        "docs_url": "https://cloud.tencent.com/document/product/1831/134387",
        "release_url": "https://www.workbuddy.cn",
        "cli_install": {
            "method": "manual",
            "url": "https://www.workbuddy.cn",
            "uninstall_cmd_mac": "rm -f ~/.local/bin/workbuddy; rm -rf ~/.workbuddy; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\workbuddy.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.workbuddy\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://www.workbuddy.cn",
            "uninstall_cmd_mac": "rm -rf /Applications/WorkBuddy.app ~/.workbuddy 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\WorkBuddy\" 2>nul & rmdir /s /q \"%LOCALAPPDATA%\\WorkBuddy\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.workbuddy\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://www.workbuddy.cn",
            "macos_x64": "https://www.workbuddy.cn",
            "windows_x64": "https://www.workbuddy.cn",
            "linux_x64": "https://www.workbuddy.cn",
        },
        "install_methods": ["app"],
        "categories": ["app"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "WorkBuddy", "category": "work", "forms": ['app'],
    },
    "ZCode": {
        # 智谱 ADE ZCode（AgentBuddy/ZCode 智能体编程平台）
        # 最新版本：3.0+
        # 来源：https://zcode.z.ai/cn
        "label": "ZCode",
        "version": "3.0+",
        "release_date": "2026-06-01",
        "homepage": "https://zcode.z.ai/cn",
        "docs_url": "https://zcode.z.ai/cn/docs",
        "release_url": "https://zcode.z.ai/cn/changelog",
        "cli_install": {
            "method": "manual",
            "url": "https://zcode.z.ai/cn",
            "uninstall_cmd_mac": "rm -f ~/.local/bin/zcode; rm -rf ~/.zcode; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\zcode.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.zcode\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://zcode.z.ai/cn/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/ZCode.app' ~/.zcode 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\ZCode\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.zcode\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://zcode.z.ai/cn/download",
            "macos_x64": "https://zcode.z.ai/cn/download",
            "windows_x64": "https://zcode.z.ai/cn/download",
            "linux_x64": "https://zcode.z.ai/cn/download",
        },
        "install_methods": ["app"],
        "categories": ["app"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "ZCode", "category": "code", "forms": ['app'],
    },
    "IDEA": {
        # JetBrains IntelliJ IDEA（Community / Ultimate）
        # 来源：https://www.jetbrains.com/idea
        "label": "IntelliJ IDEA",
        "version": "2026.2",
        "release_date": "2026-07-01",
        "homepage": "https://www.jetbrains.com/idea",
        "docs_url": "https://www.jetbrains.com/help/idea/getting-started.html",
        "release_url": "https://www.jetbrains.com/idea/whatsnew/",
        "cli_install": {
            "method": "manual",
            "url": "https://www.jetbrains.com/idea/download",
            "uninstall_cmd_mac": "rm -f ~/.local/bin/idea; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\idea.exe\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://www.jetbrains.com/idea/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/IntelliJ IDEA.app' '/Applications/IntelliJ IDEA CE.app' ~/.idea ~/.jetbrains 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\JetBrains\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.idea\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://www.jetbrains.com/idea/download/",
            "macos_x64": "https://www.jetbrains.com/idea/download/",
            "windows_x64": "https://www.jetbrains.com/idea/download/",
            "linux_x64": "https://www.jetbrains.com/idea/download/",
        },
        "install_methods": ["app", "toolbox"],
        "categories": ["app", "jetbrains"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "JetBrains", "category": "code", "forms": ['app', 'jetbrains'],
    },
    "Agents": {
        # 通用 Agents（占位符，无独立下载源）
        "label": "Agents",
        "version": "",
        "release_date": "",
        "homepage": "",
        "docs_url": "",
        "release_url": "",
        "cli_install": {"method": "manual", "url": ""},
        "app_install": {"method": "manual", "url": ""},
        "download_urls": {},
        "install_methods": [],
        "hidden": True,  # 占位符，不在 UI 显示
        "categories": [],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "", "category": "", "forms": [],
    },
    "KimiCLI": {
        # Kimi CLI（旧版 Python/uv CLI，Moonshot AI）
        # 仓库：https://github.com/MoonshotAI/kimi-cli
        # 文档：https://platform.moonshot.cn/docs/guide/kimi-cli-support
        # 状态：技术预览版，正逐步迁移到新版 Kimi Code CLI
        "label": "Kimi CLI",
        "version": "0.3.0",
        "release_date": "2026-06-15",
        "homepage": "https://platform.moonshot.cn/docs/guide/kimi-cli-support",
        "docs_url": "https://platform.moonshot.cn/docs/guide/kimi-cli-support",
        "release_url": "https://github.com/MoonshotAI/kimi-cli/releases",
        "cli_install": {
            "method": "manual",
            "url": "https://platform.moonshot.cn/docs/guide/kimi-cli-support",
            # uv 安装命令：uv tool install --python 3.13 kimi-cli
            # 卸载：移除 uv tool + 配置目录
            "uninstall_cmd_mac": "uv tool uninstall kimi-cli 2>/dev/null; rm -rf ~/.kimi; true",
            "uninstall_cmd_win": "uv tool uninstall kimi-cli 2>nul & rmdir /s /q \"%USERPROFILE%\\.kimi\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "manual",
            "url": "https://platform.moonshot.cn/docs/guide/kimi-cli-support",
        },
        "download_urls": {
            "macos_arm64": "https://platform.moonshot.cn/docs/guide/kimi-cli-support",
            "macos_x64": "https://platform.moonshot.cn/docs/guide/kimi-cli-support",
            "windows_x64": "https://platform.moonshot.cn/docs/guide/kimi-cli-support",
            "linux_x64": "https://platform.moonshot.cn/docs/guide/kimi-cli-support",
        },
        "install_methods": ["manual"],
        "categories": ["cli"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Kimi", "category": "code", "forms": ['cli'],
    },
    "KimiCode": {
        # Kimi Code（新版 Node.js 二进制 CLI，Moonshot AI）
        # 仓库：https://github.com/MoonshotAI/kimi-code
        # 文档：https://moonshotai.github.io/kimi-code/zh/
        # 安装：官方脚本，二进制发行，零环境依赖（不需要预装 Node.js）
        # 支持 ACP 编辑器集成（VSCode/JetBrains 等）
        "label": "Kimi Code",
        "version": "0.4.0",
        "release_date": "2026-07-22",
        "homepage": "https://code.kimi.com",
        "docs_url": "https://moonshotai.github.io/kimi-code/zh/",
        "release_url": "https://github.com/MoonshotAI/kimi-code/releases",
        "cli_install": {
            "method": "script",
            "script_url": "https://code.kimi.com/kimi-code/install.sh",
            "script_url_win": "https://code.kimi.com/kimi-code/install.ps1",
            "url": "https://code.kimi.com",
            # 卸载：删除二进制 + 配置目录
            "uninstall_cmd_mac": "rm -f $(which kimi) 2>/dev/null; rm -rf ~/.kimi-code; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\.local\\bin\\kimi.exe\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.kimi-code\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "manual",
            "url": "https://code.kimi.com",
        },
        # Kimi Code VSCode 扩展
        # 来源：https://code.kimi.com（Kimi Code 支持 VSCode 编辑器集成）
        "vscode_install": {
            "method": "manual",
            "url": "https://code.kimi.com",
            "note": "在 VS Code 扩展市场搜索 Kimi Code 安装",
        },
        # Kimi Code JetBrains 插件
        # 来源：https://code.kimi.com（Kimi Code 支持 JetBrains 编辑器集成）
        "jetbrains_install": {
            "method": "manual",
            "url": "https://plugins.jetbrains.com/search?search=kimi+code",
            "note": "在 JetBrains IDE 插件市场搜索 Kimi Code 安装",
        },
        "download_urls": {
            "macos_arm64": "https://code.kimi.com/kimi-code/install.sh",
            "macos_x64": "https://code.kimi.com/kimi-code/install.sh",
            "windows_x64": "https://code.kimi.com/kimi-code/install.ps1",
            "linux_x64": "https://code.kimi.com/kimi-code/install.sh",
        },
        "install_methods": ["script"],
        "categories": ["vscode", "jetbrains"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        # Kimi Code ACP：通过 ACP 协议接入 JetBrains IDE
        # 来源：https://www.jetbrains.com/acp/（ACP Registry）
        # Kimi CLI 实现了 ACP，运行 kimi acp 后在 JetBrains AI Assistant 中连接
        "acp_install": {
            "method": "manual",
            "url": "https://www.jetbrains.com/acp/",
            "cmd": "kimi acp",
            "note": "在 JetBrains IDE AI Assistant 中配置 ACP 智能体，运行 kimi acp 后连接",
        },
        "brand": "Kimi", "category": "code", "forms": ['vscode', 'jetbrains', 'acp'],
    },
    "KimiWork": {
        # Kimi Work（桌面 AI Agent，Moonshot AI 桌面应用）
        # 产品页：https://kimi.com/products/kimi-work
        # 定位：面向知识工作者的桌面 Agent（Local Agent）
        # 平台：macOS Apple silicon、Windows 10+
        # 内置 Skill 系统、Cron 定时、WebBridge 浏览器自动化、Agent Swarm
        "label": "Kimi Work",
        "version": "1.0.0",
        "release_date": "2026-06-08",
        "homepage": "https://kimi.com/products/kimi-work",
        "docs_url": "https://kimi.com/products/kimi-work",
        "release_url": "https://kimi.com/products/kimi-work",
        "cli_install": {
            "method": "manual",
            "url": "https://kimi.com/products/kimi-work",
        },
        "app_install": {
            "method": "manual",
            "url": "https://kimi.com/products/kimi-work",
        },
        "download_urls": {
            "macos_arm64": "https://kimi.com/products/kimi-work",
            "macos_x64": "https://kimi.com/products/kimi-work",
            "windows_x64": "https://kimi.com/products/kimi-work",
        },
        "install_methods": ["app"],
        "categories": ["app"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Kimi", "category": "work", "forms": ['app'],
    },
    "Pi": {
        # Pi（极简 agent harness，CLI 工具）
        # 官网：https://pi.dev/
        # GitHub：https://github.com/earendil-works/pi
        # 配置目录：~/.pi/
        # 支持 15+ 提供商，扩展/技能/提示模板/主题
        "label": "Pi",
        "version": "latest",
        "release_date": "2026-07-01",
        "homepage": "https://pi.dev/",
        "docs_url": "https://pi.dev/docs/latest",
        "release_url": "https://github.com/earendil-works/pi/releases",
        "cli_install": {
            # 官方安装方式：npm install -g --ignore-scripts @earendil-works/pi-coding-agent
            # 来源：https://pi.dev/docs/latest
            # --ignore-scripts 禁用依赖生命周期脚本（Pi 不需要 install scripts）
            "method": "npm",
            "package": "@earendil-works/pi-coding-agent",
            "npm_flags": "--ignore-scripts",
            "url": "https://pi.dev/",
            "script_url": "https://pi.dev/install.sh",
            "script_url_win": "https://pi.dev/install.ps1",
            "uninstall_cmd_mac": "npm uninstall -g @earendil-works/pi-coding-agent; rm -rf ~/.pi; true",
            "uninstall_cmd_win": "npm uninstall -g @earendil-works/pi-coding-agent & rmdir /s /q \"%USERPROFILE%\\.pi\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "manual",
            "url": "https://pi.dev/",
        },
        "download_urls": {
            "macos_arm64": "https://pi.dev/",
            "macos_x64": "https://pi.dev/",
            "windows_x64": "https://pi.dev/",
            "linux_x64": "https://pi.dev/",
        },
        "install_methods": ["npm"],
        "categories": ["cli"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Pi", "category": "code", "forms": ['cli'],
    },
    "CommandCode": {
        # Command Code（面向命令行场景的 AI 编程智能体）
        # 官网：https://commandcode.ai/
        # npm 包：command-code
        # CLI 命令：cmd / command-code / cmnd
        # 配置目录：~/.commandcode/
        # 核心能力：Taste 编码风格持续学习系统
        "label": "Command Code",
        "version": "0.0.3",
        "release_date": "2026-07-01",
        "homepage": "https://commandcode.ai/",
        "docs_url": "https://commandcode.ai/",
        "release_url": "https://www.npmjs.com/package/command-code",
        "cli_install": {
            "method": "npm",
            "package": "command-code",
            "url": "https://commandcode.ai/",
            "uninstall_cmd_mac": "npm uninstall -g command-code; rm -rf ~/.commandcode; true",
            "uninstall_cmd_win": "npm uninstall -g command-code & rmdir /s /q \"%USERPROFILE%\\.commandcode\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "manual",
            "url": "https://commandcode.ai/",
        },
        "download_urls": {
            "macos_arm64": "https://commandcode.ai/",
            "macos_x64": "https://commandcode.ai/",
            "windows_x64": "https://commandcode.ai/",
            "linux_x64": "https://commandcode.ai/",
        },
        "install_methods": ["npm"],
        "categories": ["cli"],
        # 新分类字段（品牌 brand + 顶层 category + 形式 forms）
        "brand": "Command Code", "category": "code", "forms": ['cli'],
    },
    "VSCode": {
        # Visual Studio Code（Microsoft 代码编辑器）
        # 来源：https://code.visualstudio.com/
        "label": "VSCode",
        "version": "1.103",
        "release_date": "2026-07-01",
        "homepage": "https://code.visualstudio.com",
        "docs_url": "https://code.visualstudio.com/docs",
        "release_url": "https://code.visualstudio.com/updates",
        "cli_install": {
            # VSCode CLI 随 App 一起安装（code 命令）
            "method": "manual",
            "url": "https://code.visualstudio.com/download",
            "note": "安装 VSCode 后，在命令面板执行 'Shell Command: Install code in PATH' 启用 code CLI",
            "uninstall_cmd_mac": "rm -f /usr/local/bin/code; true",
            "uninstall_cmd_win": "del /q \"%USERPROFILE%\\AppData\\Local\\Programs\\Microsoft VS Code\\bin\\code.cmd\" 2>nul & exit /b 0",
        },
        "app_install": {
            "method": "system_uninstall",
            "url": "https://code.visualstudio.com/download",
            "uninstall_cmd_mac": "rm -rf '/Applications/Visual Studio Code.app' ~/.vscode 2>/dev/null; true",
            "uninstall_cmd_win": "rmdir /s /q \"%LOCALAPPDATA%\\Programs\\Microsoft VS Code\" 2>nul & rmdir /s /q \"%USERPROFILE%\\.vscode\" 2>nul & exit /b 0",
        },
        "download_urls": {
            "macos_arm64": "https://code.visualstudio.com/download",
            "macos_x64": "https://code.visualstudio.com/download",
            "windows_x64": "https://code.visualstudio.com/download",
            "linux_x64": "https://code.visualstudio.com/download",
        },
        "install_methods": ["app"],
        "categories": ["app", "cli"],
        "brand": "Microsoft", "category": "code", "forms": ['app', 'cli'],
    },
}


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
    3. 各 method 的额外必填字段（如 brew/npm 必须有 package）
    4. install_methods 列表必须存在（可空）
    """
    warnings: list[str] = []
    for ide_key, meta in IDE_INSTALL_META.items():
        # 1. 顶层字段
        for field in _REQUIRED_TOP_FIELDS:
            if field not in meta:
                warnings.append(f"[{ide_key}] 缺少顶层字段: {field}")
        # 2. install 块的 method
        for install_type in ("cli_install", "app_install"):
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
        # 4. install_methods 列表
        if "install_methods" not in meta:
            warnings.append(f"[{ide_key}] 缺少 install_methods 列表（即使为空也需声明）")
        elif not isinstance(meta["install_methods"], list):
            warnings.append(f"[{ide_key}] install_methods 必须是 list")
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
        if not shutil.which("npm"):
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
            npm_flags = install_meta.get("npm_flags", "")
            if npm_flags:
                cmd = ["npm", "install", "-g", package] + npm_flags.split()
            else:
                cmd = ["npm", "install", "-g", package]
            r = _run_cmd(cmd, timeout=600)
            if r["ok"]:
                return {
                    "ok": True, "ide": ide_key, "mode": mode, "method": "npm",
                    "message": "安装成功",
                    "cmd": r["cmd"], "stdout": r["stdout"][-2000:], "stderr": r["stderr"][-2000:],
                }
            # npm 安装失败，尝试 --ignore-scripts（解决 sharp 等原生模块编译失败）
            r2 = None
            if "--ignore-scripts" not in npm_flags:
                r2 = _run_cmd(["npm", "install", "-g", package, "--ignore-scripts"], timeout=600)
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
        mode: "cli" 或 "app"
        force: 强制卸载——跳过系统卸载程序，直接按 uninstall_cmd 强删目录。
               用于 GUI 卸载器卡死/超时/需交互弹窗的场景（如 Trae/Cursor app）。

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
            if not shutil.which("npm"):
                return {"ok": False, "ide": ide_key, "mode": mode, "method": "npm",
                        "message": "未安装 npm", "cmd": "", "stdout": "", "stderr": ""}
            cmd = ["npm", "uninstall", "-g", package]
            r = _run_cmd(cmd, timeout=300)
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
    jetbrains_install = dict(meta.get("jetbrains_install", {}))
    acp_install = dict(meta.get("acp_install", {}))
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
        # 卡片内按 Code/Work 顶层分组，再按 cli/app/vscode/jetbrains 子形式分行）
        "brand": meta.get("brand") or "",
        "category": meta.get("category") or "",
        "forms": meta.get("forms") or [],
        # 兼容字段：旧 categories（app/cli/vscode/jetbrains 平铺列表）
        # 从新 forms 字段派生，保证旧前端代码不破坏
        "categories": meta.get("categories") or meta.get("forms") or _infer_categories(meta),
        "cli": cli_install,
        "app": app_install,
        "vscode": vscode_install,
        "jetbrains": jetbrains_install,
        "acp": acp_install,
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
