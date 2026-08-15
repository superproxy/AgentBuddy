# AgentBuddy — 智能体构建与分发平台

- **项目定位**：AI 智能体构建与分发平台 — 可视化构建智能体配置（LLM / MCP / Skills / Rules / Commands / Subagents / Hooks），通过插件化打包分发，一键同步到多 IDE
- **技术栈**：Python 3 + Flask + pywebview + PyInstaller（桌面应用）+ Vue 3 + Vite（前端）
- **核心能力**：
  - **智能体构建**：LLM Provider、MCP 服务、Skills、Rules、Commands、Subagents、Hooks 的可视化编辑与组合
  - **插件分发**：插件打包（zip 含 yaml + skills + llm key + rules + commands + subagents + hooks）→ 导入导出 → 跨团队共享
  - **多 IDE 同步**：一键同步到 ZCode / Trae / OpenCode / Claude / Cursor / Codex / OpenClaw / WorkBuddy / Copilot / Cline / DeepSeek 等 IDE（含 ACP 协议）
  - **桌面应用**：pywebview 桌面版，无需部署服务端，本地运行
- **主要业务流程**：智能体构建 → 插件打包 → 分发导入 → 同步多 IDE

> 原 AGENTS.md（仓库级治理文档）已备份为 `AGENTS.old.md`，含业务角色路由 / Rules / MCP / Skills 矩阵。

---

## 开发规范（强制）

> 以下规范由近期反复出现的低级问题沉淀而来，**发布前必须逐条检查**。

### 1. generate ≠ sync — 配置变更后两步缺一不可

**问题**：修改 LLM 配置后只 generate（生成到 `config/ide/`），不 sync（同步到 `~/.codex/` `~/.claude/` 等），导致 IDE 不生效。

**规则**：
- `/api/init-env`（自动保存触发）必须执行 `agentctl generate` + `agentctl sync --ide All --force --scope llm,mcp`
- `/api/init-ide`（手动同步触发）必须先 generate 再 sync（已在 `agentctl sync` 内置）
- 任何修改 `config/llm/llm.yaml` 或 `config/mcp/mcp.yaml` 的 API，返回前必须触发 generate + sync

### 2. 打包模式检测 — 不能用子进程执行 Python 代码

**问题**：打包后 `AgentBuddy.exe -c "import litellm"` 失败，PyInstaller exe 不是标准 Python 解释器。

**规则**：
- `getattr(sys, "frozen", False)` 为 True 时，**直接在当前进程 `import`** 检测库是否可用
- 子进程检测仅用于开发模式（`sys.executable` 是真实 Python 解释器）
- 启动打包内嵌的 Python 模块用 `python -m <module>`，不用 PATH 中的 CLI 命令

### 3. 第三方库版本属性 — 不要假设 `__version__`

**问题**：`litellm.__version__` 不存在（litellm 1.93.0 用 `litellm._version.version`），导致检测永远失败。

**规则**：
- 检测第三方库时，`import` 成功即可，版本号用 `importlib.metadata.version("pkg_name")` 获取
- 不要假设库有 `__version__` 属性，先 `hasattr` 检查或 try/except
- 子进程检测的 timeout 要留足（litellm import 需 10-20 秒），至少 30 秒

### 4. PyInstaller 打包 — 用 collect_submodules 自动收集

**问题**：手动列举 litellm 子模块（5 个），遗漏了 40+ 个动态导入的子模块。

**规则**：
- `app.spec` 中对大型库（litellm / fastapi 等）用 `collect_submodules('pkg')` + `collect_data_files('pkg')` 自动收集
- 不要手动列举子模块，维护成本高且容易遗漏
- 新增 Python 依赖时，检查是否需要加入 `hiddenimports`

### 5. 路径 — 日志和命令中不暴露开发目录绝对路径

**问题**：打包后日志显示 `D:\yxz\MyAgentPlugin\config\proxy\config.yaml`，暴露开发目录。

**规则**：
- 命令中使用相对路径（如 `config/proxy/config.yaml`），配合 `cwd=PROJECT_ROOT` 执行
- 日志输出前用 `Path.relative_to(PROJECT_ROOT)` 转相对路径
- 例外：用户需要看到的配置文件路径（如"已生成: config/ide/codex/config.toml"）用相对路径

### 6. 模板占位符 — generate 后必须验证无残留

**问题**：网关模式下 `ANTHROPIC_BASE_URL` 等变量未设置，`settings.json` 中残留 `${VAR}`。

**规则**：
- `agentctl generate` 后检查所有产物中是否残留 `${` 占位符
- 网关模式下，`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL` 必须指向网关地址
- 新增模板变量时，同步在 `flatten_env_config` 中设置对应的 flat key

### 7. 发布前验证清单（强制）

每次打 tag 发布前，**必须执行以下验证**：

