---
name: data-management
description: Use when the user needs database facts through CTS, such as record lookup, scope estimation, anomaly sampling, release validation, or business data confirmation.
---

# 数据管理

## When To Use

- 需要查询数据事实
- 需要抽样验证异常或影响范围
- 需要做发布后数据校验

## Preconditions

- Run `app-context-init` if CTS environment is not ready.

## Inputs

- environment
- business key or table
- time range
- question to answer

## Workflow

1. Discover the available data mounts or operations if needed.
2. Clarify the business key, time range, and environment.
3. Query the minimum data needed to answer the question.
4. Summarize findings in business terms, not raw rows only.

## Typical R&D Scenarios

### Scenario 1: 缺陷影响范围评估

- Trigger: 已定位一个业务逻辑缺陷，需要评估影响用户和记录范围。
- Focus: 统计数量、时间分布、关键样本，而不是先导全量。
- Output: 影响规模、典型样本、是否需要补数据。

### Scenario 2: 发布后数据对账

- Trigger: 发布后需要确认核心数据是否按预期写入。
- Focus: 新增量、状态流转、关键字段变化。
- Output: 是否通过、异常样本、下一步处理建议。

### Scenario 3: 单个投诉工单回溯

- Trigger: 用户提供订单号、用户 ID、任务 ID 等业务键。
- Focus: 沿业务主键回看完整状态变化。
- Output: 真实业务状态、异常环节、是否需要联动缓存或配置检查。

## Core MCP Usage

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json info mysql
mcp-cli -c ~/.config/mcp/mcp_servers.json grep "*query*"
mcp-cli -c ~/.config/mcp/mcp_servers.json call mysql <query_tool> '{"sql":"select count(*) as c from orders where created_at >= now() - interval 1 day"}'
```

Core scenes:

- 查询单条业务记录
- 统计影响范围
- 抽样异常数据
- 发布后做数据对账

## Output Contract

- query scope
- key counts or samples
- business conclusion
- next check

## Guardrails

- Avoid destructive SQL.
- Summarize sensitive fields rather than exposing unnecessary raw values.

## Related Skills

- `incident-diagnosis`
- `requirements-development`
- `release-verify`
