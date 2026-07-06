# 协同工作区

本目录是多角色协同的"当前状态"中枢，回答"现在做到哪了"。

## 文件职责
| 文件 | 职责 |
|---|---|
| `progress.yaml` | 全局进度看板（工作流状态、角色队列、阻塞项、里程碑） |
| `sync-log.md` | 操作时间线日志 |
| `handoffs/` | 角色间交接记录（未确认阻塞后续） |
| `experience-summary.md` | 跨角色经验总结（桥梁，大周期从 evolution/ 提炼） |

## 与 evolution/ 的边界
- `sync/` = 当前状态（进度、日志、交接）—— 回答"现在做到哪了"
- `evolution/` = 历史沉淀（经验、模式、变更）—— 回答"过去学到什么"
- 边界模糊时优先归 evolution/lessons-learned.md，大周期再升华

## 维护规则
- 每次节点切换追加 sync-log.md
- 每次角色交接生成 handoffs/ 记录
- 每次状态变更更新 progress.yaml
- 大周期时提炼 experience-summary.md
