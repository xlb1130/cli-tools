---
name: solution-review
description: Use when the user needs technical solution review, option comparison, architecture risk identification, edge-case coverage checks, or readiness feedback before implementation starts.
---

# 方案评审

## When To Use

- 技术方案需要评审
- 需要比较多个实现路径
- 需要提前暴露边界条件和风险

## Preconditions

- A written solution draft should exist.

## Inputs

- problem statement
- proposed design
- constraints
- alternatives if any

## Workflow

1. Evaluate the proposal against the goal and constraints.
2. Check correctness, maintainability, operability, and compatibility.
3. Compare alternatives where tradeoffs are material.
4. Return risks, questions, and recommended adjustments.

## Typical R&D Scenarios

### Scenario 1: 方案评审会前预审

- Trigger: 技术方案已成稿，准备进正式评审。
- Focus: 先筛掉明显风险和逻辑漏洞。
- Output: 评审问题列表和建议调整项。

### Scenario 2: 多方案选型比较

- Trigger: 同一个问题有两到三个实现路径。
- Focus: 比较复杂度、可运维性、兼容性和长期成本。
- Output: 推荐路径和放弃其他方案的理由。

## Core MCP Usage

Typical alias usage:

- `yunxiao`: requirement and release context
- `gitlab`: existing implementation or repository context
- `grafana`: current observability baseline

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <workitem_tool> '{"id":"<ticket>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call gitlab <repo_tool> '{"project":"<project>"}'
```

## Output Contract

- strengths
- risks
- open questions
- recommendation

## Guardrails

- Challenge weak assumptions directly.
- Prefer concrete failure modes over generic advice.

## Related Skills

- `technical-solution-writing`
- `security-review`
