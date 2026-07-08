# AgentBuddy 构建指南

## GitHub Actions 自动构建发布

推送 tag 即可触发 GitHub Actions 自动构建 macOS + Windows 并发布 Release：

```bash
# 1. 打 tag
git tag v1.0.0

# 2. 推送 tag（触发自动构建）
git push origin v1.0.0

# 3. 等待 Actions 完成，自动在 Releases 页面生成:
#    - AgentBuddy-1.0.0-macos.dmg / .zip
#    - AgentBuddy-1.0.0-x64.exe
```

也可在 GitHub 仓库 Actions 页面手动触发（workflow_dispatch）。

> 首次使用前需在 GitHub 仓库 Settings -> Actions -> General 中允许读写权限。

## 本地快速构建

```bash
# macOS / Linux
./build.sh --windowed --clean

# Windows
build.cmd --windowed --clean
```

## 构建流程

`build.sh` / `build.cmd` 自动完成 5 步：

1. **前端构建**：`cd frontend && npm run build-only` -> 产出 `tools/dist-ui/`
2. **Python 依赖检查**：自动安装缺失的 flask/pyyaml/requests/pywebview/pyinstaller
3. **PyInstaller 打包**：`python build.py` -> 产出 `dist/AgentBuddy/`
4. **验证**：确认前端产物（dist-ui/index.html）已进 bundle
5. **安装包生成**（仅 Windows）：调用 Inno Setup 生成 `.exe` 安装包

## 参数

| 参数 | 说明 |
|---|---|
| `--windowed` | 无控制台（macOS 生成 .app / Windows 无黑框） |
| `--clean` | 构建前清理 dist/ build/ |
| `--no-frontend` | 跳过前端构建（使用已有 tools/dist-ui） |
| `--no-verify` | 跳过密钥泄漏扫描（不推荐） |
| `--no-installer` | 跳过 Inno Setup 安装包生成（仅 Windows） |
| `--version 1.2.0` | 安装包版本号（默认 1.0.0） |

## Windows 安装包

### 前置条件

安装 [Inno Setup 6](https://jrsoftware.org/isdl.php)（免费开源的 Windows 安装包制作工具）。

`build.py` 会自动检测以下位置的 `ISCC.exe`：
- 系统 PATH
- `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
- `C:\Program Files\Inno Setup 6\ISCC.exe`
- `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`

### 生成安装包

```batch
:: 默认构建（含安装包）
build.cmd --windowed --clean

:: 指定版本号
build.cmd --windowed --clean --version 1.2.0

:: 跳过安装包（仅生成 exe 目录）
build.cmd --windowed --clean --no-installer
```

### 产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 可执行目录 | `dist\AgentBuddy\` | PyInstaller onedir 产物 |
| 可执行文件 | `dist\AgentBuddy\AgentBuddy.exe` | 主程序 |
| 安装包 | `dist\installer\AgentBuddy-Setup-<version>-x64.exe` | Inno Setup 安装包 |

安装包特性：
- 64 位 Windows 安装包（LZMA2/ultra64 压缩）
- 支持按用户安装（无需管理员）或全局安装（弹出 UAC）
- 开始菜单快捷方式 + 可选桌面图标
- 卸载时清理日志文件，保留用户配置
- 应用图标：`assets/app.ico`

## macOS 分发包

### 前置条件

- **.zip**（默认）：无需额外工具，系统自带 `zip` 命令
- **.dmg**（可选）：安装 `create-dmg`：`brew install create-dmg`

### 生成分发包

```bash
# 默认构建（自动生成 .zip 或 .dmg）
./build.sh --windowed --clean --version 1.2.0

# 跳过分发包生成
./build.sh --windowed --clean --no-installer
```

`build.py` 会自动选择：
1. 检测到 `create-dmg` -> 生成 `.dmg`（带拖拽安装界面）
2. 未检测到 -> 回退生成 `.zip`

### 产物

| 产物 | 路径 | 说明 |
|---|---|---|
| 可执行目录 | `dist/AgentBuddy/` | PyInstaller onedir 产物 |
| 可执行文件 | `dist/AgentBuddy/AgentBuddy` | 主程序 |
| DMG 分发包 | `dist/installer/AgentBuddy-<version>-macos.dmg` | 需 create-dmg |
| ZIP 分发包 | `dist/installer/AgentBuddy-<version>-macos.zip` | 默认回退 |

## 开发模式

```bash
# 前端热更新（5173）+ 后端 Flask（5050）
cd frontend && npm run dev        # 终端 1
./run.sh --no-webview             # 终端 2，浏览器开 http://127.0.0.1:5173
```

## 生产模式

```bash
cd frontend && npm run build-only  # 构建前端
./run.sh                           # pywebview 加载 tools/dist-ui
```

## 文件结构

```
frontend/               # Vue 3 + Vite 工程（开发/构建用，不打包）
  src/                  #   SFC 组件 + stores + api
  dist-ui -> ../tools/  #   构建产物输出到 tools/dist-ui/

tools/
  config_ui.html        # 旧版 UI（/old 路由备用）
  dist-ui/              # Vue 3 构建产物（Flask 根路由 serve）
  config_server.py      # Flask 后端
  static/               # 旧版 Vue/Tailwind 运行时（兼容期保留）

scripts/
  agentctl.py           # CLI 入口（sync/generate/env）
  lib/                  #   llm/mcp/skills/plugins/ide 模块

app.py                  # pywebview 桌面启动器
app.spec                # PyInstaller 打包配置
build.sh / build.cmd    # 一键构建脚本
run.sh / run.cmd        # 一键启动脚本
```
