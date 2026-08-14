# AgentBuddy — 项目结构与技术

## 项目定位
- **项目目标**：把 agents/ 共享配置（LLM/MCP/Skills/Rules）一键映射到多 IDE 的桌面工具
- **技术栈**：Python 3 + Flask + pywebview + PyInstaller（桌面应用）+ Vue 3 + Vite（前端）
- **主要业务流程**：配置编辑 → 生成 → 同步多 IDE

> 原 AGENTS.md（仓库级治理文档）已备份为 `AGENTS.old.md`，含业务角色路由 / Rules / MCP / Skills 矩阵。

## 项目结构
```
desktop/                    # 桌面应用层（API + Vue 前端 + 启动器）
  launcher.py               # pywebview 桌面启动器（Frozen-aware）
  service/config_server.py  # Flask 后端（API + SSE 流式安装）
  frontend/                 # Vue 3 + Vite + Pinia + TailwindCSS
    src/stores/plugin.ts    # 插件 store（导入导出 / 安装 / 卸载）
    src/stores/skill.ts     # 技能 store（搜索 / 安装 / 启用切换）
    src/views/PluginView.vue    # 插件列表（导出下拉菜单 ZIP/YAML）
    src/views/PluginBuildView.vue  # 插件构建
    src/views/SkillView.vue # 技能管理
cli/                        # CLI 层（独立可发布的 agentctl 包）
  agentctl.py               # CLI 入口（generate / sync / install / uninstall）
  lib/                      # 公共库（skills / plugins / mcp / llm / ide/）
    skills.py               # skill 安装 + 同步 + 启用清单
    plugins.py              # 插件安装编排 + CSV 生成
    config_io.py            # yaml/json 读写
    ide/                    # IDE 检测 / 启动 / 会话 / 安装
  pyproject.toml            # agentctl 包元数据（pip install -e cli/）
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
| `template/skills/` | 预置清单（只读缓存） | `skills-index.csv` 登记所有预置/远程 skill 元信息；skill 目录按需存在 |
| `.agents/skills/` | 安装目标 | `npx skills add` / 插件安装写入此处 |
| `config/skills/` | 项目级副本 | 本地缓存复制 + 导入 zip 解压目标，含 `skill.yaml` 启用清单 |

> sync 时三源并集，前源优先（同名跳过）。`skill.yaml` 控制启用清单。
> 「本地预置」列表（`/api/skills/local`）扫描三源目录下有 `SKILL.md` 的 skill，前源优先去重，合并 CSV 元信息。

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
