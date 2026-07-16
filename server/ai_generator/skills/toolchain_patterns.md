# Skill: 常见工具链模式

## 概述
根据不同的开发场景，以下是常见的工具链组合模式。生成插件时参考这些模式，选择最匹配的组合。

## 1. 全栈 Web 开发

**适用场景**：前后端一体化项目，需要前后端协作

| 资源类型 | 推荐配置 |
|---|---|
| Skills | frontend-design + backend-patterns + testing + code-review |
| MCP | filesystem + web-search |
| Subagents | frontend-dev + java-dev + dev |
| Rules | frontend/coding + backend/coding + testing + security |
| Commands | commit + review + test + docs |

**协作链路**：需求分析 → 前端设计 → 后端 API → 联调测试 → 代码审查 → 提交

## 2. API 服务开发

**适用场景**：后端 API 服务，RESTful 设计

| 资源类型 | 推荐配置 |
|---|---|
| Skills | api-design + backend-patterns + security + testing |
| MCP | filesystem |
| Subagents | java-dev + dev |
| Rules | backend/coding + backend/database + backend/ddd + api/collaboration |
| Commands | commit + review + test |

**协作链路**：需求 → API 设计 → 数据库建模 → 实现 → 测试 → 审查

## 3. 前端专项开发

**适用场景**：纯前端项目，UI/UX 为主

| 资源类型 | 推荐配置 |
|---|---|
| Skills | frontend-design + ui-ux-pro-max + testing + code-review |
| MCP | filesystem + playwright（浏览器测试） |
| Subagents | frontend-dev |
| Rules | frontend/coding + design + testing |
| Commands | commit + review + test + docs |

**协作链路**：UI 设计 → 组件开发 → 交互测试 → 代码审查 → 提交

## 4. 嵌入式开发

**适用场景**：嵌入式系统，C/RTOS/硬件驱动

| 资源类型 | 推荐配置 |
|---|---|
| Skills | embedded-patterns + testing + code-review |
| MCP | filesystem |
| Subagents | embedded-dev |
| Rules | backend/coding + testing + security |
| Commands | commit + review + test |

**协作链路**：需求 → 硬件接口设计 → 驱动开发 → 交叉编译 → 测试

## 5. 产品+开发协作

**适用场景**：产品经理与开发团队协作

| 资源类型 | 推荐配置 |
|---|---|
| Skills | prd-to-code + api-design + testing + code-review |
| MCP | filesystem + web-search |
| Subagents | product + java-dev + frontend-dev |
| Rules | product/prd + backend/coding + api/collaboration |
| Commands | commit + review + docs |

**协作链路**：需求分析 → PRD 编写 → 任务拆解 → 开发实现 → 审查验收

## 6. 安全审计

**适用场景**：代码安全审查与漏洞修复

| 资源类型 | 推荐配置 |
|---|---|
| Skills | security-and-hardening + code-review + testing |
| MCP | filesystem |
| Subagents | dev |
| Rules | security + backend/coding + testing |
| Commands | review + test |

**协作链路**：代码扫描 → 漏洞识别 → 修复方案 → 代码审查 → 测试验证

## 7. DevOps/CI-CD

**适用场景**：持续集成、自动化部署

| 资源类型 | 推荐配置 |
|---|---|
| Skills | ci-cd-and-automation + shipping-and-launch |
| MCP | filesystem |
| Subagents | dev |
| Rules | backend/coding + security |
| Commands | commit + docs |
| Hooks | true（启用自动化） |

**协作链路**：构建脚本 → CI 配置 → 部署流程 → 监控告警

## 8. 数据库设计与优化

**适用场景**：数据库建模、性能优化

| 资源类型 | 推荐配置 |
|---|---|
| Skills | domain-modeling + backend-patterns |
| MCP | filesystem + 数据库 MCP（如 postgres） |
| Subagents | java-dev + dev |
| Rules | backend/database + backend/coding |
| Commands | review + test |

## 工具链选择指南

1. **根据用户需求关键词匹配**：提到 "前端/vue/react" → 前端专项模式
2. **组合多个模式**：如"全栈+安全审计"可组合模式1和模式6
3. **按级别调整密度**：basic 模式减少资源数，expert 模式增加
4. **MCP 按需选择**：不要默认添加，只在用户需求或场景需要时
5. **优先复用本地资源**：先从本地 Skills/MCP 中选择，再考虑外部市场
