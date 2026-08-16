# 插件构建与发布

从来源（GitHub 仓库 / 文章 URL / 本地目录）自动分析、打包、发布插件到市场。

核心流程：**analyze_source → download_skills → generate_yaml → package → publish**

---

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│               PluginBuilder 引擎 (cli/lib/plugin_builder.py)              │
│                                                                          │
│   analyze_source()     download_skills()      generate_yaml()           │
│       ↓                     ↓                      ↓                      │
│   GitHub API          skills.install_skill     plugin.schema.yaml        │
│   URL 抓取            npx / git clone          YAML 生成                │
│   本地扫描            本地复制                                          │
│                          ↓                                              │
│                   package()                publish()                    │
│                   ┌──────┴──────┐         HTTP POST                     │
│                   │             │         → /api/marketplace/publish     │
│                inline         split                                       │
│            (一个yaml)    (yaml+mcp+keys)                                  │
└─────────────────────────────────────────────────────────┘
        ↑                ↑                    ↑
        │                │                    │
   ┌────┴────┐     ┌─────┴─────┐      ┌──────┴──────┐
   │ 场景一   │     │  场景二    │      │   场景三    │
   │ CLI     │     │  UI 界面   │      │  定时任务   │
   │ agentctl│     │  PluginBuildView │ PluginMarketWorker.py │
   └─────────┘     └───────────┘      └─────────────┘
```

### 三条发布路径

| 路径 | 调用方 | 构建 zip | 发布到市场 | Token 来源 |
|------|--------|---------|-----------|-----------|
| **A. UI 一键构建并发布** | `buildFromSource(true)` | `POST /api/plugin/build` 后端构建 | 后端 `PluginBuilder.publish()` 直接 HTTP POST | 请求头 `Authorization`（浏览器 localStorage） |
| **B. UI 已有发布** | `marketplace.publish()` | `GET /api/plugin/export` 导出 zip | 浏览器 `fetch(serverApi('/api/marketplace/publish'))` | 浏览器 localStorage `getAuthToken()` |
| **C. CLI / Crawler** | `agentctl plugin build --publish` / `PluginMarketWorker.py` | `PluginBuilder.package()` | `PluginBuilder.publish()` 直接 HTTP POST | `~/.agentbuddy/auth.json`（CLI auth 模块） |

---

## 场景一：命令行（agentctl）

### 认证

```bash
# 登录市场（token 存到 ~/.agentbuddy/auth.json）
agentctl plugin auth login --username <user> --password <pass>

# 注册新账号
agentctl plugin auth register --username <user> --password <pass> --email <email>

# 查看当前登录状态
agentctl plugin auth whoami

# 退出登录
agentctl plugin auth logout
```

### 构建插件

```bash
# 基本语法
agentctl plugin build <source> [options]

# 从 GitHub 仓库构建（owner/repo 简写）
agentctl plugin build QwenLM/Qwen-MM-Plugins \
  --skills core,api,search \
  --name qwen-mm-plugins \
  --version 1.0.0 \
  --mode inline

# 从 GitHub URL 构建
agentctl plugin build https://github.com/QwenLM/Qwen-MM-Plugins

# 从文章 URL 构建（需 AI 分析）
agentctl plugin build "https://mp.weixin.qq.com/s/xxx" --ai

# 从本地目录构建
agentctl plugin build ./my-plugin/ --name my-plugin --version 1.0.0
```

### 指定 MCP 和环境变量

`--mcp` 和 `--env` 参数让命令行直接传入 MCP server 配置和环境变量声明：

```bash
agentctl plugin build QwenLM/Qwen-MM-Plugins \
  --mcp 'qwen-core:uvx:--from:qwen-mm-plugins[core]@git+https://github.com/QwenLM/Qwen-MM-Plugins.git@v1.0.2:qwen-mm-plugins-core' \
  --mcp 'qwen-api:uvx:--from:qwen-mm-plugins[api]@git+https://github.com/QwenLM/Qwen-MM-Plugins.git@v1.0.3:qwen-mm-plugins-api' \
  --env 'DASHSCOPE_API_KEY:阿里百炼平台API Key::false' \
  --env 'SERPER_API_KEY:Serper搜索API Key::false' \
  --mode split
