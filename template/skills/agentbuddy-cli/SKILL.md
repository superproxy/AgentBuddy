---
name: agentbuddy-cli
description: >-
  用 AgentBuddy / 飞翼的 CLI（agentctl）查询、同步或清除各 IDE 的 LLM/MCP/Skills 配置，并验证目标
  IDE（尤其是 WorkBuddy）的配置是按当前设定被替换而不是追加。当用户要在命令行测试同步/清除、核对 WorkBuddy 的
  models.json，或检查 CLI 覆盖范围时使用。不要把密钥写入报告。
---
# AgentBuddy CLI（agentctl）

用命令行驱动 AgentBuddy（产品名也可显示为「飞翼」）的同步与清除，并核对目标 IDE 配置是否按当前 LLM 设定被改写。本 skill 是通用步骤，不要写死某台机器的路径或账号。

## 何时使用

- 要用命令（而不是只点界面）同步或清除某个 IDE，尤其是 WorkBuddy
- 要确认 CLI 入口、参数、哪些命令会写配置
- 要做完整性验证：备份 → 快照 → 调用 → 对比目标文件是否被替换而非追加

不要用本 skill 去改用户的真实配置，除非用户明确要求执行同步或清除。只读查询优先。

## 可执行入口

按环境任选其一。项目根（`PROJECT_ROOT`）：源码仓库根；macOS 打包版是 `~/Library/Application Support/AgentBuddy`；Windows 打包版是安装目录（`AgentBuddy.exe` 所在目录）。

| 入口 | 适用 | 示例 |
| --- | --- | --- |
| `agentctl` | 已 `pip install -e cli/`（包名 `agentctl`，脚本入口 `agentctl.agentctl:main`） | `agentctl provider` |
| `python -m agentctl.agentctl` | 已把 `cli/` 映射为 `agentctl` 包（见 `cli/pyproject.toml` 的 `package-dir`） | `python -m agentctl.agentctl provider` |
| 仓库内文件 | 开发树 | 把 `cli/` 放到 `PYTHONPATH` 后同样用 `-m agentctl.agentctl` |
| 打包桌面程序 `--run agentctl` | 已安装的桌面版 | macOS: `"<App>.app/Contents/MacOS/AgentBuddy" --run agentctl provider`；Windows: `AgentBuddy.exe --run agentctl provider` |

注意：

- 打包版把 `--help` / `-h` 解析在启动器层，`AgentBuddy --run agentctl --help` 不会显示 agentctl 帮助。查看子命令帮助请用 `python -m agentctl.agentctl <cmd> -h`，或先运行 `AgentBuddy --run agentctl`（无子命令会打印 usage）。
- 不要对正在跑的 AgentBuddy 进程做 kill。桌面后端默认监听 `127.0.0.1:5050`。
- PowerShell 5 不要用 `$_`、`\"` 或 `&&`；Windows 上用 `py -3`。

## 与同步 / 清除 / IDE 相关的命令

`--ide` 可选值（大小写需与注册表一致）：`All`，以及 `Agents`、`Claude`、`CherryStudio`、`Cline`、`CodeBuddy`、`Codex`、`CommandCode`、`Copilot`、`Cursor`、`DeepSeek`、`Hermes`、`IDEA`、`KimiCLI`、`KimiCode`、`KimiWork`、`OpenClaw`、`OpenCode`、`OpenWorker`、`Pi`、`Qoder`、`QoderCN`、`Trae`、`TraeCN`、`TraeSoloCN`、`VSCode`、`WorkBuddy`、`ZCode`。

| 命令 | 作用 | 关键参数 | 默认 | 危险程度 |
| --- | --- | --- | --- | --- |
| `provider` | 查看或切换活跃 LLM provider / 协议 | 省略名称则只读；`name` 切换；`--protocol openai\|anthropic` | 只读查看 | **只读**（不带名称）；带名称会改 `config/llm/llm.yaml` |
| `sync` | 把当前设定同步到 IDE | `--ide/-i`（默认 `All`）、`--force/-f` 覆盖已存在文件、`--scope`、`--skills` | `--scope llm,mcp,skill,rules` | **会写 IDE 配置**。无 `--force` 时，目标文件已存在则跳过（WorkBuddy 的 `~/.workbuddy/models.json` 也是如此） |
| `generate` | 只生成运行态模板（mcp.json、各 IDE 模板），不写用户级 IDE 目录 | `--provider`、`--protocol` | 按当前 llm.yaml | 写项目内生成物，一般不直接改 `~/.workbuddy` |
| `setup` | `generate` + `sync`（不含插件安装） | 无额外 IDE 参数，等同全量 sync | 全流程 | **会写 IDE 配置** |
| `env` / `shell` | 设置或导出环境变量 | `env --scope process\|user`，`--force` 跳过确认 | `process` | `env` 会改环境变量；`shell` 只读打印 |
| `plugin` / `skill` | 插件与技能管理 | install/list/uninstall/build/publish；skill list/enable/disable/scan/gen-plugin | 见 `--help` | list/scan **只读**；install/uninstall/enable/disable **会写配置** |

**CLI 没有 `clear` 子命令。** 清除已同步的 LLM 要用 HTTP `POST /api/llm/clear-sync`（见 companion skill `agentbuddy-api`），或在 `PROJECT_ROOT` 可用的 Python 环境里调用：

