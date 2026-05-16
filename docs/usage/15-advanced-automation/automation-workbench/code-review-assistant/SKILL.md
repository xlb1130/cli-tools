---
name: code-review-assistant
description: Use when the user needs structured code review help, including risk identification, regression review, missing tests, rollout concerns, and implementation consistency checks.
---

# 代码审查辅助

## When To Use

- 需要审查 diff、提交或实现方案
- 需要梳理风险点和缺失测试点
- 需要发布前做变更质量把关

## Preconditions

- None.

## Inputs

- diff or changed files
- requirement or expected behavior
- test evidence if available

## Workflow

1. Read the change with the intended behavior in mind.
2. Identify correctness, regression, and operability risks.
3. Check missing tests, rollout notes, and compatibility concerns.
4. Return findings ordered by severity.

## Typical R&D Scenarios

### Scenario 1: 合并前 MR 风险审查

- Trigger: 提交已完成，需要判断是否适合合并。
- Focus: 正确性、回归风险、缺失测试、发布风险。
- Output: 按严重度排序的 findings。

### Scenario 2: 高风险改动专项审查

- Trigger: 涉及配置中心、缓存、数据修复、兼容性或安全边界。
- Focus: 不只看代码风格，重点看失败模式和回滚能力。
- Output: 是否需要补测试、补监控、拆分发布。

## Core MCP Usage

Typical alias usage:

- `gitlab`: merge request, diff, pipeline, issue context
- `yunxiao`: requirement or task context

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json info gitlab
mcp-cli -c ~/.config/mcp/mcp_servers.json call gitlab <mr_tool> '{"project":"<project>","merge_request":"<mr_id>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <workitem_tool> '{"id":"<ticket>"}'
```

## Output Contract

- findings
- affected areas
- missing tests
- open questions

## Guardrails

- Prioritize concrete risks over stylistic opinions.
- Do not approve behavior that is not evidenced by code or tests.

## Related Skills

- `requirements-development`
- `implementation-acceptance`
