---
name: implementation-acceptance
description: Use when the user needs implementation acceptance, feature completion checks, acceptance criteria traceability, and structured go or no-go conclusions after delivery.
---

# 实现验收

## When To Use

- 开发完成后需要做验收
- 需要核对需求与实现是否一致
- 需要产出验收结论

## Preconditions

- Integration or verification evidence should exist.

## Inputs

- acceptance criteria
- implementation scope
- verification evidence

## Workflow

1. Map acceptance criteria to implementation and evidence.
2. Check missing scenarios, compatibility, and rollback readiness.
3. Classify each acceptance item as pass, fail, or pending.
4. Give an explicit release recommendation.

## Typical R&D Scenarios

### Scenario 1: 开发完成后的正式验收

- Trigger: 需求开发结束，准备进入发布或交付。
- Focus: 逐条验收需求，而不是只看“功能能跑”。
- Output: 通过、附条件通过或不通过。

### Scenario 2: 返工后的二次验收

- Trigger: 首轮验收发现问题，修复后再次确认。
- Focus: 问题是否关闭、是否引入新问题。
- Output: 闭环结论和剩余风险。

## Core MCP Usage

Typical alias usage:

- `playwright`: UI and E2E evidence
- `mysql`: data verification
- `grafana`: runtime verification

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call playwright <browser_tool> '{"url":"https://test.example.com"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call mysql <query_tool> '{"sql":"select ..."}'
```

## Output Contract

- acceptance matrix
- evidence summary
- unresolved gaps
- final recommendation

## Guardrails

- Do not mark pass without evidence.
- Call out pending items separately from failures.

## Related Skills

- `integration-test-platform`
- `release-verify`
