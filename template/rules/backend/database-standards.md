---
description: 进行数据库表设计、字段定义、索引规划、SQL 编写、数据迁移、数据库性能优化时使用此规则
globs: **/*.sql,**/*.ddl,**/*.dml,**/*.prisma,**/*.entity.ts,**/*.entity.java,**/models.py,**/migrations/**
alwaysApply: false
---

# 数据库设计规范

## 1. 命名规范

### 通用规则
- 所有数据库对象名称使用 **snake_case** 小写 + 下划线
- 名称简洁且具有描述性，避免缩写（除非是广泛认可的缩写如 `id`、`url`）
- 禁止使用数据库保留字作为名称
- 名称长度不超过 63 字符（兼容不同数据库）

### 表命名
- 使用**复数形式**名词：`users`、`orders`、`order_items`
- 关联表命名：`{表A}_{表B}`，按字母顺序排列：`user_roles`
- 前缀约定（按模块）：如 `sys_`（系统）、`biz_`（业务）、`log_`（日志）

### 字段命名
- 主键统一使用 `id`
- 外键命名：`{关联表单数名}_id`，如 `user_id`、`order_id`
- 布尔字段使用 `is_` 前缀：`is_active`、`is_deleted`
- 时间字段：`created_at`、`updated_at`、`deleted_at`
- 状态字段：`status`，枚举值在代码/注释中说明
- 数量字段：`count`、`total_count`
- 金额字段：`amount`、`total_amount`，使用 `DECIMAL` 类型

### 索引命名
| 索引类型 | 命名格式 | 示例 |
|----------|----------|------|
| 主键 | `pk_{表名}` | `pk_users` |
| 唯一索引 | `uk_{表名}_{字段名}` | `uk_users_email` |
| 普通索引 | `idx_{表名}_{字段名}` | `idx_orders_user_id` |
| 联合索引 | `idx_{表名}_{字段1}_{字段2}` | `idx_orders_user_status` |

## 2. 表设计规范

### 必备字段
每张业务表必须包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT UNSIGNED AUTO_INCREMENT | 主键 |
| `created_at` | DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

### 可选标准字段
| 字段 | 类型 | 说明 |
|------|------|------|
| `deleted_at` | DATETIME DEFAULT NULL | 软删除标记 |
| `created_by` | BIGINT UNSIGNED | 创建人 |
| `updated_by` | BIGINT UNSIGNED | 更新人 |
| `version` | INT DEFAULT 0 | 乐观锁版本号 |
| `sort_order` | INT DEFAULT 0 | 排序权重 |

### 表设计原则
- 遵循第三范式（3NF），减少数据冗余
- 单表字段数不超过 30 个，超出考虑垂直拆分
- 不使用外键约束（应用层保证数据一致性），但保留外键字段命名
- 字符集统一使用 `utf8mb4`，排序规则 `utf8mb4_unicode_ci`
- 存储引擎使用 `InnoDB`

## 3. 字段类型规范

### 类型选择
| 场景 | 推荐类型 | 说明 |
|------|----------|------|
| 主键/外键 | BIGINT UNSIGNED | 避免 INT 溢出 |
| 短文本（≤255） | VARCHAR(N) | N 为实际最大长度 |
| 长文本 | TEXT | 不设默认值 |
| 超长文本 | MEDIUMTEXT / LONGTEXT | 按需选择 |
| 整数 | TINYINT / INT / BIGINT | 按值范围选择最小类型 |
| 小数/金额 | DECIMAL(M,D) | 禁止使用 FLOAT/DOUBLE |
| 布尔值 | TINYINT(1) | 0=否，1=是 |
| 日期 | DATE | 仅日期 |
| 时间 | DATETIME | 日期+时间，不用 TIMESTAMP |
| JSON | JSON | MySQL 5.7+ 原生支持 |
| 枚举 | TINYINT + 注释 | 不用 ENUM 类型 |

### 字段约束
- 所有字段尽量设置 `NOT NULL`，给出 `DEFAULT` 值
- VARCHAR 字段指定合理长度，不滥用 `VARCHAR(255)`
- 金额字段使用 `DECIMAL(18,2)` 或 `DECIMAL(18,4)`
- 状态字段使用 `TINYINT` 并在注释中说明枚举含义

## 4. 索引设计规范

### 索引原则
- WHERE、ORDER BY、GROUP BY、JOIN 涉及的字段建索引
- 选择性高的字段优先建索引（选择性 = 不重复值/总行数）
- 联合索引遵循**最左前缀**原则，区分度高的字段放最左
- 避免在频繁更新的字段上建过多索引
- 单表索引数不超过 5 个

### 索引禁忌
- 不在大字段（TEXT/BLOB）上建全文索引之外的索引
- 不在低选择性字段上单独建索引（如性别、布尔字段）
- 避免冗余索引：`idx(a,b)` 已覆盖 `idx(a)`
- 避免使用外键约束，用索引替代

### 联合索引设计
```sql
-- 查询：WHERE status = 1 AND user_id = 123 ORDER BY created_at DESC
-- 正确：区分度高的 user_id 放最左
CREATE INDEX idx_orders_user_status_created ON orders(user_id, status, created_at);

-- 错误：status 区分度低，放最左效果差
CREATE INDEX idx_orders_status_user ON orders(status, user_id);
```

## 5. SQL 编写规范

### 查询规范
- 禁止使用 `SELECT *`，明确列出所需字段
- 多表 JOIN 时使用表别名，字段前加别名前缀
- WHERE 条件中避免对字段进行函数运算（会导致索引失效）
- 分页查询必须带 ORDER BY，确保结果稳定
- IN 查询元素不超过 500 个，超过改用临时表 JOIN
- 大批量操作分批处理，每批不超过 1000 条

### 写入规范
- INSERT 必须指定字段名，不依赖字段顺序
- 批量 INSERT 单次不超过 1000 条
- UPDATE/DELETE 必须有 WHERE 条件，禁止全表操作
- 上线前 EXPLAIN 检查所有 SQL 的执行计划

### 示例
```sql
-- 正确
SELECT u.id, u.name, u.email
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE u.status = 1
  AND o.created_at >= '2024-01-01'
ORDER BY o.created_at DESC
LIMIT 20;

-- 错误：SELECT *，无别名，函数运算导致索引失效
SELECT *
FROM users
JOIN orders ON users.id = orders.user_id
WHERE DATE(orders.created_at) = '2024-01-01';
```

## 6. 数据迁移规范

### 变更原则
- 所有 DDL 变更必须可回滚，编写回滚脚本
- 大表变更使用在线 DDL 工具（pt-online-schema-change / gh-ost）
- 新增字段必须有 DEFAULT 值或允许 NULL
- 删除字段先标记废弃，确认无引用后再删除
- 修改字段类型先新增后迁移数据再删除旧字段

### 迁移流程
1. 开发环境验证 DDL 和回滚脚本
2. 测试环境验证数据迁移完整性
3. 生产环境低峰期执行
4. 执行前备份相关表
5. 执行后验证数据一致性

### 版本管理
- 迁移文件命名：`V{版本号}__{描述}.sql`
- 每次变更独立一个文件
- 迁移文件不可修改已提交的内容，只能新增

## 7. 性能优化

### 查询优化
- 所有查询必须走索引，上线前 EXPLAIN 确认
- type 列目标：const > eq_ref > ref > range，避免 ALL（全表扫描）
- Extra 列避免 Using filesort、Using temporary
- 大偏移量分页使用游标分页或延迟关联

### 表优化
- 单表数据量超过 500 万行考虑分表
- 历史数据定期归档，保持热表数据量可控
- 定期分析慢查询日志，优化 TOP 10 慢 SQL
- 合理使用缓存，减少数据库直接查询压力

### 连接池
- 应用层使用连接池，不每次新建连接
- 连接池最大连接数不超过数据库最大连接数的 80%
- 设置连接超时和空闲回收时间

## 8. 安全规范

- 应用使用专用数据库账号，最小权限原则
- 生产库禁止应用账号拥有 DDL 权限
- 敏感数据（密码、手机号、身份证）加密存储
- 数据库密码通过配置中心/环境变量注入，不硬编码
- 生产库操作需经过审批，操作前备份
- 定期审计数据库账号和权限
