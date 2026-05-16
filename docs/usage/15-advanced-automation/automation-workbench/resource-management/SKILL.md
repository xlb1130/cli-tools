---
name: resource-management
description: Use when the user needs runtime resource inspection through CTS, including configuration, cache, JVM, health state, switch usage, and related environment checks.
---

# 资源管理

## When To Use

- 需要检查配置、缓存或 JVM 状态
- 需要做环境健康检查
- 需要核对开关、配置中心或运行资源

## Preconditions

- Run `app-context-init` if the environment is not initialized.

## Inputs

- environment
- service
- resource type
- expected behavior

## Workflow

1. Confirm the target environment and resource class.
2. Inspect configuration, cache, health state, or JVM as needed.
3. Compare expected and actual values or signals.
4. Summarize risky differences and next actions.

## Typical R&D Scenarios

### Scenario 1: 配置变更后行为异常

- Trigger: 发布未变，但业务行为突然变化。
- Focus: 配置中心、开关、命名空间、灰度范围是否发生漂移。
- Output: 配置差异、影响范围、建议恢复值。

### Scenario 2: 缓存或锁导致的状态异常

- Trigger: 数据正确，但接口返回不符合预期，且具有时间性或实例性。
- Focus: 缓存值、过期时间、锁状态、队列积压。
- Output: 资源侧异常点和是否可用清理/刷新缓解。

### Scenario 3: 运行资源逼近极限

- Trigger: 延迟抬升、重启增多、线程堆积。
- Focus: pod 状态、资源配额、连接池、JVM 或容器事件。
- Output: 资源瓶颈结论和扩容、限流、回滚建议。

## Core MCP Usage

Typical alias to scenario mapping:

- `redis`: cache, lock, queue, rate-limit state
- `kubernetes`: pod, deployment, events, restart status
- `grafana`: health, metrics, alerts
- `yunxiao` or `gitlab`: correlate resource state with release or task context

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json info redis
mcp-cli -c ~/.config/mcp/mcp_servers.json call redis <cache_tool> '{"key":"order:123"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json info kubernetes
mcp-cli -c ~/.config/mcp/mcp_servers.json call kubernetes <cluster_tool> '{"namespace":"prod","labelSelector":"app=order"}'
```

## Output Contract

- target resource
- observed state
- mismatch or anomaly
- risk level

## Guardrails

- Prefer read-only inspection unless mutation is explicitly requested.
- Separate confirmable facts from suggestive runtime clues.

## Related Skills

- `incident-diagnosis`
- `performance-baseline`
- `security-review`