```bash
# 0. 功能特性任务列表必须全部 [x]（见「功能特性任务列表」章节）
#    未完成的功能特性不得随版本发布

# 1. generate + sync 全流程
python -m agentctl.agentctl generate
python -m agentctl.agentctl sync --ide All --force --scope llm,mcp,skill,rules

# 2. 检查产物无占位符残留
# codex
grep '\${' config/ide/codex/config.toml config/ide/codex/auth.json
# claude
grep '\${' config/ide/claude/settings.json
# proxy
grep '\${' config/proxy/config.yaml

# 3. 检查关键配置项
# codex config.toml: wire_api = "responses"
# claude settings.json: ANTHROPIC_BASE_URL 已填充
# proxy config.yaml: 路由条目正确

# 4. 前端构建
cd desktop/frontend && npx vite build

# 5. 单元测试
python -m pytest -q
```

以上验证全部通过后，方可 `git tag` 发布。

### 8. 测试策略 — 本地测试，CI 发布跳过

**问题**：CI 发布构建（`build-release.yml`）调用 `build.py` 时也会执行自动测试，测试失败会中断发布；且 CI 环境缺少本地 `config/` 文件，测试易受环境差异影响。

**规则**：
- **本地**：`build.py` 默认执行自动测试（`run_tests()`），pre-commit hook 提交前也执行测试
- **CI 发布**：`build-release.yml` 的 macOS/Windows 构建命令必须加 `--skip-tests`，跳过测试，避免测试失败中断发布
- 测试只在本地执行（本地构建 + 提交前 hook），CI 发布不跑测试
- 新增测试必须使用临时目录/模板文件，不得依赖 `config/` 下被 gitignore 的真实文件（CI 中不存在）

### 9. 旧品牌目录迁移 — 只执行一次，禁止每次启动覆盖用户配置

**问题**：`app.py` 的 `_migrate_legacy_data_dir()` 每次启动都会执行，只要旧品牌目录 `~/Library/Application Support/AdeBuddy/` 存在，就用旧目录的 `llm.yaml` 无条件覆盖新目录的 `llm.yaml`，导致用户在新版本里设置的 Provider `_enabled` 开关在重启后消失。

**规则**：
- 迁移只执行一次：迁移前检查标记文件 `.migrated_from_adebuddy`，已迁移则直接跳过
- 迁移成功后必须写入标记文件 `(PROJECT_ROOT / ".migrated_from_adebuddy")`
- 禁止在迁移逻辑中无条件 `shutil.copy2` 覆盖 `USER_DATA_FILES`（含 `llm.yaml` / `mcp.yaml` / `keys.yaml` 等）——旧目录只应作为一次性数据源，不能反复覆盖新目录中用户的最新修改
- 新增/修改任何"启动时同步/迁移用户数据"的逻辑时，必须保证幂等（只执行一次或只合并缺失项），并补充回归测试（见 `tests/test_legacy_migration_once.py`）

### 10. 功能开发流程 — 先方案后代码

**问题**：直接写代码实现功能，用户无法在动手前把控方向，发现偏差后返工成本高。

**规则**：
- 涉及**功能开发或界面改动**时，**必须先给出设计方案**，等用户审核确认后才能写代码
- 方案需包含：设计思路、改动点（涉及哪些文件/模块）、影响范围、可选方案对比
- 审核通过后再动手实现
- **例外**：简单 bug 修复、用户明确说"直接改"的，可跳过方案审核

## 功能特性任务列表（发布依据）

> 每个条目是一个**功能特性**（Feature），完成时标记 `[x]`。**发布（打 tag）前必须全部 `[x]`**，未完成的功能特性不得随版本发布。新增功能特性时在此追加。

### 智能体构建
- [x] LLM Provider 可视化编辑（base_url / api_key / models / 多协议）
- [x] LLM Provider 启用开关（`_enabled`）持久化，重启不丢失
- [x] LLM 智能添加（粘贴 Key 自动识别厂商 + 协议 + 拉取模型）
- [x] MCP 服务可视化编辑与密钥管理（keys.yaml）
- [x] Skills 搜索 / 安装 / 启用切换（三源目录体系）
- [x] Rules / Commands / Subagents / Hooks 配置编辑
- [x] Subagent「产品经理职责需求梳理」：从业务目标到可执行需求清单（用户故事 + 验收标准 + 优先级 + 风险）

### 插件分发
- [x] 插件打包导出（ZIP 含 skills / YAML 仅配置 / 导出全部）
- [x] 插件导入（ZIP 解压 / YAML / JSON 向后兼容）
- [x] 插件安装 / 卸载 / 列表

