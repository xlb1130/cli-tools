---
name: task-scheduling-execution
description: Use when the user needs to schedule, trigger, or track repeatable automation tasks, including execution windows, run conditions, result tracking, and failure handling.
---

# 任务调度与执行

## When To Use

- 需要定时执行自动化任务
- 需要批量触发或条件触发任务
- 需要追踪执行结果和失败处理

## Preconditions

- Run `app-context-init` if tracking assets are required.

## Inputs

- task objective
- schedule or trigger condition
- environment
- success and failure criteria

## Workflow

1. Define trigger, scope, and execution boundaries.
2. Validate required config, scripts, and reporting path.
3. Execute or register the task schedule.
4. Record run status, output summary, and retries or escalation.

## Typical R&D Scenarios

### Scenario 1: 周期性健康检查任务

- Trigger: 需要每天或每小时自动巡检。
- Focus: 固定窗口、固定责任边界、固定上报出口。
- Output: 执行记录和异常告警。

### Scenario 2: 定时数据核对或补偿

- Trigger: 需要周期性核对数据或触发轻量补偿动作。
- Focus: 调度条件、失败重试、异常升级。
- Output: 可追踪的批次执行结果。

## Core MCP Usage

Typical alias usage:

- `kubernetes`: scheduled cluster tasks or runtime checks
- `grafana`: periodic verification
- `dingtalk`: failure notification

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call kubernetes <cluster_tool> '{"namespace":"prod"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call dingtalk <notify_tool> '{"text":"scheduled task failed"}'
```

## Output Contract

- schedule or trigger
- execution status
- tracking summary
- escalation path

## Guardrails

- Make retries explicit.
- Keep scheduled work observable and attributable.

## Related Skills

- `app-context-init`
- `dingtalk-webhook-notify`
