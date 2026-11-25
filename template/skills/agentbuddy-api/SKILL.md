---
name: agentbuddy-api
description: >-
  用 AgentBuddy / 飞翼桌面后端的 HTTP API 查询、同步或清除各 IDE 的 LLM 配置，并验证 WorkBuddy
  等目标配置是按当前设定被替换而不是追加。当用户要用 curl/API 测试同步与清除、排查界面同步未生效，或对照 CLI
  做完整性验证时使用。不要调用会写配置的接口，除非用户明确要求。不要把密钥写入报告。
---
# AgentBuddy 桌面后端 API

桌面应用在本机起 Flask 后端，把 `agentctl` 和清除逻辑暴露为 HTTP。本 skill 说明如何用 HTTP 做与 CLI 同等的查询 / 同步 / 清除，以及如何验证完整性。不要写死某台机器的路径、端口以外的环境细节，或某人账号。

## 何时使用

- 要用 curl 或脚本验证同步、清除、IDE 检测
- 界面显示成功但目标 IDE 配置看起来没变
- 需要对照 CLI skill（`agentbuddy-cli`）走同一套完整性步骤

默认只读。没有用户明确授权时，不要调用下面标为「会写 IDE」的接口。

## 基址与版本

- 打包版默认：`http://127.0.0.1:5050`（启动器也可 `--port` 覆盖）
- 源码开发通常同样是 5050；先 `GET /api/version` 确认进程还在，不要重启或杀死已在跑的 AgentBuddy
- 这些是本机桌面 API，一般无需登录 token。`Authorization: Bearer` 主要用于远程市场/服务器，不用于本机同步
- 成功响应多为 `{ok: true, ...}`；失败为非 200 且 `{ok: false, error}`
- `GET /api/sync` 返回 SSE（`text/event-stream`），不是普通 JSON

先确认版本（只读）：

```bash
curl -sS http://127.0.0.1:5050/api/version
```

返回示例：`{"version":"3.22.4","build_time":"..."}`。`/api/llm/clear-sync` 与「只同步勾选 IDE」需要较新的桌面后端；若 404，说明运行中的包可能偏旧。

## 与同步 / 清除 / LLM / IDE 检测相关的接口

| 方法 | 路径 | 请求 | 响应要点 | 是否写 IDE |
| --- | --- | --- | --- | --- |
| GET | `/api/version` | 无 | `{version, build_time}` | 否 |
| GET | `/api/ui-state` | 无 | 含 `ideSyncTargets`（同步栏勾选的 IDE key 列表）、`autoSync` 等 | 否 |
| POST | `/api/ui-state` | JSON 状态对象 | 保存界面状态 | 否（只改飞翼 UI 状态，但会影响之后静默同步的目标） |
| GET | `/api/ide/detect` | 无 | `{ok, ides:[{key,label,installed,exe_path,app_path,version,config_paths}], stats}`。WorkBuddy 的 `config_paths` 一般为 `~/.workbuddy` | 否 |
| GET | `/api/ide/install-info` | 无 | 安装说明 | 否 |
| GET | `/api/llm` | 无 | `{ok, data, path}`，`data` 为完整 llm.yaml。**可能因旧 `llm.proxy` 迁移或 env 占位符迁移而写回 llm.yaml**，不要在「纯只读」排查里随手打 | 不写 IDE，但可能改飞翼自己的 llm.yaml |
| POST | `/api/llm` | `{"data": {完整 llm 配置}}` | 保存后对勾选 IDE 自动 `sync --force --scope llm,mcp`；未勾选则只 `generate` | **会写勾选 IDE** |
| GET | `/api/llm/catalog` | 无 | 模板里的 provider catalog | 否 |
| GET | `/api/llm/env-vars` | 无 | 已声明的环境变量名（不要把值记进报告） | 否 |
| POST | `/api/llm/verify` | 含 provider/协议信息 | 探测模型列表或校验 key | 否，但会把 key 发到对应厂商 |
| POST | `/api/llm/detect` | `{api_key, base_url?, probe?}` | 推断厂商与协议 | 否，但请求里有密钥 |
| POST | `/api/llm/apply` | `{api_key, provider, ...}` | 写入 llm.yaml | 可能间接触发后续保存/同步，视为写配置 |
| GET | `/api/sync` | Query：`ide`（默认 `All`）、`scope`（默认 `llm,mcp,skill,plugin`）、可选 `skills` | SSE 文本流，内部执行 `agentctl sync --ide <ide> --force --scope <scope>` | **会写 IDE**。尽管是 GET，也绝不能当作只读 |
| POST | `/api/sync` | 无 body（目标取自 `ui-state.ideSyncTargets`） | `{ok, ides, generated, stdout}`。先 `generate`，再对勾选 IDE 执行 `sync --force --scope llm,mcp`。未勾选则只 generate | **会写勾选 IDE** |
| POST | `/api/llm/clear-sync` | `{"ides":["WorkBuddy","Pi"]}`；也可 `"ide":"WorkBuddy"`；省略则用当前勾选 | `{ok, ides:[{key,cleared:[path],skipped,hint?}], cleared_count, count}`。不改 llm.yaml，不动 MCP/Skills。不支持 `All` | **会改目标 IDE 的 LLM 文件**。WorkBuddy 是删除 `~/.workbuddy/models.json` |
| GET | `/api/keys` | 无 | 密钥表 | 否，但响应含密钥，输出必须打码 |
| POST | `/api/ide/open-config` 等 | 打开/安装/启动 IDE | 视接口而定 | 可能打开应用或改安装，不是同步 LLM；本 skill 不做这些 |

