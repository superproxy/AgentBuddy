# AdeBuddy — 智能体构建与分发平台

- **项目定位**：AI 智能体构建与分发平台 — 可视化构建智能体配置（LLM / MCP / Skills / Rules / Commands / Subagents / Hooks），通过插件化打包分发，一键同步到多 IDE
- **技术栈**：Python 3 + Flask + pywebview + PyInstaller（桌面应用）+ Vue 3 + Vite（前端）
- **核心能力**：
  - **智能体构建**：LLM Provider、MCP 服务、Skills、Rules、Commands、Subagents、Hooks 的可视化编辑与组合
  - **插件分发**：插件打包（zip 含 yaml + skills + llm key + rules + commands + subagents + hooks）→ 导入导出 → 跨团队共享
  - **多 IDE 同步**：一键同步到 ZCode / Trae / OpenCode / Claude / Cursor / Codex / OpenClaw / WorkBuddy 等 IDE
  - **桌面应用**：pywebview 桌面版，无需部署服务端，本地运行
- **主要业务流程**：智能体构建 → 插件打包 → 分发导入 → 同步多 IDE

> 原 AGENTS.md（仓库级治理文档）已备份为 `AGENTS.old.md`，含业务角色路由 / Rules / MCP / Skills 矩阵。

## 文档导航

| 文档 | 内容 |
|---|---|
| [docs/project-overview.md](docs/project-overview.md) | 项目定位、项目结构、Skill 目录体系（三源）、插件导入导出 |
| [docs/build-release.md](docs/build-release.md) | 发布流程（Release）、安装更新（升级覆盖）、Windows 批处理脚本规范 |
| [docs/agent-governance.md](docs/agent-governance.md) | Agent 架构拓扑、协作流程、治理规则、FAQ/最佳实践、自我迭代、协同进度、Skill 依赖表、通信协议 |