```bash
python -c "from pathlib import Path; from agentctl.lib.ide.clear_llm import clear_llm_for_ides; import json; print(json.dumps(clear_llm_for_ides(Path('PROJECT_ROOT'), ['WorkBuddy']), ensure_ascii=False, indent=2))"
```

这会写目标 IDE。WorkBuddy 的清除语义是删除 `~/.workbuddy/models.json`（不是写成空的官方对象）。`_delete_file` 遇到 `OSError` 会静默返回未清除。

清除会实际改文件的 IDE：`Claude`、`Codex`、`OpenCode`、`WorkBuddy`、`CodeBuddy`、`CherryStudio`、`Pi`、`OpenWorker`、`DeepSeek`、`Hermes`、`ZCode`。以下 IDE 会被跳过（飞翼不写其本地 LLM 文件，或可能与用户配置混在一起）：`Cursor`、`Cline`、`Copilot`、`KimiCode`、`KimiCLI`、`KimiWork`、`Trae`、`TraeCN`、`TraeSoloCN`、`Qoder`、`QoderCN`、`OpenClaw`、`IDEA`、`VSCode`、`CommandCode`、`Agents`。

## 默认路径（WorkBuddy）

- 活动配置：`~/.workbuddy/models.json`（macOS / Linux / Windows 用户主目录下的 `.workbuddy`）
- 飞翼写入的官方格式应为对象：`{"models": [{"id","name","vendor","apiKey","url", ...}]}`，不是裸数组
- `url` 对 OpenAI 兼容协议会补全为以 `/chat/completions` 结尾
- MCP：`~/.workbuddy/mcp.json`；Skills：`~/.workbuddy/skills/`
- 不要把 `Application Support/AgentBuddy/.workbuddy/`（或打包资源里的副本）当成 WorkBuddy 正在使用的配置

状态查询没有专用 CLI。只读做法：`agentctl provider` 看当前源；再直接读目标文件（先打码 `apiKey` / `api_key`）。也可用 API 的 `GET /api/ide/detect`、`GET /api/ui-state`、`GET /api/version`。

## 可复制示例（含 WorkBuddy）

只读查看当前 LLM 源：

```bash
agentctl provider
# 或打包版：
# "<AgentBuddy 可执行文件>" --run agentctl provider
```

同步 LLM 到 WorkBuddy（会覆盖已有 `models.json`，先备份）：

```bash
agentctl sync --ide WorkBuddy --force --scope llm
```

清除 WorkBuddy 上由飞翼写入的 LLM 文件（会删除 `~/.workbuddy/models.json`）：

```bash
python -c "from pathlib import Path; from agentctl.lib.ide.clear_llm import clear_llm_for_ides; print(clear_llm_for_ides(Path('PROJECT_ROOT'), ['WorkBuddy']))"
```

## 验证完整性（必须做）

目标：确认按**当前设定**替换，而不是在旧模型列表上追加。当前设定以 `PROJECT_ROOT/config/llm/llm.yaml` 为准：未启用的 provider（`_enabled: false`）应被跳过；模型级 `_enabled: false` 以及 `~` 前缀的 model id 也应被跳过。

1. **先退出 WorkBuddy**（它可能在启动时重写 `models.json`）。不要杀 AgentBuddy 进程。
2. **备份到用户家目录之外的临时目录**，例如 `/tmp/ab-wb-backup-<date>/` 或 Windows 的 `%TEMP%\ab-wb-backup-<date>\`。只备份配置文件，不要把备份内容粘进 skill 或报告。路径记下来告诉用户。
3. **记录同步前快照**（只记录结构，密钥打码）：文件是否存在、顶层类型（对象还是裸数组）、`models` 数量、id 列表、vendor、url、mtime。同时记录 llm.yaml 里 `_active_provider`、`_active_model`，以及各 provider / 模型的 `_enabled`。
4. **调用同步或清除**（仅在用户明确要求时）。同步必须带 `--force`，否则已存在的 `models.json` 会被跳过。清除后应看到文件被删除；若随后又同步，应出现新的官方格式文件。
5. **对比**：
   - 同步后应为 `{"models": [...]}`，而不是裸数组
   - `models` 的 id 集合应等于当前**启用**的模型，而不是 llm.yaml 里该 provider 的全部模型，更不应残留清除前的旧 id
   - 旧 id 被替换掉，而不是新旧并列
   - 清除后、且尚未再次同步、且 WorkBuddy 未重启时，`models.json` 应不存在
6. 如需确认应用层是否接受该文件，再启动 WorkBuddy，并立刻复读 `models.json`：若格式变回裸数组或模型列表被全量目录覆盖，说明应用在启动时重写了配置，问题不一定在 CLI 调用本身。

已知缺口（验证时要检查，本 skill 不负责改代码）：`generate_workbuddy_models` 目前只跳过未启用的 **provider** 和 `~` 前缀 id，**不读取模型级 `_enabled`**。对比对象若是「界面上勾选的模型」，WorkBuddy 可能仍被写成该 provider 的全量列表。Pi 等实现会走 `_enabled_models`，行为不一致。

## 密钥与安全

- 不要把 `apiKey`、`api_key`、token、密码写入 skill、聊天或报告正文。需要对比时只保留前后缀与长度。
- 备份目录同样含密钥，不要提交、不要推送、不要发到群里。
- 不要对用户真实 WorkBuddy 配置做清除或同步，除非用户明确要求；默认只读。
