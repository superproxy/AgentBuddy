# 配置工具 Web UI（API 层）

桌面应用的 API 层，Flask 后端，通过浏览器或 pywebview 窗口管理 `llm.yaml` / `mcp.yaml`、插件、MCP、Skill。

> 三层分离后位于 `desktop/service/`，通过 `pip install -e cli/` 引入 `agentctl` 包共享业务库。

## 启动

```bash
# 安装依赖（一次性）
pip install flask pyyaml requests
pip install -e cli/    # 三层分离：共享业务库

# 启动
python desktop/service/config_server.py

# 自定义端口/不自动开浏览器
python desktop/service/config_server.py --port 8080 --no-open
```

启动后自动打开 `http://127.0.0.1:5050`。

## 功能页签

| 页签 | 功能 |
|---|---|
| **LLM 配置** | 可视化编辑 `llm.yaml`（LLM providers / proxy / embedding / tts / asr / vision / misc） |
| **MCP** | 单页三区：市场搜索 / 已配置（含手动添加） / 密钥配置（`mcp.yaml`） |
| **Skills 配置** | ModelScope 市场 + skills.sh + 本地预置 + 手动 `owner/repo`，一键 `npx skills add` |
| **插件组装** | 预定义插件卡片 + 从技能目录/MCP 目录勾选组装 `plugin.yaml` 并安装 |
| **IDE 同步** | 触发 `agentctl sync` 同步配置到各 IDE |

## 设计要点

- **复用 agentctl 包**：后端 `from agentctl.lib.X import Y` 直接复用 `cli/lib/` 业务逻辑，不重写
- **流式安装日志**：所有 `npx` / `subprocess` 调用通过 SSE 推送实时日志，避免界面卡死
- **强制 `--copy`**：复用 skills 安装策略，避免 Trae 沙箱下 symlink 失败
- **外部 API 代理**：ModelScope / skills.sh 由后端代理调用，前端不跨域

## 外部市场源

- MCP：`https://www.modelscope.cn/openapi/v1/mcp/servers`（列表 + 详情，返回 `server_config`）
- Skill：`https://www.modelscope.cn/openapi/v1/skills`（搜索 + `install_command`）
- Skill 备源：`https://skills.sh/api/search`

## 文件清单

```
desktop/
  ├── launcher.py             # pywebview 桌面启动器（Frozen-aware）
  └── service/
      ├── config_server.py    # Flask 后端（API 层）
      ├── dist-ui/            # Vue 前端构建产物（由 desktop/frontend 构建生成）
      └── README.md           # 本文件
desktop/frontend/             # Vue 3 + Vite + Pinia + TailwindCSS（前端层）
cli/                          # agentctl 包（CLI 层，pip install -e cli/）
```

## 依赖

- Python 3.8+
- flask, pyyaml, requests
- agentctl（`pip install -e cli/`）
- Node.js（`npx skills add` 需要，前端构建需要）
