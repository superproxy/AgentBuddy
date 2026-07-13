---
scene: git_message
---

# Git 提交规范

## 提交信息格式

采用 Conventional Commits 规范，格式如下：

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Type 类型

| Type | 说明 |
|------|------|
| feat | 新功能 |
| fix | 修复 Bug |
| docs | 文档变更 |
| style | 代码格式（不影响代码运行的变动） |
| refactor | 重构（既不是新增功能，也不是修复 Bug） |
| perf | 性能优化 |
| test | 增加测试 |
| chore | 构建过程或辅助工具的变动 |
| ci | CI/CD 配置变更 |
| build | 构建系统或外部依赖变更 |
| revert | 回滚提交 |

## 规则

1. subject 使用中文描述，不超过 50 个字符，不以句号结尾
2. subject 使用祈使句，如"添加"而非"添加了"
3. body 与 subject 之间空一行
4. body 使用中文详细描述变更原因、内容和影响
5. 每次提交应聚焦单一变更，避免混合无关改动
6. 涉及敏感信息（Token、密钥、密码等）的变更不得提交
7. 提交前确保代码通过 lint 检查
8. 禁止提交调试代码、临时文件、本地配置文件

## 示例

```
feat(用户模块): 添加手机号验证码登录功能

- 新增 /api/auth/sms/send 发送验证码接口
- 新增 /api/auth/sms/login 验证码登录接口
- 60 秒内同一手机号不可重复发送
- 验证码 5 分钟内有效

Closes #123
```

```
fix(订单模块): 修复并发下单导致库存超卖的问题

- 添加数据库行级锁
- 下单前二次校验库存

Closes #456
```