其它 `/api/rules/sync`、`/api/hooks/sync`、`/api/memory/sync`、`/api/cmd/sync`、`/api/subagent/sync` 也会写对应 IDE 配置，但不属于 LLM 同步。`GET /api/proxy/start`、`GET /api/proxy/stop` 会启停本机网关。

同步栏勾选来自 `ui-state.ideSyncTargets`。界面上的「点击同步」（LLM 页）走的是 **GET** `/api/sync?ide=<key>&scope=llm`（逐个勾选的 IDE，SSE）。「清除设置」走 **POST** `/api/llm/clear-sync`，body 为当前勾选列表。

## 可复制的 curl 示例

只读：版本、勾选目标、WorkBuddy 是否被检测到（不调用 `/api/llm`，避免潜在写回）：

```bash
curl -sS http://127.0.0.1:5050/api/version
curl -sS http://127.0.0.1:5050/api/ui-state
curl -sS http://127.0.0.1:5050/api/ide/detect
```

同步 LLM 到 WorkBuddy（会写配置；先备份。`-N` 关闭 SSE 缓冲）：

```bash
curl -sSN "http://127.0.0.1:5050/api/sync?ide=WorkBuddy&scope=llm"
```

按当前勾选做静默同步（scope 固定为 `llm,mcp`）：

```bash
curl -sS -X POST http://127.0.0.1:5050/api/sync
```

清除 WorkBuddy（以及需要时的其它 IDE）已同步 LLM 设置：

```bash
curl -sS -X POST http://127.0.0.1:5050/api/llm/clear-sync \
  -H "Content-Type: application/json" \
  -d '{"ides":["WorkBuddy"]}'
```

PowerShell 5 不要用 `$_`、`\"` 或 `&&`。可用 `py -3` 发请求，或把 JSON 放进文件再用 `curl --data-binary "@body.json"`。

## 验证完整性（必须做）

与 CLI skill 同一套标准：备份 → 同步前快照 → 调用同步或清除 → 对比目标 IDE（尤其 WorkBuddy）是按当前设定替换，而不是追加。

1. **先退出 WorkBuddy**，再操作。WorkBuddy 启动时可能重写 `~/.workbuddy/models.json`。不要杀死正在跑的 AgentBuddy。
2. **备份** `~/.workbuddy/models.json`（若存在）到用户家目录之外的临时目录，并记录备份路径。不要把文件内容（含 apiKey）贴进报告。
3. **快照**：`GET /api/ui-state` 看 `ideSyncTargets`；`GET /api/ide/detect` 确认 WorkBuddy 的 `config_paths`；只读打开 `models.json` 记录顶层类型、模型 id 列表、mtime。当前设定以 `PROJECT_ROOT/config/llm/llm.yaml` 为准（打包版 macOS 在 `~/Library/Application Support/AgentBuddy/config/llm/llm.yaml`）：记下启用的 provider 与模型级 `_enabled: true` 的 id。尽量不要用 `GET /api/llm` 做「纯只读」快照。
4. **调用**（仅当用户明确要求）：清除用 `POST /api/llm/clear-sync`；同步用 `GET /api/sync?ide=WorkBuddy&scope=llm`。界面若在清除后立刻再点同步，文件会被重建，不能单独用来判断「清除是否生效」。
5. **对比**：
   - 看 SSE / JSON 是否 `ok`，`clear-sync` 的 `ides[].cleared` 是否包含 `models.json` 的路径，`skipped` 是否为 false。`cleared_count` 为 0 表示没删到文件（文件本就不在，或删除时发生 `OSError` 被吞掉）
   - 清除后、尚未再次同步、WorkBuddy 未重启：`models.json` 应消失
   - 同步后文件应为 `{"models":[...]}`，id 集合应等于当前启用的模型，旧 id 应消失而不是仍堆在列表里
6. 再启动 WorkBuddy 并立刻复读该文件。若变回裸数组或模型又变成全量目录，说明是应用启动重写，而不是 API 没执行。

已知缺口（验证时检查，不要在本 skill 流程里改代码）：WorkBuddy 的生成器目前不按模型级 `_enabled` 过滤，可能把该 provider 的全部模型都写进去；同时 WorkBuddy 进程可能在启动时把文件改回它自己的裸数组目录。API 层对 WorkBuddy 的同步已带 `--force`，与「文件已存在被跳过」不是同一类问题。

## 密钥与安全

- `/api/llm`、`/api/keys`、目标 IDE 的 `models.json` 都可能含密钥。报告里只保留前后缀与长度，不要转储。
- 不要把 key 写进 skill、日志或备份说明正文。
- `GET /api/sync` 会写配置；把它当只读是错误的。
