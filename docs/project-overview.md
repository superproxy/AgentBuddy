# AgentBuddy — 项目结构与技术

## 项目定位
- **项目目标**：AI 智能体构建与分发平台 — 可视化构建智能体配置，通过插件化打包分发，一键同步到多 IDE
- **技术栈**：Python 3 + Flask + pywebview + PyInstaller（桌面应用）+ Vue 3 + Vite（前端）
- **主要业务流程**：智能体构建 → 插件打包 → 分发导入 → 同步多 IDE

> 原 AGENTS.md（仓库级治理文档）已备份为 `AGENTS.old.md`，含业务角色路由 / Rules / MCP / Skills 矩阵。

---

## 三端服务总览

```
AgentBuddy/
├── cli/          # ① CLI 端 — agentctl 命令行工具（独立可发布的 Python 包）
├── desktop/      # ② 桌面端 — pywebview 桌面应用（Flask API + Vue 前端 + 启动器）
├── server/       # ③ 服务端 — 远程服务（插件市场 + AI 生成器 + 认证）
├── template/     # 只读配置模板（首次运行复制到 config/）
├── config/       # 运行态配置（用户可编辑，含真实密钥，gitignored）
├── agents/       # 智能体治理文档（角色 / 工作流 / 最佳实践）
├── tests/        # 单元测试
├── docs/         # 项目文档
├── scripts/      # 辅助脚本
└── 构建文件       # build.py / app.spec / build.sh / build.cmd
```

---

## ① CLI 端 — `cli/`

独立可发布的 Python 包，提供 `agentctl` 命令行工具。

```
cli/
├── agentctl.py               # CLI 入口（generate / sync / install / uninstall）
├── cleanup.py                # 清理工具
├── pyproject.toml            # 包元数据（pip install -e cli/）
└── lib/                      # 公共库
    ├── paths.py              # 路径解析（PROJECT_ROOT / frozen-aware）
    ├── config_io.py          # yaml/json 读写
    ├── llm.py                # LLM 配置处理
    ├── mcp.py                # MCP 配置处理
    ├── plugins.py            # 插件安装编排 + CSV 生成
    ├── skills.py             # skill 安装 + 同步 + 启用清单
    ├── session.py            # 会话管理
    └── ide/                  # IDE 同步模块（每个 IDE 一个文件）
        ├── base.py           # IDE 基类
        ├── detect.py         # IDE 检测
        ├── launch.py         # IDE 启动
        ├── install.py        # JetBrains 插件安装
        ├── ide.yaml          # IDE 元数据
        ├── claude.py         # Claude 同步
        ├── codex.py          # Codex 同步
        ├── cursor.py         # Cursor 同步
        ├── opencode.py       # OpenCode 同步
        ├── copilot.py        # Copilot 同步（含 ACP）
        ├── cline.py          # Cline 同步（含 ACP）
        ├── deepseek.py       # DeepSeek 同步
        ├── workbuddy.py      # WorkBuddy 同步
        ├── zcode.py          # ZCode 同步
        ├── trae.py           # Trae 同步
        ├── qoder.py          # Qoder 同步
        ├── kimi.py          # KimiCLI 同步
        ├── openclaw.py       # OpenClaw 同步
        ├── idea.py          # JetBrains IDEA 同步
        └── ...              # 其他 IDE
```

**核心命令**：
- `agentctl generate` — 从 `config/` 生成 IDE 配置到 `config/ide/`
- `agentctl sync --ide All --force` — 同步到各 IDE 配置目录
- `agentctl install <plugin>` — 安装插件
- `agentctl uninstall <plugin>` — 卸载插件

---

## ② 桌面端 — `desktop/`

pywebview 桌面应用，无需部署服务端，本地运行。

