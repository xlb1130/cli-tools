---
name: engineering-collaboration
description: Use when the user needs engineering task collaboration, Yunxiao-linked work item sync, task status updates, risk notes, release notes, or structured coordination across delivery roles.
---

# 研发协作

## When To Use

- 需要读写 Yunxiao 任务或需求上下文
- 需要同步任务拆分、风险和测试点
- 需要做跨角色协作更新

## Preconditions

- Run `app-context-init` if CTS delivery sources are not ready.

## Inputs

- work item id
- update type
- structured summary

## Workflow

1. Read the work item or release context first.
2. Capture only the fields needed for the current task.
3. Write back concise structured results such as conclusion, task split, risk, test point, and release note.
4. Notify stakeholders only when useful.

## Typical R&D Scenarios

### Scenario 1: 需求分析后回写任务拆分

- Trigger: 已完成需求上下文分析，需要同步给研发、测试或交付角色。
- Focus: 只回写真正能推动执行的结构化信息。
- Output: 任务拆分、风险、测试点、发布说明。

### Scenario 2: 故障处理后的结论同步

- Trigger: 排障结束，需要把根因和处理结果同步回工作项。
- Focus: 结论、影响范围、修复动作、后续跟踪项。
- Output: 便于后续复盘和审计的简明更新。

### Scenario 3: 发布过程中的里程碑同步

- Trigger: 转测、发布开始、发布完成、回滚完成。
- Focus: 保持跨角色信息一致，而不是刷屏式通知。
- Output: 状态更新和下一动作。

## Core MCP Usage

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json info yunxiao
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <read_tool> '{"id":"<work_item_id>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <update_tool> '{"id":"<work_item_id>","summary":"<update>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call dingtalk <notify_tool> '{"text":"<milestone update>"}'
```

Core scenes:

- 读取任务/需求详情
- 回写结论、风险、测试点
- 关键节点同步通知

## Output Contract

- read or update target
- structured summary
- sync result

## Guardrails

- Do not spam repeated updates.
- Keep task updates concise and execution-oriented.

## Related Skills

- `requirements-development`
- `dingtalk-webhook-notify`
