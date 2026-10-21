# 协同操作时间线日志

> 按时间倒序追加，每条记录角色操作。格式：`[时间] [角色] [操作类型] [工作流ID] 详情`

| 时间 | 角色 | 操作类型 | 工流 | 详情 |
|---|---|---|---|---|
| 2026-10-21 | executor | fix+release | market-skill-001 | **v3.22.3**：服务端打包 `SKILL.md` 补 YAML frontmatter（7f43226）；市场 zip 根目录 `plugin.yaml` 可导入为 `config/plugins/*.plugin.yaml`；导入时 legacy SKILL 补 frontmatter 并写入 `skill.yaml` enabled；split 包改为 `{name}.plugin.yaml`。**验证**：`pytest tests/test_plugin_market_zip_import.py` + server article_to_plugin；市场重装插件后 SyncBar scope=skill 同步 Cursor。 |
| 2026-10-21 | executor | fix+rule | sync-bar-sse-001 | **v3.22.1 后续**：SyncBar「点击同步」在 SSE 正常 `[DONE]` 后仍触发 `EventSource.onerror`，被误判「连接中断」并抛出未捕获异常。**修复**：`api/sse.ts` 忽略 DONE 后的 onerror；`SyncBar` 增加 catch + LLM 校验读配置失败提示。**同期交付**：插件市场详情/原文地址（v3.22.0）、LLM verify keys.yaml/latin-1（v3.22.1）、同步栏「同步到 AIDE」文案与 detect 名称对齐。**验证**：Flask `/api/sync?ide=Pi&scope=llm` SSE 见 returncode=0；浏览器 LLM 页勾选 AIDE 后同步 toast。**规则**：AGENTS.md §12 + Cursor `task-flow.mdc` 补充界面必测与本文档追加日志。 |
| 2026-07-06T00:00 | retro-optimizer | init | harness-init-001 | Harness 框架初始化完成 |
| 2026-07-06T00:01 | reviewer | review | harness-init-001 | 第三次触发合并增强：10 项自洽性检查通过，修复 executor.md + AGENTS.md Skill 表 2 处不一致 |
| 2026-07-06T00:02 | devops | commit | harness-init-001 | 提交 Harness 全套配置 + LLM 4 渠道配置 |