### 多 IDE 同步
- [x] 一键同步到 ZCode / Trae / OpenCode / Claude / Cursor / Codex / OpenClaw / WorkBuddy / Copilot / Cline / DeepSeek
- [x] OpenCode 多 Provider 原生协议注入（openai / anthropic / openai-compatible）
- [x] Codex / Claude 默认 LLM 源校验（Provider 或网关二选一）
- [x] LLM 网关（LiteLLM）路由配置与模型列表生成
- [x] IDE CLI 会话恢复命令（Claude / Codex / OpenCode / WorkBuddy / Copilot / Cline / DeepSeek 等）
- [x] ACP 协议支持：Copilot / Cline 通过 `~/.jetbrains/acp.json` 注册为 agent_servers（供 JetBrains AI Assistant / Zed 调用）
- [x] JetBrains 插件命令行安装（`idea installPlugins <plugin-id>`，支持 Copilot / Cline）

### 桌面应用与工程
- [x] pywebview 桌面版（Frozen-aware，macOS / Windows）
- [x] 旧品牌目录迁移只执行一次（不覆盖用户最新配置）
- [x] 自动测试：本地构建 / 提交前运行 pytest（pre-commit hook），CI 发布跳过测试（--skip-tests）
- [x] 发布前验证清单（generate + sync + 占位符检查 + 前端构建）

## 文档导航

| 文档 | 内容 |
|---|---|
| [docs/project-overview.md](docs/project-overview.md) | 项目定位、项目结构、Skill 目录体系（三源）、插件导入导出 |
| [docs/plugin-build.md](docs/plugin-build.md) | 插件构建与发布（三场景：CLI / UI 一键构建 / Crawler 定时任务）、打包模式、API 文档 |
| [docs/build-release.md](docs/build-release.md) | 发布流程（Release）、安装更新（升级覆盖）、Windows 批处理脚本规范 |
| [docs/agent-governance.md](docs/agent-governance.md) | Agent 架构拓扑、协作流程、治理规则、FAQ/最佳实践、自我迭代、协同进度、Skill 依赖表、通信协议 |

## IDE CLI 会话恢复命令参考

> 所有命令均来自官方文档验证，禁止臆测。更新时务必查官方文档。

| IDE | 命令 | 官方文档来源 |
|-----|------|-------------|
| Claude | `claude --resume <id>` | docs.anthropic.com/claude-code/cli-reference |
| Codex | `codex resume <id>` | 用户确认（非 `--resume`） |
| KimiCLI / KimiCode | `kimi --session <id>` | kimi-cli.com/reference/kimi-command |
| Cursor | `cursor --continue` | 无 `--resume`，只能继续最近会话 |
| OpenCode | `opencode --session <id>` | open-code.ai/docs/cli（非 `--resume`） |
| Qoder | `qodercli -r <id>` | docs.qoder.com/zh/cli/using-cli（非 `--resume`） |
| QoderCN | `qoderclicn -r <id>` | help.aliyun.com/zh/lingma/qodercli-cn |
| WorkBuddy | `codebuddy --resume <id>` | codebuddy.ai/docs/cli/slash-commands |
| TraeCN | `traecli --resume <id>` | docs.trae.cn/cli |
| Copilot | `copilot --resume <id>` | docs.github.com/en/copilot/cli（CLI 预览版，`--resume[=VALUE]`） |
| Cline | `cline resume <session-id>` | docs.cline.bot/usage/cli-overview |
| DeepSeek | `dsh resume <session-id>` | deepseek-harness.github.io/deepseek-harness/guide/cli |

### 不支持 CLI 会话恢复的 IDE

| IDE | 原因 |
|-----|------|
| OpenClaw | Gateway 服务架构，非 TUI CLI（`openclaw sessions` 仅列出会话，无 `--resume` 参数） |
| ZCode | 桌面 IDE，非 TUI CLI（会话管理通过 UI 进行） |
| Copilot (ACP) | ACP 模式作为 agent server，会话由 JetBrains/Zed 客户端管理，CLI 不直接支持 resume |
| Cline (ACP) | ACP 模式作为 agent server，会话由 JetBrains/Zed 客户端管理 |

### Copilot 远程控制（Remote Control）

> 来源：docs.github.com/zh/copilot/how-tos/copilot-cli/steer-remotely

Copilot CLI 支持远程控制——从 GitHub.com 或 GitHub Mobile 操控本地 CLI 会话。

| 命令 | 说明 |
|------|------|
| `copilot --remote` | 启动时启用远程控制 |
| `copilot --no-remote` | 启动时禁用远程控制 |
| `copilot --resume <id> --remote` | 恢复会话并重新启用远程控制 |
| `/remote on` / `/remote off` | 会话内切换远程控制开关 |

AgentBuddy 在 Copilot 卡片提供「远程控制」按钮，一键启动 `copilot --remote`。

## Git 部署约定

- **推送**：只推 GitHub（`git push`），不手动推 Gitee
- **Gitee 自动同步**：Gitee 仓库配置了从 GitHub 自动镜像同步，push GitHub 后 Gitee 会自动拉取
- **服务器部署**：服务器 `run.sh update` 从 Gitee 拉取代码，Gitee 同步延迟约 1-2 分钟，部署前等待同步完成
- **部署命令**：`cd /root/AgentBuddy/server && ./run.sh update`（自动 git pull + 重启）