```
desktop/
├── launcher.py               # pywebview 桌面启动器（Frozen-aware）
├── config_server.py          # Flask 后端（API + SSE 流式安装 + 静态文件服务）
├── frontend/                 # Vue 3 + Vite + Pinia + TailwindCSS
│   ├── index.html            # Vite 入口
│   ├── package.json          # 依赖管理
│   ├── vite.config.ts        # Vite 配置（outDir: ../dist-ui/）
│   ├── tsconfig.json        # TypeScript 配置
│   ├── src/
│   │   ├── main.ts            # Vue 应用入口
│   │   ├── App.vue            # 根组件
│   │   ├── style.css          # 全局样式（TailwindCSS）
│   │   ├── api/               # API 客户端
│   │   │   ├── client.ts      # HTTP 请求封装
│   │   │   ├── download.ts    # 下载处理
│   │   │   └── sse.ts         # SSE 流式事件
│   │   ├── components/         # 通用组件
│   │   │   ├── Header.vue     # 顶部导航
│   │   │   ├── SyncBar.vue    # 同步操作栏
│   │   │   ├── Modal.vue      # 模态框
│   │   │   ├── Toast.vue      # 通知
│   │   │   ├── AuthDialog.vue # 认证弹窗
│   │   │   ├── LogPanel.vue   # 日志面板
│   │   │   └── SmartProviderPicker.vue  # 智能选择 Provider
│   │   ├── stores/            # Pinia 状态管理
│   │   │   ├── llm → LlmView       # LLM Provider
│   │   │   ├── mcp → McpView       # MCP 服务
│   │   │   ├── skill → SkillView   # 技能管理
│   │   │   ├── plugin → PluginView # 插件列表
│   │   │   ├── pluginBuild → PluginBuildView  # 插件构建
│   │   │   ├── marketplace → MarketplaceView  # 插件市场
│   │   │   ├── ide → IdeView       # IDE 同步
│   │   │   ├── sync → SyncBar      # 同步状态
│   │   │   ├── keys → KeysView     # 密钥管理
│   │   │   ├── rules → RulesView   # 规则
│   │   │   ├── cmd → CommandView   # 命令
│   │   │   ├── subagent → SubagentView  # 子智能体
│   │   │   ├── hooks → HooksView   # 钩子
│   │   │   ├── memory → MemoryView # 记忆
│   │   │   ├── terminal → TerminalView  # 终端
│   │   │   ├── auth               # 认证状态
│   │   │   ├── aiGenerate         # AI 生成
│   │   │   ├── theme              # 主题
│   │   │   ├── env                # 环境变量
│   │   │   ├── ui                 # UI 状态
│   │   │   └── upgrade            # 升级检查
│   │   └── views/              # 页面视图（与 stores 对应）
│   │       ├── LlmView.vue
│   │       ├── McpView.vue
│   │       ├── SkillView.vue
│   │       ├── PluginView.vue
│   │       ├── PluginBuildView.vue
│   │       ├── MarketplaceView.vue
│   │       ├── IdeView.vue
│   │       ├── KeysView.vue
│   │       ├── RulesView.vue
│   │       ├── CommandView.vue
│   │       ├── SubagentView.vue
│   │       ├── HooksView.vue
│   │       ├── MemoryView.vue
│   │       └── TerminalView.vue
│   └── design-previews/      # 设计预览（仅本地参考，gitignored）
├── dist-ui/                  # Vite 构建产物（gitignored，由 build.py 生成）
└── README.md                 # 桌面端说明
```

**运行模式**：
- **开发模式**：`python desktop/launcher.py` → Flask 服务 `localhost:5000` + pywebview 窗口
- **打包模式**：PyInstaller onedir → `AgentBuddy.app` / `AgentBuddy.exe`
  - `PROJECT_ROOT` = exe 目录（macOS: `~/Library/Application Support/AgentBuddy/`）
  - 首次运行从 bundle 同步 `template/` → `config/`

**Flask API 服务**（`config_server.py`）：
- `/api/llm/*` — LLM Provider CRUD
- `/api/mcp/*` — MCP 服务 CRUD
- `/api/skills/*` — 技能搜索 / 安装 / 启用
- `/api/plugin/*` — 插件导入导出 / 安装 / 卸载
- `/api/init-env` — 自动保存（generate + sync）
- `/api/init-ide` — 手动同步
- `/api/sync/*` — IDE 同步状态
- `/api/marketplace/*` — 插件市场（代理到 server）
- SSE 流式安装日志

---

## ③ 服务端 — `server/`

远程服务，提供插件市场、AI 生成器、用户认证。

```
server/
├── app.py                    # Flask 应用入口
├── run.sh / run.bat          # 启动脚本
├── requirements.txt          # 服务端依赖
├── DEPLOY.md                 # 部署文档
├── marketplace/              # 插件市场
│   ├── routes.py             # 市场 API（发布 / 搜索 / 下载 / 评分）
│   └── storage.py            # 存储层（SQLite）
├── ai_generator/             # AI 智能生成器
│   ├── routes.py             # 生成 API
│   ├── generator.py          # 生成逻辑（LLM 调用）
│   └── skills/               # 生成提示词模板
│       ├── plugin_design.md
│       ├── plugin_generate.md
│       └── toolchain_patterns.md
├── auth/                     # 用户认证
│   ├── routes.py             # 认证 API（注册 / 登录 / Token）
│   ├── middleware.py         # JWT 中间件
│   └── models.py             # 用户模型
├── web/                      # 服务端 Web 页面
│   └── index.html
└── data/                     # 运行态数据（gitignored）
    └── agentbuddy.db         # SQLite 数据库
```

**部署**：`cd /root/AgentBuddy/server && ./run.sh update`（自动 git pull + 重启）

---

## 配置体系

### template/ — 只读模板

首次运行时复制到 `config/`，是所有配置的初始来源。

