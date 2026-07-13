---
description: 编写后端代码、API 接口、数据库操作、服务端逻辑、中间件、后端测试时使用此规则
globs: **/*.java,**/*.py,**/*.go,**/*.ts,**/*.js,**/*.sql,**/*.yml,**/*.yaml
alwaysApply: false
---

# 后端编码规范

## 1. API 设计

### RESTful 资源建模
- URL 使用名词复数形式：`/api/users`、`/api/orders`
- 资源关系通过 URL 层级表达：`/api/users/{id}/orders`
- 使用 HTTP 方法表达操作：GET（查询）、POST（创建）、PUT（全量更新）、PATCH（部分更新）、DELETE（删除）
- 避免动词出现在 URL 中，动作通过 HTTP 方法表达

### 状态码规范

| 状态码 | 场景 |
|--------|------|
| 200 | 请求成功 |
| 201 | 创建成功 |
| 204 | 删除成功（无返回体） |
| 400 | 参数校验失败 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如重复创建） |
| 422 | 请求格式正确但语义错误 |
| 500 | 服务器内部错误 |

### 统一响应结构
```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

### 错误响应结构
```json
{
  "code": 40001,
  "message": "参数校验失败",
  "errors": [
    { "field": "email", "message": "邮箱格式不正确" }
  ]
}
```

## 2. 分页、过滤、排序

### 分页
- 统一使用 `page`（页码，从 1 开始）和 `pageSize`（每页条数，默认 20，最大 100）
- 响应中包含 `total`（总数）、`page`、`pageSize`、`list`

### 过滤
- 查询参数直接使用字段名：`?status=active&role=admin`
- 范围查询使用 `_gte`、`_lte` 后缀：`?createdAt_gte=2024-01-01`

### 排序
- 使用 `sortBy` 和 `sortOrder`（asc/desc）
- 默认按创建时间倒序

## 3. 鉴权与安全

- 所有非公开接口必须验证 Token
- Token 通过 Authorization Header 传递：`Bearer <token>`
- 敏感操作（删除、权限变更）需二次校验权限
- 输入必须做参数校验，防止 SQL 注入、XSS
- 不在日志中记录密码、Token 等敏感信息
- 不在代码中硬编码密钥、密码

## 4. 数据库

- 表名使用 snake_case 复数形式
- 字段名使用 snake_case
- 必须包含 `id`、`created_at`、`updated_at` 字段
- 软删除使用 `deleted_at` 字段
- 外键命名：`{关联表单数名}_id`
- 索引命名：`idx_{表名}_{字段名}`

## 5. 代码组织

### 分层结构
```
src/
├── controller/    # 控制器层，处理请求参数校验与响应
├── service/       # 服务层，核心业务逻辑
├── repository/    # 数据访问层，数据库操作
├── model/         # 数据模型/实体
├── middleware/    # 中间件（鉴权、日志、限流等）
├── dto/           # 数据传输对象
├── utils/         # 工具函数
└── config/        # 配置文件
```

### 命名规范
- 类名：PascalCase
- 方法/函数：camelCase
- 常量：UPPER_SNAKE_CASE
- 文件名与主要导出类名一致

## 6. 错误处理与日志

- 业务异常使用自定义异常类，包含错误码和错误信息
- 全局异常拦截器统一处理未捕获异常
- 日志分级：DEBUG、INFO、WARN、ERROR
- 关键操作（登录、支付、权限变更）必须记录日志
- 日志包含：时间、操作人、操作类型、关键参数、结果

## 7. 测试

- 核心业务逻辑必须有单元测试
- API 接口必须有集成测试
- 测试覆盖正常流程、边界条件、异常情况
- 测试数据与生产数据隔离
