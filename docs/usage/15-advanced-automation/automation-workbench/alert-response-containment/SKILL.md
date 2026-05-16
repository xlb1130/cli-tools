---
name: alert-response-containment
description: Use when the user needs alert response, impact containment, rollback guidance, switch-based mitigation, or short-term stop-loss actions before a full root-cause fix.
---

# 告警响应与止血

## When To Use

- 需要先止血再排查
- 需要判断是否回滚
- 需要通过开关、限流或隔离做临时缓解

## Preconditions

- `incident-diagnosis` should already have symptom and impact evidence.

## Inputs

- incident summary
- impact scope
- available mitigation options

## Workflow

1. Confirm user impact, blast radius, and current severity.
2. Evaluate rollback, switch, downgrade, or isolation options.
3. Recommend the lowest-risk stop-loss path.
4. Define validation signals after mitigation.

## Typical R&D Scenarios

### Scenario 1: 生产故障快速止血

- Trigger: 核心链路故障正在扩大。
- Focus: 先恢复稳定性，再追求完美根因。
- Output: 最低风险止血路径和验证指标。

### Scenario 2: 配置或开关导致的异常扩散

- Trigger: 发布后无代码回滚价值，但配置或灰度范围有问题。
- Focus: 回切配置、关闭开关、缩小影响面。
- Output: 最小化影响的操作顺序。

## Core MCP Usage

Typical alias usage:

- `redis`: queue, lock, rate-limit, session state
- `kubernetes`: pod isolation, rollout state
- `grafana`: mitigation result verification
- `dingtalk`: escalation broadcast

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call kubernetes <cluster_tool> '{"namespace":"prod","labelSelector":"app=order"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call grafana <metric_tool> '{"service":"order","metric":"error_rate","window":"15m"}'
```

## Output Contract

- impact summary
- containment option
- execution order
- verification signals

## Guardrails

- Prefer reversible mitigations.
- Call out business tradeoffs and residual risk explicitly.

## Related Skills

- `incident-diagnosis`
- `dingtalk-webhook-notify`