```

**参数格式说明：**

| 参数 | 格式 | 示例 |
|------|------|------|
| `--mcp` | `名称:command:arg1:arg2:...` | `qwen-core:uvx:--from:pkg:entry` |
| `--env` | `KEY:description:default:required` | `API_KEY:描述::false`（default 为空，required=false） |

### 一条命令构建并发布

```bash
agentctl plugin build QwenLM/Qwen-MM-Plugins \
  --skills core,api,search \
  --publish --scope public --tags multimodal,vision,ocr
```

### 发布已有 zip

```bash
agentctl plugin publish ./qwen-mm-plugins-plugin.zip \
  --scope public --tags ai,mcp
```

### 命令参数速查

| 参数 | 说明 |
|------|------|
| `<source>` | 来源：GitHub(owner/repo)、URL、本地目录路径 |
| `--name` | 插件名称（覆盖自动分析结果） |
| `--version` | 插件版本 |
| `--description` | 插件描述 |
| `--author` | 作者 |
| `--skills` | 指定要打包的 skill（逗号分隔），省略则全部 |
| `--mcp` | MCP server 配置（`名称:command:arg1:arg2`），可多次指定 |
| `--env` | 环境变量声明（`KEY:desc:default:required`），可多次指定 |
| `--mode` | 打包模式：`inline`（默认）或 `split` |
| `--ai` | 启用 AI 分析来源内容（从文章 URL 构建时推荐） |
| `--output` | 输出目录（默认 `config/plugins`） |
| `--publish` | 构建后自动发布到市场 |
| `--scope` | 发布范围：`public`（默认）或 `team` |
| `--tags` | 标签（逗号分隔，发布时生效） |
| `--team-id` | 团队 ID（scope=team 时需要） |

---

## 场景二：用户界面（一键构建）

在插件构建页面选择 **🔗 一键构建** 标签页。

### 交互流程

1. **输入来源** — 在输入框中输入 GitHub 仓库地址（`owner/repo` 或完整 URL）、文章 URL 或本地目录路径
2. **点击「分析」** — 后端调用 `PluginBuilder.analyze_source()`，返回提取的元数据（插件名、描述、skills 列表、MCP servers、环境变量）
3. **编辑与选择** — 展示分析结果，可编辑名称/版本/描述，勾选要打包的 skills，查看 MCP servers 和环境变量
4. **选择打包模式** — 内联模式（MCP+envVars 在 plugin.yaml）或拆分模式（mcp.yaml + keys.yaml 独立文件）
5. **构建** — 点击「构建 ZIP」生成 zip 到 `config/plugins/`；点击「构建并发布」生成后自动发布到市场

### 后端 API

#### `POST /api/plugin/analyze`

分析来源，返回插件元数据。

```json
// 请求
{
  "source": "QwenLM/Qwen-MM-Plugins",
  "ai": false
}

// 响应
{
  "ok": true,
  "data": {
    "name": "qwen-mm-plugins",
    "version": "1.0.0",
    "description": "给 AI Agent 装上眼睛...",
    "skills": [
      { "name": "core", "description": "本地多模态读取工具", "requires_key": false }
    ],
    "mcpServers": {
      "qwen-core": { "command": "uvx", "args": ["--from", "..."] }
    },
    "envVars": {
      "DASHSCOPE_API_KEY": { "description": "阿里百炼Key", "required": false }
    }
  }
}
```

#### `POST /api/plugin/build`

一键构建 zip，可选发布。

```json
// 请求
{
  "source": "QwenLM/Qwen-MM-Plugins",
  "ai": false,
  "name": "qwen-mm-plugins",          // 可选，覆盖分析结果
  "version": "1.0.0",
  "description": "...",
  "skills": ["core", "api"],          // 可选，过滤 skills
  "mcpServers": { ... },              // 可选，覆盖 MCP 配置
  "envVars": { ... },                 // 可选，覆盖环境变量
  "mode": "inline",                   // inline 或 split
  "publish": true,                    // 构建后是否发布
  "tags": ["vision", "ocr"],
  "scope": "public",
  "server_url": "http://123.60.75.27:5001"  // 远程市场地址
}

