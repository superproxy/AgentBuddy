#!/usr/bin/env bash
# AdeBuddy 一键初始化安装入口 (macOS / Linux)
# 等价于 agentctl setup: generate + sync 到所有 IDE
#
# 用法:
#   ./install.sh              # 默认全量初始化（generate + sync All）
#   ./install.sh --ide ZCode  # 仅同步指定 IDE
#   ./install.sh --help       # 查看更多选项

set -e
cd "$(dirname "$0")"

echo "========================================"
echo "  AdeBuddy 一键初始化"
echo "========================================"
echo

# === Step 0: 检查 Python ===
if ! command -v python3 &>/dev/null; then
    if command -v python &>/dev/null; then
        PY=python
    else
        echo "[ERROR] 未找到 Python，请先安装 Python 3.8+"
        echo "        macOS:  brew install python"
        echo "        Ubuntu: sudo apt install python3 python3-pip"
        exit 1
    fi
else
    PY=python3
fi

echo "[INFO] Python: $($PY --version 2>&1)"

# === Step 1: 检查并安装核心依赖 ===
if ! $PY -c "import flask, yaml, requests" 2>/dev/null; then
    echo "[INFO] 缺少核心依赖，正在安装..."
    $PY -m pip install flask pyyaml requests
fi

# === Step 2: 首次运行时从模板生成配置文件 ===
echo
echo "[Step 1/3] 初始化配置文件"
if [ ! -f "config/llm/llm.yaml" ]; then
    if [ -f "template/llm/llm-env-example.yaml" ]; then
        mkdir -p config/llm
        cp "template/llm/llm-env-example.yaml" "config/llm/llm.yaml"
        echo "  [NEW] 已生成 config/llm/llm.yaml（请填入 API Key）"
    fi
else
    echo "  [OK]  config/llm/llm.yaml 已存在"
fi
if [ ! -f "config/mcp/mcp.yaml" ]; then
    if [ -f "template/mcp/mcp-env-example.yaml" ]; then
        mkdir -p config/mcp
        cp "template/mcp/mcp-env-example.yaml" "config/mcp/mcp.yaml"
        echo "  [NEW] 已生成 config/mcp/mcp.yaml"
    fi
else
    echo "  [OK]  config/mcp/mcp.yaml 已存在"
fi

# === Step 3: generate + sync ===
echo
echo "[Step 2/3] 生成运行态配置 (mcp.json + IDE 模板)"
$PY scripts/agentctl.py generate

echo
echo "[Step 3/3] 同步配置到所有 IDE"
$PY scripts/agentctl.py sync --ide All --force "$@"

echo
echo "========================================"
echo "  安装完成！"
echo "========================================"
echo
echo "已同步的 IDE 配置:"
echo "  - Claude:    ~/.claude/mcp.json"
echo "  - ZCode:     ~/.zcode/cli/config.json"
echo "  - Trae CN:   ~/Library/Application Support/Trae CN/User/mcp.json"
echo "  - Codex:     ~/.codex/config.toml"
echo "  - OpenCode:  ~/.config/opencode/opencode.json"
echo
echo "如需修改配置，编辑 config/llm/llm.yaml 和 config/mcp/mcp.yaml 后重新运行 ./install.sh"
echo "如需启动 GUI 桌面工具，运行 ./run.sh"
