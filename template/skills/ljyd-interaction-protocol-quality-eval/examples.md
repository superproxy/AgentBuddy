# 示例：ljyd《播放器方案》规范检查报告

> 评估对象：语雀文档《播放器方案》  
> URL：`https://xjiangiot.yuque.com/afahpl/project_doc/mk7ups3a03nuwrsw`  
> slug：`mk7ups3a03nuwrsw`（1321 字，含 1 个 sequenceDiagram + 多个 HTTP/MQTT 接口定义）  
> 对照基线：语雀《资源管理流程》（`owg3sv8eodzqkcq4`）

## 1. 评估概况
- 总分：**54.5 / 100**　等级：**E（不合格）**
- 重大缺陷数：**4**

## 2. 维度评分明细

| 维度 | 权重 | 得分 | 加权 | 等级 | 结论 |
|------|------|------|------|------|------|
| 1 流程逻辑合理性 | 20% | 65 | 13.0 | C | 起止连贯，缺异常分支与状态反馈环节 |
| 2 命名规范合理性 | 15% | 50 | 7.5 | E | participant/字段/topic 三套命名混用 |
| 3 格式规范 | 10% | 55 | 5.5 | D | 层级跳跃、JSON 多处语法错误 |
| 4 HTTP/MQTT 双接口一致性 | 15% | 55 | 8.25 | D | 3 个接口缺 HTTP 版（重大缺陷封顶 C）|
| 5 接口设计规范性 | 15% | 50 | 7.5 | E | 缺通用协议头/Header/公共结构体/错误码 |
| 6 生命（状态）管理整齐性 | 10% | 45 | 4.5 | E | 三套状态定义不一致、无状态机图 |
| 7 场景支持全面性 | 15% | 55 | 8.25 | D | 正常场景覆盖，异常/边界/多端协同缺失 |

## 3. 重大缺陷（必须修正）

1. **[双通道缺失]** 「基于 iot-mq 播放控制协议」「获取播放器状态」「设备主动上报状态」3 个接口仅给出 MQTT 版，无 HTTP 对应版。按基线"每接口双通道并存"要求，触发的维度 4 直接封顶 C。
2. **[JSON 语法错误]** MQTT payload 多处 JSON 非法：
   - `"subMethod":"play|stop|...","//播放..."` —— JSON 不支持 `//` 注释
   - `"resourceBundleName": "xx"` 后缺逗号、`"totalDuration":"..."` 后缺逗号、`"type":"audio",` 末尾多余逗号
   - `"code":0` 后缺逗号（播放反馈/上报响应）
3. **[状态定义三套并存且不一致]** 同一播放器状态在不同接口用三种表达：
   - `playState`（数字 1=开始/2=暂停/3=继续，远程暂停播放协议）
   - `playStatus`（字符串 playing/stopped/paused，获取播放器状态）
   - `subMethod`（动词 play/stop/pause/resume/next/prev，播放控制）
   - "停止"在 playState 无对应、在 playStatus 是 stopped、在 subMethod 是 stop；"继续"在 playState=3、在 subMethod=resume。状态集合不对齐，无法闭环。
4. **[无状态机图]** 播放器有 playing/stopped/paused 等多状态及切换，但全文无 `stateDiagram-v2`，状态迁移条件与终态未可视化。

## 4. 各维度问题与修正建议

### 维度 1 流程逻辑合理性（得分 65）
- [缺陷] 流程图末尾（步骤 11 播放）后无"设备上报播放状态/完成"环节，但文档后续有"设备主动上报状态"接口 → 建议在 sequenceDiagram 增补 `Device->>MQTT: 12. 上报播放状态` 与 `MQTT->>Server: 13. 平台更新状态` 两条消息，与接口呼应。
- [缺陷] 无异常分支：上传失败、OSS 失败、下载失败、播放失败均未用 `alt`/`opt` 体现 → 建议对步骤 2/3/9/11 各加 `alt 失败` 分支与回滚/重试路径。
- [警告] 未使用 `autonumber`，步骤序号靠手写"1. 2. ..."维护易漂移 → 加 `autonumber` 后去掉标签前缀数字。