// 响应
{
  "ok": true,
  "data": {
    "zipPath": "config/plugins/qwen-mm-plugins-plugin.zip",
    "published": { "name": "qwen-mm-plugins", "version": "1.0.0" }
  }
}
```

**Token 机制**：前端 `api()` 自动从 localStorage 附带 `Authorization: Bearer <token>` 请求头，后端从请求头提取。CLI 场景无请求头时，从 `~/.agentbuddy/auth.json` 读取。

---

## 场景三：定时任务（Crawler）

独立 worker 脚本 `server/PluginMarketWorker.py`，用系统 crontab 调度，不依赖 Flask 进程。

### 工作流

```
读取 config/plugin-sources.yaml
    ↓
逐个处理每个源:
    1. analyze_source(url) → 提取元数据
    2. evaluate_quality(meta) → 质量评分（< 30 分跳过）
    3. already_published? → 去重检查
    4. download_skills → 下载/安装 skills
    5. generate_yaml + package(inline) → 构建 zip
    6. publish → 发布到市场
```

### 命令

```bash
cd server

# 执行所有启用的源
python PluginMarketWorker.py

# 只执行指定源（名称模糊匹配）
python PluginMarketWorker.py --source qwen-mm

# 只分析+构建，不发布
python PluginMarketWorker.py --dry-run

# 列出所有源及状态
python PluginMarketWorker.py --list

# 添加新源
python PluginMarketWorker.py --add https://github.com/owner/repo --add-name my-plugin --add-tags ai,mcp

# 移除源
python PluginMarketWorker.py --remove my-plugin
```

### crontab 配置

```bash
# 每天凌晨 3 点执行
0 3 * * * cd /path/to/AgentBuddy/server && python PluginMarketWorker.py >> /var/log/agentbuddy-crawler.log 2>&1
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENTBUDDY_SERVER_URL` | `http://127.0.0.1:5001` | 市场服务器地址 |
| `AGENTBUDDY_CRAWLER_USER` | `crawler` | 服务账号用户名 |
| `AGENTBUDDY_CRAWLER_PASS` | — | 服务账号密码（首次用 `agentctl plugin auth login` 登录后可不设） |

### 质量评分规则

满分 100 分，低于 30 分自动跳过：

| 维度 | 分值 | 规则 |
|------|------|------|
| Skill 数量 | 最多 30 | 每个 skill 10 分 |
| MCP servers | 最多 20 | 每个 server 10 分 |
| 描述完整 | 15 | description 超过 20 字符 |
| 有 homepage | 15 | — |
| 有 license | 10 | — |
| 有环境变量声明 | 10 | — |

### 源配置文件

`server/config/plugin-sources.yaml`：

```yaml
sources:
  - name: qwen-mm-plugins
    url: https://github.com/QwenLM/Qwen-MM-Plugins
    skills: [core, api, search]       # 可选，指定要打包的 skill
    tags: [multimodal, vision, ocr]
    enabled: true
    schedule: daily                   # daily / weekly / manual

  - name: awesome-mcp-servers
    url: https://github.com/punkpeye/awesome-mcp-servers
    type: directory                   # 目录型源
    enabled: false
    schedule: weekly
```

---

## 打包模式

### inline 模式（默认）

MCP servers 和 envVars 内联在 `plugin.yaml` 中，一个文件包含全部配置。

**zip 结构：**
```
qwen-mm-plugins-plugin.zip
├── qwen-mm-plugins.plugin.yaml    ← 包含 mcpServers + envVars
└── skills/
    ├── core/SKILL.md
    ├── api/SKILL.md
    └── search/SKILL.md
```

