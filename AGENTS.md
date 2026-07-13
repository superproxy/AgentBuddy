# AdeBuddy — Harness Engineering 入口

## 项目定位
- **项目目标**：把 agents/ 共享配置（LLM/MCP/Skills/Rules）一键映射到多 IDE 的桌面工具
- **技术栈**：Python 3 + Flask + pywebview + PyInstaller（桌面应用）+ Vue 3 + Vite（前端）
- **主要业务流程**：配置编辑 → 生成 → 同步多 IDE

> 原 AGENTS.md（仓库级治理文档）已备份为 `AGENTS.old.md`，含业务角色路由 / Rules / MCP / Skills 矩阵。

## 项目结构
```
app.py                      # pywebview 桌面启动器（Frozen-aware）
tools/config_server.py      # Flask 后端（API + SSE 流式安装）
scripts/agentctl.py         # CLI 入口（generate / sync / install / uninstall）
scripts/lib/                # 公共库（skills / plugins / mcp / llm / ide/）
  skills.py                 # skill 安装 + 同步 + 启用清单
  plugins.py                # 插件安装编排 + CSV 生成
  config_io.py              # yaml/json 读写
  ide/                      # IDE 检测 / 启动 / 会话 / 安装
frontend/                   # Vue 3 + Vite + Pinia + TailwindCSS
  src/stores/plugin.ts      # 插件 store（导入导出 / 安装 / 卸载）
  src/stores/skill.ts       # 技能 store（搜索 / 安装 / 启用切换）
  src/views/PluginView.vue  # 插件列表（导出下拉菜单 ZIP/YAML）
  src/views/PluginBuildView.vue  # 插件构建
  src/views/SkillView.vue   # 技能管理
config/                     # 运行态配置（用户可编辑）
  llm/llm.yaml              # LLM Provider 配置
  mcp/mcp.yaml              # MCP 服务定义 + 密钥
  skills/                   # 项目级 skill 副本 + skill.yaml 启用清单
  cmd/cmd.yaml              # 常用命令
  subagent/subagent.yaml    # 预设角色
template/                   # 只读模板（首次运行复制到 config/）
  plugins/*.plugin.yaml     # 预定义插件
  skills/                   # 内置预置技能
  llm/ mcp/ cmd/ subagent/  # 各配置示例
.agents/skills/              # 安装目标（npx skills add / 插件安装）
```

## Skill 目录体系（三源）
| 目录 | 作用 | 说明 |
|---|---|---|
| `template/skills/` | 内置预置（只读缓存） | 首次运行复制到 config/skills/，约 6 个 |
| `.agents/skills/` | 安装目标 | `npx skills add` / 插件安装写入此处，约 80 个 |
| `config/skills/` | 项目级副本 | 本地缓存复制 + 导入 zip 解压目标，含 skill.yaml |

> sync 时三源并集，前源优先（同名跳过）。`skill.yaml` 控制启用清单。

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

## Agent 架构拓扑
6 角色，详见 `agents/harness.yaml`：

| 角色 | 隐喻 | 核心职责 |
|---|---|---|
| architect 🏛️ | 总经理 | 架构骨架、范围冻结、风险评估、演进点清单 |
| orchestrator 🎖️ | 参谋部 | triage-route 路由、阶段切换守门、backlog 管理 |
| executor ⚔️ | 先锋营 | TDD 红绿重构、小步快跑、YAGNI 约束 |
| reviewer 🔍 | 监军 | DoD 验收、TDD 覆盖检查、多维度审查 |
| devops 🚚 | 后勤辎重 | 演进式部署、监控、启停脚本自审视 |
| retro-optimizer 📜 | 军师史官 | Sprint 回顾、strangler fig 评估、角色武器库同步（飞轮） |

## 协作流程
- 日常开发：`standard-dev` 工作流（triage → route → implement → review → fix → deploy → retro）
- 架构优先：`architecture-first` 工作流
- 代码审查：`code-review` 工作流
- PRD 到代码：`prd-to-code` 工作流
- 调试：`debug-flow` 工作流
- 运维：`devops-ops` 工作流
- 双阶段融合开发（条件启用，默认关闭）：`dual-phase-dev` 工作流

## 治理规则
- **大决策（用户）**：项目目标 / 技术栈 / dual-phase-dev 启停 / Agent 范围 / 大周期 N / 通信超时
- **小决策（角色自决）**：节点-skill 映射、FAQ 条目、经验归类、角色契约、启停脚本、武器库同步
- **决策升级**：小决策遇阻 → orchestrator → 跨角色协调或升级大决策
- **决策可错性**：每决策标注可证伪条件，retro-optimizer 在 Sprint 回顾时检验是否被推翻

## FAQ / 最佳实践入口
- 负向错误沉淀：`agents/faq/{role}.faq.md`
- 正向经验沉淀：`agents/best-practices/{role}.best-practices.md`
- 跨角色经验：`agents/evolution/lessons-learned.md`

## 自我迭代机制
- **小步快跑**：每次交互 collect → analyze → sink → iterate（角色自决，最小改动）
- **大周期沉淀**：每 N=10 轮或 `/harness-evolve`（orchestrator 牵头，模式固化、角色定义升级）
- 详见 `agents/evolution/evolution.yaml`

## 协同进度
- 进度看板：`agents/sync/progress.yaml`
- 操作日志：`agents/sync/sync-log.md`
- 交接记录：`agents/sync/handoffs/`
- 经验总结：`agents/sync/experience-summary.md`

## 交互记录
用户询问与变更归档：`docs/interaction-changes/`（每次 Harness 配置调整同步追加）

## Skill 依赖表
| Skill | 必需/可选 | 用途 |
|---|---|---|
| brainstorming | 必需 | 需求澄清 |
| writing-plans | 必需 | 实施计划 |
| subagent-driven-development | 必需 | 逐任务实施 |
| test-driven-development | 必需 | TDD 红绿重构 |
| systematic-debugging | 必需 | 系统化调试 |
| verification-before-completion | 必需 | 完成前验证 |
| requesting-code-review | 必需 | 代码审查 |
| receiving-code-review | 必需 | 审查反馈修复 |
| codebase-design | 可选 | 启用 architecture-first/dual-phase-dev 时必需 |
| design-an-interface | 可选 | 启用 architecture-first/dual-phase-dev 时必需 |
| review | 可选 | 标准化代码审查 |
| dispatching-parallel-agents | 可选 | orchestrator 并行任务派发 |
| setup-pre-commit | 可选 | 提交钩子 |
| git-guardrails-claude-code | 可选 | git 安全防护 |

## 通信协议
详见 `agents/communication.yaml`（JSON 格式 + 超时 30s + 重试 3 次 + 消息 schema）。

