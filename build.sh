#!/usr/bin/env bash
# AgentBuddy 完整构建脚本（前端 + 后端 + PyInstaller 打包）
# 用法: ./build.sh [--windowed] [--clean] [--no-frontend] [--no-verify] [--version 1.0.0]
set -e

cd "$(dirname "$0")"
ROOT="$(pwd)"

# ===== 颜色 =====
G="\033[32m"  # green
Y="\033[33m"  # yellow
R="\033[31m"  # red
N="\033[0m"   # reset
info()  { echo -e "${G}[build]${N} $1"; }
warn()  { echo -e "${Y}[build]${N} $1"; }
fail()  { echo -e "${R}[build][ERROR]${N} $1"; exit 1; }

# ===== 参数解析 =====
WINDOWED=false
CLEAN=false
NO_FRONTEND=false
NO_VERIFY=false
NO_INSTALLER=false
BUILD_CLI=false
VERSION="1.0.0"
for arg in "$@"; do
  case "$arg" in
    --windowed)     WINDOWED=true ;;
    --clean)        CLEAN=true ;;
    --no-frontend)  NO_FRONTEND=true ;;
    --no-verify)    NO_VERIFY=true ;;
    --no-installer) NO_INSTALLER=true ;;
    --cli)          BUILD_CLI=true ;;
    --cli-sdk)      BUILD_CLI_SDK=true ;;
    --version=*)    VERSION="${arg#--version=}" ;;
    --version)      shift_next=true ;;
    *) if [ "$shift_next" = true ]; then VERSION="$arg"; shift_next=false; fi ;;
  esac
done

info "AgentBuddy 完整构建 (platform=$(uname -s))"

# ===== 1. 前端构建（Vue 3 + Vite -> desktop/dist-ui）=====
if [ "$NO_FRONTEND" = false ]; then
  info "步骤 1/4: 构建前端 (Vue 3 + Vite)..."
  if [ ! -d "desktop/frontend/node_modules" ]; then
    warn "desktop/frontend/node_modules 不存在，正在安装依赖..."
    cd desktop/frontend && npm install && cd "$ROOT"
  fi
  cd desktop/frontend
  npm run build-only || fail "前端构建失败"
  cd "$ROOT"
  info "前端产物: desktop/dist-ui/ ($(du -sh desktop/dist-ui 2>/dev/null | cut -f1))"
else
  warn "跳过前端构建 (--no-frontend)"
fi

# ===== 2. 检查 Python 依赖 =====
info "步骤 2/4: 检查 Python 依赖..."
VENV_PY=".venv/bin/python"
if [ -x "$VENV_PY" ]; then
  PY="$VENV_PY"
else
  PY="python3"
fi
if ! "$PY" -c "import flask, yaml, requests" 2>/dev/null; then
  warn "缺少运行时依赖，正在安装..."
  "$PY" -m pip install flask pyyaml requests pywebview || fail "依赖安装失败"
fi
# 三层分离：agentctl 包以 editable install 方式注册
if ! "$PY" -c "import agentctl" 2>/dev/null; then
  warn "安装 agentctl 包（cli/ 共享业务库）..."
  "$PY" -m pip install -e cli/ || fail "agentctl 安装失败"
fi
if ! "$PY" -c "import PyInstaller" 2>/dev/null; then
  warn "缺少 PyInstaller，正在安装..."
  "$PY" -m pip install pyinstaller || fail "PyInstaller 安装失败"
fi
info "Python 依赖就绪"

# ===== 3. PyInstaller 打包 =====
info "步骤 3/4: PyInstaller 打包..."
BUILD_ARGS=""
if [ "$WINDOWED" = true ]; then BUILD_ARGS="$BUILD_ARGS --windowed"; fi
if [ "$CLEAN" = true ]; then BUILD_ARGS="$BUILD_ARGS --clean"; fi
if [ "$NO_VERIFY" = true ]; then BUILD_ARGS="$BUILD_ARGS --no-verify"; fi
if [ "$NO_INSTALLER" = true ]; then BUILD_ARGS="$BUILD_ARGS --no-installer"; fi
if [ "$BUILD_CLI" = true ]; then BUILD_ARGS="$BUILD_ARGS --cli"; fi
if [ "$BUILD_CLI_SDK" = true ]; then BUILD_ARGS="$BUILD_ARGS --cli-sdk"; fi
BUILD_ARGS="$BUILD_ARGS --version $VERSION"
"$PY" build.py $BUILD_ARGS || fail "PyInstaller 打包失败"
info "后端打包完成: dist/AgentBuddy/"
if [ "$BUILD_CLI" = true ]; then
  info "CLI 打包完成: dist/agentctl/"
fi

# ===== 4. 验证前端产物已进 bundle =====
info "步骤 4/4: 验证前端产物..."
BUNDLE_DESKTOP="dist/AgentBuddy/_internal/desktop"
if [ ! -d "$BUNDLE_DESKTOP/dist-ui" ]; then
  BUNDLE_DESKTOP="dist/AgentBuddy/desktop"
fi
if [ -f "$BUNDLE_DESKTOP/dist-ui/index.html" ]; then
  info "前端产物已进 bundle: $BUNDLE_DESKTOP/dist-ui/index.html"
else
  warn "前端产物未在 bundle 中找到（desktop/dist-ui），打包后 UI 可能无法显示"
fi

echo ""
info "========================================"
info "  构建完成！"
info "========================================"
info "  产物目录: dist/AgentBuddy/"
info "  启动:     dist/AgentBuddy/AgentBuddy"
echo ""
