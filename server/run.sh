#!/usr/bin/env bash
# AgentBuddy Server 一键构建和运行脚本
# 用法：
#   ./run.sh          # 前台运行
#   ./run.sh -d       # 后台运行（nohup）
#   ./run.sh stop     # 停止后台进程
#   ./run.sh restart  # 重启
#   ./run.sh status   # 查看状态
#   ./run.sh update   # 更新代码并重启
#   ./run.sh log      # 查看日志

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE=".server.pid"
LOG_FILE="server.log"
HOST="${AGENTBUDDY_SERVER_HOST:-0.0.0.0}"
PORT="${AGENTBUDDY_SERVER_PORT:-5001}"

# Gitee 镜像地址（国内服务器优先使用）
GITEE_URL="https://gitee.com/superproxy/AgentBuddy.git"

# === 颜色 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# === 检查 Python ===
check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        error "未找到 Python，请先安装 Python 3.8+"
        exit 1
    fi
    local version=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    info "Python: $PYTHON ($version)"
}

# === 安装依赖 ===
setup_deps() {
    PIP="$PYTHON -m pip"
    PIP_MIRROR="-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com"

    # 确保 pip 可用
    if ! $PIP --version 2>/dev/null; then
        info "安装 pip..."
        apt-get update -qq 2>/dev/null
        apt-get install -y -qq python3-pip 2>/dev/null || true
    fi

    # 检查依赖是否已安装
    if ! $PYTHON -c "import flask" 2>/dev/null; then
        info "安装依赖（使用阿里云镜像）..."
        if ! $PIP install --upgrade pip $PIP_MIRROR 2>&1; then
            warn "pip 升级失败，继续安装依赖..."
        fi
        if ! $PIP install -r requirements.txt $PIP_MIRROR 2>&1; then
            error "依赖安装失败！请手动执行："
            error "  $PIP install -r requirements.txt $PIP_MIRROR"
            exit 1
        fi
        info "依赖安装完成"
    else
        info "依赖已就绪"
    fi
}

# === 启动 ===
start() {
    check_python
    setup_deps

    info "启动 AgentBuddy Server ..."
    info "  监听: $HOST:$PORT"
    info "  数据目录: ${AGENTBUDDY_DATA_DIR:-$SCRIPT_DIR/data}"
    info "  LLM 配置: ${AGENTBUDDY_LLM_CONFIG:-$SCRIPT_DIR/config/llm/llm.yaml}"

    exec $PYTHON app.py
}

# === 后台启动 ===
start_daemon() {
    check_python
    setup_deps

    # 检查是否已在运行
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            warn "Server 已在运行 (PID: $pid)"
            exit 0
        fi
        rm -f "$PID_FILE"
    fi

    info "后台启动 AgentBuddy Server ..."
    info "  监听: $HOST:$PORT"
    info "  日志: $LOG_FILE"

    nohup $PYTHON app.py > "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    sleep 3
    if kill -0 "$pid" 2>/dev/null; then
        info "Server 已启动 (PID: $pid)"
        info "  查看日志: tail -f $LOG_FILE"
        info "  健康检查: curl http://$HOST:$PORT/api/health"
    else
        error "Server 启动失败！日志内容："
        cat "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# === 停止 ===
stop() {
    if [ ! -f "$PID_FILE" ]; then
        warn "Server 未在运行"
        return 0
    fi
    local pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        sleep 1
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid"
        fi
        info "Server 已停止 (PID: $pid)"
    else
        warn "进程 $pid 不存在，清理 PID 文件"
    fi
    rm -f "$PID_FILE"
}

# === 状态 ===
status() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            info "Server 运行中 (PID: $pid)"
            info "  日志: tail -f $LOG_FILE"
            exit 0
        fi
    fi
    warn "Server 未运行"
    exit 1
}

# === 更新代码 ===
update() {
    # 检测当前 remote 是否是 Gitee
    local remote_url=$(git remote get-url origin 2>/dev/null)

    if echo "$remote_url" | grep -q "gitee.com"; then
        info "从 Gitee 拉取代码..."
        git pull || { error "git pull 失败"; exit 1; }
    else
        # 尝试切换到 Gitee
        info "尝试从 Gitee 拉取代码..."
        git pull origin main 2>/dev/null
        if [ $? -ne 0 ]; then
            warn "当前 remote 非 Gitee，尝试添加 Gitee remote..."
            git remote add gitee "$GITEE_URL" 2>/dev/null || true
            info "从 Gitee 拉取..."
            if ! git pull gitee main 2>/dev/null; then
                warn "Gitee 拉取失败，尝试直连 GitHub..."
                if ! git pull origin main 2>/dev/null; then
                    error "所有拉取方式均失败，请手动检查网络"
                    exit 1
                fi
            fi
        fi
    fi

    info "代码更新完成，正在重启服务..."
    stop
    sleep 1
    start_daemon
}

# === 查看日志 ===
show_log() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        warn "日志文件不存在: $LOG_FILE"
    fi
}

# === 主逻辑 ===
case "${1:-}" in
    -d|--daemon)
        start_daemon
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start_daemon
        ;;
    status)
        status
        ;;
    update)
        update
        ;;
    log)
        show_log
        ;;
    *)
        start
        ;;
esac
