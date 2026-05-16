---
name: dingtalk-webhook-notify
description: Use when the user needs DingTalk webhook messages for task completion, deployment milestones, incident updates, release failures, or other important engineering checkpoints.
---

# 钉钉 Webhook 消息

## When To Use

- 任务完成
- 测试开始或结束
- 发布开始、成功、失败或回滚
- 故障结论确认

## Preconditions

- None.

## Inputs

- event type
- task or release id
- environment
- owner
- message body

## Workflow

1. Confirm the notification is meaningful and actionable.
2. Build a short message with key identifiers and next action.
3. Send via the webhook path exposed by CTS.
4. Record the result.

## Core MCP Usage

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json info dingtalk
mcp-cli -c ~/.config/mcp/mcp_servers.json call dingtalk <notify_tool> '{"text":"[prod] release succeeded"}'
```

Core scenes:

- 发布结果播报
- 故障结论通知
- 任务里程碑同步

## Output Contract

- notification target
- message summary
- send result

## Guardrails

- Do not send noisy intermediate updates.
- Prefer short, scannable messages.

## Related Skills

- `release-verify`
- `incident-diagnosis`
- `engineering-collaboration`
