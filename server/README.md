# AgentBuddy 平台服务

## 目录结构

```
server/
├── marketplace/          # 插件市场服务（Flask Blueprint）
│   ├── __init__.py
│   ├── routes.py         # 市场 API 路由
│   └── storage.py        # 索引 + 包存储
├── ai_generator/         # AI 插件生成服务
│   ├── __init__.py
│   ├── generator.py      # 生成逻辑（openai SDK）
│   └── skills/           # 生成 skill 定义
│       ├── plugin_design.md
│       └── plugin_generate.md
├── requirements.txt      # Python 依赖
└── README.md
```

## 架构说明

### 插件市场（marketplace/）
- 作为 Flask Blueprint 挂载到主应用 `config_server.py`
- 路由前缀：`/api/marketplace/*`
- 数据存储：`config/marketplace/index.json` + `packages/*.zip`
- 通过依赖注入复用 `config_server.py` 的辅助函数

### AI 插件生成（ai_generator/）
- 被 `config_server.py` 直接 import 调用
- API 端点：`GET /api/ai/generate?prompt=<需求>` (SSE) + `POST /api/ai/save`
- 从 `config/llm/llm.yaml` 读取 provider + API Key
- 使用 openai SDK（兼容 OpenAI / Anthropic / 火山引擎 / DeepSeek 等）
- 流式输出 LLM 生成的 plugin.yaml

## 安装依赖

```bash
pip install -r server/requirements.txt
```
