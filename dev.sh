#!/usr/bin/env bash
# AgentBuddy 开发环境一键启动 (macOS/Linux)
# 同时启动：Flask 后端 (5050) + Vite 前端 (19527)
# 前端 /api /static 自动 proxy 到后端，改代码即时热更新
#
# 用法:
#   ./dev.sh              # 启动前端 + 后端
#   ./dev.sh --server     # 额外启动远程服务端 (5001)
#   ./dev.sh --cli        # 仅启动后端（调试 CLI 用，不开前端）
#
# 退出: Ctrl+C 终止所有子进程

set -e
cd "$(dirname "$0")"

# ---- 颜色 ----
R='\033[0;31m'  G='\033[0;32m'  Y='\033[0;33m'  C='\033[0;36m'  N='\033[0m'

# ---- Python 环境 ----
VENV_PY=".venv/bin/python"
if [ -x "$VENV_PY" ] && "$VENV_PY" -V >/dev/null 2>&1; then
    PY="$VENV_PY"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
else
    echo -e "${R}[ERROR] 未找到 Python${N}"
    exit 1
fi

# 确保核心依赖
if ! "$PY" -c "import flask, yaml, requests" >/dev/null 2>&1; then
    echo -e "${Y}[INFO] 安装核心依赖...${N}"
    "$PY" -m pip install flask pyyaml requests
fi
if ! "$PY" -c "import agentctl" >/dev/null 2>&1; then
    echo -e "${Y}[INFO] 安装 agentctl (editable)...${N}"
    "$PY" -m pip install -e cli/
fi

# ---- 前端依赖检查 ----
FRONTEND_DIR="desktop/frontend"
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${Y}[INFO] 安装前端依赖...${N}"
    (cd "$FRONTEND_DIR" && npm install)
fi

# ---- 参数解析 ----
START_SERVER=false
START_FRONTEND=true
for arg in "$@"; do
    case "$arg" in
        --server) START_SERVER=true ;;
        --cli)    START_FRONTEND=false ;;
    esac
done

# ---- 子进程管理 ----
PIDS=()
cleanup() {
    echo -e "\n${Y}[DEV] 正在停止所有服务...${N}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null && echo -e "${C}[DEV] 已停止 PID $pid${N}"
    done
    wait 2>/dev/null
    echo -e "${G}[DEV] 全部已停止${N}"
}
trap cleanup EXIT INT TERM

# ---- 启动 Flask 后端 (5050) ----
echo -e "${G}[DEV] 启动 Flask 后端 → http://127.0.0.1:5050${N}"
FLASK_DEBUG=1 PYTHONPATH="desktop:cli" "$PY" desktop/config_server.py --no-open &
PIDS+=($!)

# ---- 启动 Vite 前端 (19527) ----
if [ "$START_FRONTEND" = true ]; then
    sleep 1
    echo -e "${G}[DEV] 启动 Vite 前端  → http://127.0.0.1:19527${N}"
    (cd "$FRONTEND_DIR" && npx vite) &
    PIDS+=($!)
    echo -e "${C}[DEV] 前端 /api /static → proxy 到 5050${N}"
fi

# ---- 启动远程服务端 (5001) ----
if [ "$START_SERVER" = true ]; then
    sleep 1
    echo -e "${G}[DEV] 启动远程服务端 → http://0.0.0.0:5001${N}"
    PYTHONPATH="server:cli" "$PY" server/app.py &
    PIDS+=($!)
fi

echo -e "\n${G}[DEV] 全部已启动，Ctrl+C 退出${N}\n"
wait