```
template/
├── llm/llm-template.yaml         # LLM Provider 模板
├── mcp/mcp-template.yaml          # MCP 服务模板
├── cmd/cmd.yaml                   # 常用命令模板
├── hooks/hooks.json               # Hooks 模板
├── memory/memory.json             # 记忆模板
├── subagent/subagent.yaml         # 预设角色模板
├── proxy/config.template.yaml     # LLM 网关（LiteLLM）模板
├── plugins/                       # 预定义插件（19 个）
│   ├── *.plugin.yaml              # 各角色插件配置
│   └── plugin.schema.yaml         # 插件 Schema
├── rules/                         # 规则模板（10 个）
│   ├── backend/*.md               # 后端规范
│   ├── frontend/*.md              # 前端规范
│   ├── design/*.md                # 设计规范
│   ├── security/*.md              # 安全规范
│   └── ...
├── skills/                        # 内置预置技能
│   └── skills-index.csv           # 技能索引
├── ide/                           # IDE 配置模板
│   ├── claude/settings.template.json
│   ├── codex/config.template.toml
│   ├── codex/auth.template.json
│   ├── opencode/opencode.template.json
│   ├── idea/acp.json              # ACP 协议配置
│   └── ...
└── system-prompts/                # 系统提示词
```

### config/ — 运行态配置（gitignored）

由 `template/` 生成，用户可编辑，含真实密钥。

```
config/
├── llm/llm.yaml               # LLM Provider 配置（base_url / api_key / models）
├── mcp/mcp.yaml               # MCP 服务定义 + 密钥引用
├── keys.yaml                  # 密钥存储（API Key / Token）
├── cmd/cmd.yaml               # 常用命令
├── hooks/hooks.json           # Hooks 配置
├── memory/memory.json         # 记忆数据
├── subagent/subagent.yaml     # 预设角色
├── proxy/config.yaml          # LLM 网关配置
├── skills/                    # 项目级技能副本 + skill.yaml 启用清单
├── ide/                       # 生成的 IDE 配置（agentctl generate 产物）
│   ├── claude/settings.json
│   ├── codex/config.toml
│   ├── codex/auth.json
│   ├── opencode/opencode.json
│   └── ...
├── marketplace/               # 市场缓存
├── plugins/                   # 插件安装状态
├── rules/                     # 规则
├── ui/                        # UI 配置
└── memory/                    # 记忆
```

---

## Skill 目录体系（三源）

| 目录 | 作用 | 说明 |
|---|---|---|
| `template/skills/` | 预置清单（只读缓存） | `skills-index.csv` 登记所有预置/远程 skill 元信息；skill 目录按需存在 |
| `.agents/skills/` | 安装目标 | `npx skills add` / 插件安装写入此处 |
| `config/skills/` | 项目级副本 | 本地缓存复制 + 导入 zip 解压目标，含 `skill.yaml` 启用清单 |

> sync 时三源并集，前源优先（同名跳过）。`skill.yaml` 控制启用清单。
> 「本地预置」列表（`/api/skills/local`）扫描三源目录下有 `SKILL.md` 的 skill，前源优先去重，合并 CSV 元信息。

---

## 插件导入导出

### 导出（两种格式）
- **ZIP（含 Skills）**：`GET /api/plugin/export?file=xxx.plugin.yaml&format=zip`
  - zip 结构：`xxx.plugin.yaml` + `skills/<name>/...`
  - skill 搜索路径：`config/skills/` → `.agents/skills/` → `template/skills/`
- **YAML（仅配置）**：`GET /api/plugin/export?file=xxx.plugin.yaml&format=yaml`
  - 返回原始 plugin.yaml，不含 skills
- **导出全部**：`GET /api/plugin/export-all` → `plugins-export.zip`（所有插件 + 去重 skills）

### 导入
- **ZIP 包**：`POST /api/plugin/import`（multipart/form-data，`file` 字段）
  - 自动解压：`*.plugin.yaml` → `template/plugins/`，`skills/<name>/` → `config/skills/`
  - 支持 `overwrite=true` 覆盖同名
- **YAML 文件**：同上 multipart 上传 `.yaml` 文件
- **JSON body（向后兼容）**：`POST /api/plugin/import`（application/json，`{filename, content, overwrite}`）

---

## 构建与打包

### 构建流程
```
build.py
  ├── build_frontend()    # cd desktop/frontend && npm install && npm run build-only → desktop/dist-ui/
  ├── write_version()    # 写入版本号
  └── PyInstaller        # app.spec → dist/AgentBuddy.app 或 AgentBuddy.exe
```

### PyInstaller 打包（app.spec）
- **pathex**: `['cli', 'desktop', 'server']` — Python 模块搜索路径
- **datas**: `template/` + `desktop/dist-ui/` + `agents/` 打入 bundle
- **hiddenimports**: litellm / fastapi 等用 `collect_submodules` 自动收集

### 运行时路径解析
- **开发模式**：`PROJECT_ROOT` = 仓库根目录
- **打包模式**：`PROJECT_ROOT` = exe 目录（macOS: `~/Library/Application Support/AgentBuddy/`）
  - 首次运行从 bundle 同步 `template/` → `config/`（标记文件 `.bundle_bootstrapped`）
