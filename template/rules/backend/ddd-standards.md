---
description: 进行领域驱动设计、领域建模、聚合设计、限界上下文划分、领域事件定义时使用此规则
alwaysApply: false
---

# 后端 DDD（领域驱动设计）规范

## 1. 分层架构

### 四层架构

```
├── interfaces/       # 接口层（用户接口）
│   ├── controller/   # REST 控制器
│   ├── dto/          # 数据传输对象
│   └── assembler/    # DTO ↔ Domain 转换器
├── application/      # 应用层（用例编排）
│   ├── service/      # 应用服务
│   ├── command/      # 命令对象
│   └── query/        # 查询对象
├── domain/           # 领域层（核心业务逻辑）
│   ├── model/        # 聚合根、实体、值对象
│   ├── service/      # 领域服务
│   ├── repository/   # 仓储接口（只定义，不实现）
│   └── event/        # 领域事件
└── infrastructure/   # 基础设施层（技术实现）
    ├── repository/   # 仓储实现
    ├── persistence/  # ORM 映射
    ├── messaging/    # 消息队列
    └── external/     # 外部服务调用
```

### 依赖规则
- **domain** 不依赖任何层（核心，零外部依赖）
- **application** 只依赖 domain
- **interfaces** 依赖 application 和 domain
- **infrastructure** 依赖 domain（实现 domain 定义的接口）

## 2. 领域建模

### 实体（Entity）
- 具有唯一标识（ID），标识在整个生命周期中不变
- 可变对象，属性可以改变
- 通过 ID 判断相等性，而非属性
- 包含业务行为，不只是数据容器

```java
// 实体示例
public class Order {
    private OrderId id;           // 唯一标识
    private UserId userId;
    private OrderStatus status;
    private Money totalAmount;
    private List<OrderItem> items;
    private DateTime createdAt;

    // 业务行为
    public void pay() {
        if (this.status != OrderStatus.PENDING) {
            throw new OrderStatusException("只有待支付订单可以支付");
        }
        this.status = OrderStatus.PAID;
        // 发布领域事件
        DomainEventPublisher.publish(new OrderPaidEvent(this.id));
    }

    public void cancel(String reason) {
        if (this.status == OrderStatus.SHIPPED) {
            throw new OrderStatusException("已发货订单不可取消");
        }
        this.status = OrderStatus.CANCELLED;
        this.cancelReason = reason;
    }
}
```

### 值对象（Value Object）
- 没有唯一标识，通过属性值判断相等性
- 不可变对象，创建后不可修改
- 可替换整体，不修改部分
- 自我验证，创建时保证合法性

```java
// 值对象示例
public class Money {
    private final BigDecimal amount;
    private final Currency currency;

    public Money(BigDecimal amount, Currency currency) {
        Assert.notNull(amount, "金额不能为空");
        Assert.isTrue(amount.compareTo(BigDecimal.ZERO) >= 0, "金额不能为负");
        this.amount = amount;
        this.currency = currency;
    }

    public Money add(Money other) {
        assertSameCurrency(other);
        return new Money(this.amount.add(other.amount), this.currency);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof Money)) return false;
        Money money = (Money) o;
        return amount.equals(money.amount) && currency.equals(money.currency);
    }
}
```

### 聚合（Aggregate）
- 一组相关对象的集合，作为数据修改的单元
- 聚合根（Aggregate Root）是外部访问聚合的唯一入口
- 外部只能通过聚合根引用聚合内部对象
- 聚合内部对象之间可以相互引用
- 一个事务只修改一个聚合实例

```java
// 聚合根示例
public class Order {  // Order 是聚合根
    private OrderId id;
    private List<OrderItem> items;  // OrderItem 是聚合内部实体

    public void addItem(ProductId productId, Quantity quantity, Money price) {
        // 通过聚合根操作内部对象
        OrderItem item = new OrderItem(productId, quantity, price);
        this.items.add(item);
        this.recalculateTotal();
    }

    public void removeItem(ProductId productId) {
        this.items.removeIf(item -> item.getProductId().equals(productId));
        this.recalculateTotal();
    }
}
```

### 聚合设计原则
- **小聚合**：聚合尽量小，只包含必须保持一致的對象
- **ID 引用**：聚合之间通过 ID 引用，而非对象引用
- **最终一致性**：聚合之间通过领域事件实现最终一致性
- **一个事务一个聚合**：不在一个事务中修改多个聚合

## 3. 限界上下文（Bounded Context）

### 划分原则
- 按业务能力划分，每个上下文对应一个独立的业务领域
- 上下文内部模型统一，上下文之间模型可以不同
- 每个上下文拥有独立的数据存储
- 上下文之间通过明确的接口通信

### 上下文映射关系

| 关系 | 说明 | 示例 |
|------|------|------|
| 共享内核 | 两个上下文共享部分模型 | 用户基础信息 |
| 客户-供应商 | 上游提供，下游消费 | 订单上下文 → 支付上下文 |
| 防腐层 | 下游通过适配层隔离上游模型 | 调用外部系统 |
| 开放主机 | 上游提供标准 API 供下游调用 | REST API |
| 发布语言 | 上下游使用共同定义的消息格式 | 领域事件 |

