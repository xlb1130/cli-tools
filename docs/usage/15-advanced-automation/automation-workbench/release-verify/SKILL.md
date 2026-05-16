---
name: release-verify
description: Use when the user needs deployment execution or release verification through CTS, including Jenkins builds, pre-release checks, post-release smoke validation, rollback reasoning, milestone notifications, and evidence-based release conclusions.
---

# 发布校验

## When To Use

- 需要执行发布或发布后校验
- 需要做冒烟验证、日志验证、数据验证
- 需要判断是否回滚

## Preconditions

- Run `app-context-init` if CTS environment is not ready.

## Inputs

- environment
- release identifier
- pipeline or build identifier
- verification scope

## Workflow

1. Validate target environment and release identifier.
2. Check key config and resource readiness before deployment.
3. Trigger or inspect Jenkins pipeline.
4. Verify logs, data, and runtime signals after release.
5. Recommend rollback if the evidence fails validation.
6. Notify only at start, success, failure, or rollback.

## Typical R&D Scenarios

### Scenario 1: 常规发布放行

- Trigger: 已完成开发和测试，准备按计划发布。
- Focus: 发布前检查、发布中观察、发布后日志/指标/数据三类验证。
- Output: 放行结论或继续观察建议。

### Scenario 2: 发布后异常但未到回滚阈值

- Trigger: 有少量异常，但影响范围和趋势还不明朗。
- Focus: 区分短暂抖动还是系统性回归。
- Output: 继续观察、限流降级或立即回滚的建议。

### Scenario 3: 生产紧急回滚判断

- Trigger: 发布后核心路径明显退化或错误率持续上升。
- Focus: 是否满足回滚条件、回滚后验证哪些指标。
- Output: 回滚建议、验证步骤、通知内容。

## Core MCP Usage

Typical sequence:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <release_tool> '{"releaseId":"<id>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call grafana <log_or_metric_tool> '{"service":"order","window":"post-release"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call mysql <query_tool> '{"sql":"select count(*) as c from orders where created_at >= now() - interval 10 minute"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call dingtalk <notify_tool> '{"text":"release verified"}'
```

Core scenes:

- 发布前校验依赖和配置
- 发布后做日志、指标、数据三类验证
- 失败时形成回滚建议并通知

## Output Contract

- target release
- verification evidence
- pass or fail conclusion
- rollback recommendation if needed

## Guardrails

- Treat production deployment as high risk.
- Prefer explicit verification evidence over pipeline status alone.

## Related Skills

- `log-query`
- `data-management`
- `resource-management`
- `dingtalk-webhook-notify`
