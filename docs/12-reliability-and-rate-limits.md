# 可靠性、限流与幂等

## 1. 为什么这层不能只靠 provider 自己处理

`cts` 的核心价值之一，是把不同来源的能力统一成稳定的执行平面。那可靠性也不能各做各的。

如果 HTTP、MCP、CLI、workflow 各自定义重试和超时策略，后面会出现：

- 同样的写操作，有的会盲目重试，有的完全不重试
- 限流信息没法统一透出给前端和日志
- workflow 不知道某一步是否可安全重试
- AI 和自动化系统无法推断重复执行风险

所以可靠性必须上升到平台层。

## 2. 可靠性要覆盖哪些问题

至少包括：

- 超时
- 重试
- backoff
- 限流
- 并发控制
- 幂等
- 重复提交抑制
- 熔断与降级

## 3. 可靠性策略的分层

建议分四层。

### 3.1 全局默认

例如：

- 默认超时
- 默认最大重试次数
- 默认 backoff 策略

### 3.2 source 级

适合表达：

- 某个 API 的全局限流窗口
- 某个 CLI 的默认超时
- 某个 MCP server 的调用预算

### 3.3 mount 级

适合表达：

- 某个操作是否可重试
- 是否需要 idempotency key
- 是否允许并发执行

### 3.4 单次请求覆盖

适合：

- `--timeout 5`
- `--retry 0`
- `--non-idempotent`

## 4. 建议的配置模型

建议顶层增加：

```yaml
reliability:
  defaults:
    timeout_seconds: 30
    retry:
      max_attempts: 2
      backoff: exponential
      base_delay_ms: 300
      jitter: full
    concurrency:
      max_inflight_per_source: 4
```

source 级：

```yaml
sources:
  jira_http:
    type: http
    reliability:
      timeout_seconds: 15
      retry:
        max_attempts: 3
        retry_on:
          - timeout
          - rate_limit
          - upstream_5xx
      rate_limit:
        budget_key: jira-default
        requests_per_minute: 120
```

mount 级：

```yaml
mounts:
  - id: stripe-customer-create
    source: stripe_api
    operation: create_customer
    reliability:
      timeout_seconds: 20
      retry:
        max_attempts: 1
      idempotency:
        required: true
        strategy: hash_args
        header_name: Idempotency-Key
```

## 5. 超时与重试原则

## 5.1 超时必须显式分层

建议至少区分：

- connect timeout
- read timeout
- total timeout
- process timeout

对于 CLI 和 shell，还要区分：

- 启动超时
- 单步执行超时
- 整体 workflow 超时

## 5.2 重试不能脱离风险等级

默认建议：

- `read/query` 类型可按策略重试
- `write` 类型默认不自动重试，除非显式声明幂等
- `destructive` 类型默认禁止自动重试

## 5.3 backoff 建议

推荐至少支持：

- fixed
- exponential
- exponential with jitter

## 6. 限流与预算治理

限流不能只理解成 HTTP 429。

还包括：

- 某个 CLI 调用过于频繁导致账户封禁
- 某个 MCP server 并发太高被拒绝
- 某个内部 RPC 有每秒调用预算

建议统一抽象：

```yaml
reliability:
  budgets:
    github-api:
      requests_per_hour: 4500
    mcp-github:
      max_inflight: 2
```

source 或 mount 绑定 `budget_key` 即可。

## 7. 幂等与重复执行抑制

这是平台层特别重要的一点。

## 7.1 为什么要平台统一处理

因为 `cts` 后面既会被人手动调用，也会被：

- AI agent
- workflow
- 定时任务
- 前端按钮

重复触发的概率很高。

## 7.2 建议的幂等声明

mount 或 operation 级建议支持：

- `idempotency.required`
- `idempotency.strategy`
- `idempotency.ttl_seconds`
- `idempotency.key_template`

策略例如：

- `provider_native`
- `hash_args`
- `hash_selected_fields`
- `caller_supplied`

## 7.3 平台去重

对于支持的平台级去重，可选实现：

- 记录最近执行指纹
- 在 TTL 内拒绝重复执行
- 对 workflow 步骤生成 step-level idempotency key

## 8. 不同 provider 的特殊规则

## 8.1 HTTP / OpenAPI

重点：

- 429 / Retry-After
- 5xx 自动退避
- 对支持的接口注入 `Idempotency-Key`

## 8.2 GraphQL

需要区分：

- query 通常可安全重试
- mutation 只有声明幂等后才自动重试

## 8.3 CLI

CLI 是最危险的一类。

建议默认：

- 无明确幂等声明时，不重试写命令
- 长时间运行命令支持 kill + 标记未知状态
- 对带副作用命令保留审计记录

## 8.4 MCP

MCP tool 是否幂等常常没有完整声明。

建议：

- 默认跟随 risk 分类
- 如果 tool metadata 不足，保守处理
- 允许 mount 手工补充 `idempotency` 与 `retry` 策略

## 8.5 Workflow / Composite

workflow 要额外处理：

- 步骤级超时
- 步骤级重试
- 整体预算
- 补偿逻辑

不能简单把每一步都无限重试。

## 9. 熔断、降级与回退

长期建议支持：

- provider 连续失败时短暂熔断
- schema 拉取失败时降级到旧 cache
- help 编译失败时仍允许稳定入口执行

这类能力不一定第一阶段实现，但策略层建议预留：

- `circuit_breaker`
- `fallback_mode`
- `degraded_ok`

## 10. 观测与日志要求

建议新增事件：

- `retry_scheduled`
- `retry_executed`
- `rate_limit_hit`
- `budget_exhausted`
- `idempotency_key_generated`
- `duplicate_execution_blocked`
- `circuit_opened`
- `degraded_execution`

建议记录字段：

- `attempt`
- `max_attempts`
- `timeout_seconds`
- `budget_key`
- `retry_after_ms`
- `idempotency_key`
- `idempotency_strategy`

## 11. 前端和 AI 应看到什么

前端页面与 `cts manage explain` 建议展示：

- 是否可自动重试
- 默认超时
- 是否要求 idempotency key
- 最近一次是否因为限流失败
- 当前 source 的预算状态

这样用户在点击执行前，就能知道风险与预期行为。

## 12. 最终建议

可靠性设计的关键不是“给每个 provider 多写几个 retry 参数”，而是让所有来源都落到同一套执行语义：

- 超时怎么解释
- 重试何时发生
- 限流如何治理
- 幂等如何表达
- 重复执行怎么避免

这套语义一旦稳定，后面无论接 API、CLI、MCP 还是 workflow，都能共享同一个执行治理层。
