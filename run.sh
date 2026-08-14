#!/usr/bin/env bash
# AgentBuddy 配置工具桌面启动器 (Linux/macOS, pywebview 优先)
# 用法: ./run.sh [port] [--no-webview]

set -e
PORT="${1:-5050}"

# 切到项目根目录（脚本所在目录）
cd "$(dirname "$0")"

VENV_DIR=".venv"
VENV_PY="$VENV_DIR/bin/python"

# 校验虚拟环境 Python 是否真实可用（软链可能指向已卸载的解释器导致断链）
venv_python_works() {
    [ -x "$VENV_PY" ] && "$VENV_PY" -V >/dev/null 2>&1
}

# 优先使用项目虚拟环境 .venv（避免 Homebrew Python 的 externally-managed 限制）
if venv_python_works; then
    PY="$VENV_PY"
elif command -v python3 >/dev/null 2>&1; then
    if [ -d "$VENV_DIR" ] && [ ! -x "$VENV_PY" ]; then
        echo "[INFO] 检测到 .venv 损坏（python 断链），正在重建虚拟环境..."
        rm -rf "$VENV_DIR"
    else
        echo "[INFO] 未找到 .venv，正在创建虚拟环境..."
    fi
    python3 -m venv "$VENV_DIR"
    PY="$VENV_PY"
    if ! venv_python_works; then
        echo "[ERROR] 虚拟环境创建后仍不可用，请检查 Python 3.13+ 安装"
        exit 1
    fi
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[ERROR] 未找到 Python，请先安装 Python 3.8+"
    exit 1
fi

# 检查核心依赖（缺失则安装到当前 Python 环境）
if ! "$PY" -c "import flask, yaml, requests" >/dev/null 2>&1; then
    echo "[INFO] 缺少依赖，正在安装 flask pyyaml requests ..."
    "$PY" -m pip install flask pyyaml requests || {
        echo "[ERROR] 依赖安装失败，请手动执行: $PY -m pip install flask pyyaml requests"
        exit 1
    }
fi

# 三层分离：agentctl 包以 editable install 方式注册（共享业务库 cli/lib/）
if ! "$PY" -c "import agentctl" >/dev/null 2>&1; then
    echo "[INFO] 安装 agentctl 包（cli/ 共享业务库）..."
    "$PY" -m pip install -e cli/ || {
        echo "[ERROR] agentctl 安装失败，请手动执行: $PY -m pip install -e cli/"
        exit 1
    }
fi

# 尝试安装 pywebview（缺失则安装，可选依赖）
if ! "$PY" -c "import webview" >/dev/null 2>&1; then
    echo "[INFO] 未安装 pywebview，正在安装（可选，用于桌面窗口）..."
    "$PY" -m pip install pywebview || echo "[WARN] pywebview 安装失败，将回退到系统浏览器"
fi

echo "[INFO] 启动配置工具 (pywebview 优先): http://127.0.0.1:${PORT}"
exec $PY desktop/launcher.py --port "$PORT" ${2:-} ${3:-} ${4:-}