### 维度 2 命名规范合理性（得分 50）
- [缺陷] `participant App/Applet` 含斜杠，作为 participant Id 不合法（Mermaid 推荐 Id 仅字母数字下划线）→ 改为 `participant AppApplet as App/Applet`。
- [缺陷] 接口路径 `/api/agora/sendEvent`、`/api/agora/sendCustomEvent` 用 `agora`（声网）命名，与"播放器/资源"业务语义不符，疑似复用通道未重命名 → 建议迁到 `/api/player/sendEvent` 或加业务前缀。
- [缺陷] 控制字段三套命名混用：HTTP 用 `event=play_music`（下划线）、MQTT 早期用 `method:"set"/"playState"`、MQTT 后期用 `method:"player"+subMethod:"play"` → 全篇统一为 `method:"player"+subMethod:<动作>` 一套。
- [缺陷] MQTT topic 三套风格并存：`/pid/did/cloud/set`、`/$pid/$did/device/down`、`/$did/device/up`（最后者缺 `$pid`）→ 统一为 `/$pid/$did/device/{up|down}`，`cloud/set` 风格废弃或明确映射。
- [缺陷] 属性 key 大小写不一：`FileUrl`（大驼峰）vs `playState`（小驼峰）→ 统一小驼峰。
- [警告] `playState` 与 `playStatus` 两字段名相近表达同一语义 → 合并为一个字段名。

### 维度 3 格式规范（得分 55）
- [缺陷] 标题层级跳跃与编号缺失：`# 资源远程控制` → `## 远程播放` → `### 流程`，但 `# 基于 iot-mq 下发 url 的资源播放控制协议` 后直接 `### 播放控制`（跳过 `##`）；全篇无"1.1/1.2/2.1"编号，与基线不一致 → 补层级编号，统一为 `# 1 资源远程控制` → `## 1.1 远程播放` → `### 1.1.1 流程`。
- [缺陷] JSON 示例多处语法错误（见重大缺陷 2）→ 用 JSON 校验器过一遍，移除 `//` 注释与 `#字节` 注释，补齐缺逗号、删除多余逗号。
- [警告] 内联样式标签 `<span textColor=...>` 残留为语雀产物 → 转纯文本。
- [警告] 请求地址前有 `\t` 制表符 → 去除。

### 维度 4 HTTP/MQTT 双接口一致性（得分 55，重大缺陷封顶 C）
- [缺陷] 3 个接口缺 HTTP 版（见重大缺陷 1）→ 补 HTTP 对应接口，或明确说明该接口仅 MQTT 通道并给出理由。
- [缺陷] 已有双通道的业务内容不一致：
  - 播放音乐：HTTP `content=2001`（数字 id）vs MQTT `value={resourceId,title,url}`（对象）→ 统一为对象结构，HTTP 用 `content=<json>` 或改 POST body。
  - 暂停：HTTP `event=stop_music`（停止）vs MQTT `playState=2`（暂停）→ "停止"与"暂停"语义不对齐，需先统一状态枚举。
- [缺陷] MQTT 顶层封装前后不一：早期 `method/id/params/code`（无 ok/msg/timestamp），后期 `method/subMethod/id/params/code` → 统一为 `method/subMethod/id/code/params/ok/msg/timestamp`，与 HTTP 顶层对齐。
- [缺陷] 无 Topic 与 HTTP 路径的映射表 → 增补映射表（如 `/api/player/play` ↔ `/$pid/$did/device/down` method=player subMethod=play）。

### 维度 5 接口设计规范性（得分 50）
- [缺陷] 缺"通用协议头规范"章节（基线有"1 通用协议头规范"含请求方式/编码/传输格式/多环境域名）→ 补一节通用规范。
- [缺陷] HTTP 接口缺 Header 说明（无 `Authorization: Bearer {token}`、`Content-Type`）→ 补"请求 Header（必传）"表。
- [缺陷] MQTT 响应缺通用顶层字段：仅 `code/params`，缺 `msg/ok/timestamp` → 与 HTTP 顶层 `msg/status/ok/timestamp/result` 对齐（MQTT 用 `code` 替代 `status` 需在映射表说明等价关系）。
- [缺陷] 无公共结构体抽离：资源字段（`resourceBundleName/resourceId/title/description/url/fileSize/fileSign/type/totalDuration`）在"播放控制""获取播放器状态""设备主动上报状态"三处重复 → 抽为 `ResourceItem` 公共结构体（对齐基线 `CategoryItem` 范式）。
- [缺陷] HTTP 接口缺"请求参数表"（参数名/类型/是否必填/说明），仅一行 `query：pid、did、event、content` → 改为标准四列表。
- [缺陷] `siid=9` 在两处服务名不一：远程播放协议为 `resource`，远程暂停协议为 `playControl` → 同一 siid 应对应唯一服务名。
- [缺陷] 字段表不全：播放控制 payload 实际含 `resourceBundleName/resourceId/duration/currentPos/volume/playSpeed`，但字段表未列出 → 补全。
- [缺陷] 无错误码表 → 补 `code` 非 0 的错误码表。