### 示例划分
```
电商系统限界上下文：

├── 用户上下文（User Context）
│   职责：用户注册、登录、个人信息管理
│
├── 商品上下文（Product Context）
│   职责：商品管理、分类、库存
│
├── 订单上下文（Order Context）
│   职责：下单、订单状态流转
│
├── 支付上下文（Payment Context）
│   职责：支付处理、退款
│
└── 物流上下文（Logistics Context）
    职责：发货、物流跟踪
```

## 4. 领域服务（Domain Service）

### 使用场景
当业务逻辑不属于任何一个实体或值对象时，使用领域服务：

- 操作涉及多个聚合
- 复杂的计算或转换逻辑
- 与外部领域的交互协调

### 规范
- 无状态，只包含行为不包含数据
- 命名体现业务意图：`PricingService`、`InventoryReservationService`
- 不直接操作数据库，通过仓储接口操作
- 与应用程序服务的区别：领域服务包含业务规则，应用服务只做编排

```java
// 领域服务示例
public class PricingService {
    public Money calculateTotalPrice(List<OrderItem> items, Coupon coupon) {
        Money subtotal = items.stream()
            .map(OrderItem::getSubtotal)
            .reduce(Money.ZERO, Money::add);

        if (coupon != null) {
            return coupon.apply(subtotal);
        }
        return subtotal;
    }
}
```

## 5. 领域事件（Domain Event）

### 定义
- 领域中发生的有业务意义的事件
- 命名使用过去式：`OrderPaid`、`UserRegistered`
- 包含事件发生时间、事件 ID、相关聚合 ID
- 不可变，一旦创建不可修改

### 使用场景
- 聚合间通信（解耦聚合）
- 限界上下文间通信
- 触发后续业务流程
- 审计日志

```java
// 领域事件示例
public class OrderPaidEvent {
    private final EventId eventId;
    private final OrderId orderId;
    private final UserId userId;
    private final Money amount;
    private final DateTime occurredAt;

    public OrderPaidEvent(OrderId orderId, UserId userId, Money amount) {
        this.eventId = EventId.generate();
        this.orderId = orderId;
        this.userId = userId;
        this.amount = amount;
        this.occurredAt = DateTime.now();
    }
}
```

### 事件处理
- 同步处理：在同一个事务中执行（简单场景）
- 异步处理：通过消息队列解耦（推荐）
- 保证至少一次投递，消费者做幂等处理

## 6. 仓储（Repository）

### 接口定义（domain 层）
```java
// 仓储接口在 domain 层定义
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    List<Order> findByUserId(UserId userId);
    void save(Order order);
    void delete(Order order);
}
```

### 实现规范（infrastructure 层）
- 仓储只操作聚合根，不直接操作聚合内部对象
- 查询方法返回领域对象，不是数据库实体
- 保存方法处理整个聚合的持久化
- 不返回 IQueryable/Stream 等延迟查询接口（避免业务逻辑泄露到基础设施层）

## 7. 应用服务（Application Service）

### 职责
- 接收 DTO，转换后调用领域层
- 事务边界管理
- 权限校验
- 调用多个领域服务/聚合完成一个用例
- 发布应用层事件（非领域事件）

### 规范
- 应用服务不包含业务逻辑，只做任务编排
- 一个应用服务方法对应一个用例
- 方法命名体现用例：`createOrder`、`cancelOrder`、`queryOrderDetail`

```java
// 应用服务示例
public class OrderApplicationService {
    @Transactional
    public OrderDTO createOrder(CreateOrderCommand command) {
        // 1. 参数转换
        UserId userId = new UserId(command.getUserId());
        List<OrderItemDTO> itemDTOs = command.getItems();

        // 2. 调用领域层
        User user = userRepository.findById(userId)
            .orElseThrow(() -> new UserNotFoundException(userId));
        Order order = user.createOrder(itemDTOs);

        // 3. 持久化
        orderRepository.save(order);

        // 4. 返回 DTO
        return OrderAssembler.toDTO(order);
    }
}
```

## 8. DTO 与 Assembler

### DTO（Data Transfer Object）
- 用于层间数据传输，不包含业务逻辑
- 与领域对象分离，领域对象变化不影响外部接口
- 不同场景使用不同 DTO：RequestDTO、ResponseDTO、Command、Query

### Assembler（转换器）
- 负责 DTO ↔ 领域对象 的双向转换
- 转换逻辑集中管理，不散落在各层
- 简单转换使用静态工厂方法，复杂转换使用独立 Assembler 类

```java
public class OrderAssembler {
    public static OrderDTO toDTO(Order order) {
        OrderDTO dto = new OrderDTO();
        dto.setId(order.getId().getValue());
        dto.setStatus(order.getStatus().name());
        dto.setTotalAmount(order.getTotalAmount().toYuan());
        dto.setItems(order.getItems().stream()
            .map(OrderAssembler::toItemDTO)
            .collect(Collectors.toList()));
        return dto;
    }

    public static Order toDomain(CreateOrderCommand command) {
        // 转换逻辑
    }
}
```

## 9. 编码检查清单

- [ ] domain 层是否零外部依赖
- [ ] 实体是否包含业务行为，而非贫血模型
- [ ] 值对象是否不可变且自我验证
- [ ] 聚合边界是否合理，是否一个事务只修改一个聚合
- [ ] 聚合之间是否通过 ID 引用
- [ ] 领域服务是否无状态
- [ ] 应用服务是否只做编排，不包含业务规则
- [ ] 仓储接口是否在 domain 层定义
- [ ] 限界上下文边界是否清晰
- [ ] 领域事件命名是否使用过去式