**plugin.yaml 内容示例：**
```yaml
name: qwen-mm-plugins
version: 1.0.0
description: 给 AI Agent 装上眼睛
mcpServers:
  qwen-core:
    command: uvx
    args: ["--from", "qwen-mm-plugins[core]@git+...", "qwen-mm-plugins-core"]
envVars:
  DASHSCOPE_API_KEY:
    description: 阿里百炼平台 API Key
    default: ""
    required: false
skills:
  - name: core
    description: 本地多模态读取工具
```

**适用场景**：大多数情况。安装时一步到位，MCP 配置和密钥声明随插件一起导入。

### split 模式

MCP 配置和密钥声明拆分为独立文件，`plugin.yaml` 只保留引用。

**zip 结构：**
```
qwen-mm-plugins-plugin.zip
├── qwen-mm-plugins.plugin.yaml    ← mcp_file + keys_file 引用
├── mcp.yaml                        ← MCP servers 配置
├── keys.yaml                       ← 密钥声明（值为空，用户填充）
└── skills/
    ├── core/SKILL.md
    ├── api/SKILL.md
    └── search/SKILL.md
```

**plugin.yaml 内容示例：**
```yaml
name: qwen-mm-plugins
version: 1.0.0
description: 给 AI Agent 装上眼睛
mcp_file: mcp.yaml
mcp_servers_ref: ["qwen-core", "qwen-api", "qwen-search"]
keys_file: keys.yaml
skills:
  - name: core
    description: 本地多模态读取工具
```

**mcp.yaml 内容示例：**
```yaml
mcpServers:
  qwen-core:
    command: uvx
    args: ["--from", "qwen-mm-plugins[core]@git+...", "qwen-mm-plugins-core"]
```

**keys.yaml 内容示例：**
```yaml
mcp:
  DASHSCOPE_API_KEY:
    value: ""
    description: 阿里百炼平台 API Key
  SERPER_API_KEY:
    value: ""
    description: Serper API Key
```

**适用场景**：MCP 配置较复杂或密钥需要独立管理时。对齐现有 `export_plugin` 的 extras 导出逻辑，安装时分别导入到 `config/mcp/mcp.yaml` 和 `config/llm/keys.yaml`。

---

## 来源分析能力

| 来源类型 | 格式 | 分析方式 | 提取内容 |
|---------|------|---------|---------|
| GitHub 仓库 | `owner/repo` 或完整 URL | GitHub API 获取文件树 | README 描述、`.mcp.json` MCP 配置、`SKILL.md` 技能列表、`.claude-plugin/plugin.json` 元数据 |
| 文章 URL | `https://mp.weixin.qq.com/s/xxx` | `--ai` 时用 AI 分析；否则抓取 HTML | 标题、正文摘要 |
| 本地目录 | `./my-plugin/` 或绝对路径 | 扫描文件系统 | 已有 `plugin.yaml`、`SKILL.md` 目录 |

GitHub 分析支持 `GITHUB_TOKEN` 环境变量提高 API 速率限制。

---

## 相关文件

| 文件 | 作用 |
|------|------|
| `cli/lib/plugin_builder.py` | PluginBuilder 引擎核心（analyze + download + generate + package + publish） |
| `cli/lib/auth.py` | JWT 认证（login/register/whoami/logout，token 存 `~/.agentbuddy/auth.json`） |
| `cli/agentctl.py` | `plugin build`、`plugin publish`、`plugin auth` 子命令 |
| `desktop/config_server.py` | `/api/plugin/analyze`、`/api/plugin/build` 路由 + `_extract_bearer_token` |
| `desktop/frontend/src/stores/pluginBuild.ts` | `analyzeSource()`、`buildFromSource()` 前端状态和方法 |
| `desktop/frontend/src/views/PluginBuildView.vue` | 「🔗 一键构建」标签页 UI |
| `server/PluginMarketWorker.py` | 独立 worker 脚本（cron 调度） |
| `server/config/plugin-sources.yaml` | 抓取源配置 |
| `template/plugins/plugin.schema.yaml` | 插件 YAML Schema 定义 |