### 维度 6 生命（状态）管理整齐合理性（得分 45）
- [缺陷] 三套状态定义并存（见重大缺陷 3）→ 全篇统一为一套，建议用字符串 `playing/stopped/paused`（语义清晰），数字枚举作为代码侧映射。
- [缺陷] 无状态机图 → 补 `stateDiagram-v2`，含 `idle → playing → paused → playing → stopped` 等迁移及触发条件（play/pause/resume/stop/next/prev）。
- [缺陷] 状态字段不闭环：控制下发用 `playState`（数字），状态上报用 `playStatus`（字符串），二者无法直接对应 → 统一字段名与取值类型。
- [警告] `playState=3 继续` 无前置"暂停"状态的显式关联 → 在状态机图中标注 `paused → playing : resume`。

### 维度 7 场景支持全面性（得分 55）
- [缺陷] 异常场景全缺：上传失败、OSS 失败、下载失败、播放失败、网络中断、鉴权失败 → 至少在流程图与接口中给出失败响应码与重试策略。
- [缺陷] 边界场景缺：空列表、并发控制（多端同时下发指令）、超时、资源不存在 → 补并发冲突处理（如基于 `id` 的请求去重）与超时约定。
- [缺陷] "上一首/下一首"：`subMethod` 有 `next/prev` 但流程图未体现 → 补获取播放器状态后再下发的流程。
- [缺陷] "单曲播放和合集播放"：文末提及但无流程/接口支撑 → 明确合集播放的列表下发与单曲切换接口。
- [缺陷] "多端协同"（小程序切换→语控→设备同步）：仅文字描述，无流程 → 补多端状态同步 sequenceDiagram。
- [警告] 无资源变更查询/增量同步场景 → 评估是否需要（基线有"核心流程（增加资源变更查询）"）。
- [警告] 未区分外部/内部资源（基线有区分）→ 评估播放器场景是否需要。

## 5. 待确认项
- 「基于 iot-mq 播放控制协议」「获取播放器状态」「设备主动上报状态」是否计划补 HTTP 版？若仅 MQTT 通道，请说明业务理由（如设备单向上报无需 HTTP）。
- `playState`（数字）与 `playStatus`（字符串）是否为同一状态的不同表达？目标统一为哪一套？
- HTTP `content=2001` 与 MQTT `value.resourceId` 的映射关系？是否需要 HTTP 也改为对象结构？
- `siid=9` 服务名 `resource` 与 `playControl` 哪个为准？
- `/api/agora/*` 路径是否保留（声网通道复用）还是迁移到 `/api/player/*`？

## 6. 总体结论与优先修正顺序

1. **修正 JSON 语法错误**（最快，阻塞接口落地）——移除注释、补齐逗号。
2. **统一状态定义**（影响最大）——一套 `playStatus` 字符串枚举 + 状态机图。
3. **补 HTTP 双通道**（消除重大缺陷）——3 个仅 MQTT 的接口补 HTTP 版或说明理由。
4. **抽离 `ResourceItem` 公共结构体**（消除重复）——三处资源字段合并。
5. **统一 MQTT topic 与 method 命名**——废弃 `cloud/set`，全用 `/$pid/$did/device/{up|down}` + `method:"player"`。
6. **补通用协议头规范与错误码表**——对齐基线接口设计规范。
7. **补异常分支与多端协同流程图**——完善场景覆盖。
8. **补层级编号与 `autonumber`**——格式规范化。
