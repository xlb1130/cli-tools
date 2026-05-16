---
name: technical-solution-writing
description: Use when the user needs a technical solution document covering context, goals, options, chosen design, tradeoffs, risks, rollout, and verification strategy.
---

# 技术方案撰写

## When To Use

- 需要输出正式技术方案
- 需要把需求上下文整理成设计文档
- 需要写清楚权衡、边界和发布策略

## Preconditions

- Requirement context should exist.

## Inputs

- background
- goal and non-goals
- constraints
- proposed design

## Workflow

1. Clarify problem, scope, constraints, and success criteria.
2. Describe the proposed design and key tradeoffs.
3. Add risks, compatibility notes, rollout plan, and verification plan.
4. Keep the document structured for review and implementation.

## Typical R&D Scenarios

### Scenario 1: 新需求正式立项方案

- Trigger: 需求进入开发前，需要形成正式设计文档。
- Focus: 背景、约束、方案、风险、灰度和回滚。
- Output: 可以进入评审和开发的方案稿。

### Scenario 2: 旧系统局部改造方案

- Trigger: 看起来是小改动，但涉及历史兼容性和多模块联动。
- Focus: 明确“为什么不是简单改一下”。
- Output: 低风险演进路径和边界控制。

## Core MCP Usage

Typical alias usage:

- `yunxiao`: task and requirement context
- `gitlab`: existing code or repository context
- `grafana`: current observability and baseline context

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <workitem_tool> '{"id":"<ticket>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call gitlab <repo_tool> '{"project":"<project>"}'
```

## Output Contract

- background
- design
- tradeoffs
- risks
- rollout and verification plan

## Guardrails

- State non-goals explicitly.
- Prefer decision-ready documents over narrative-only prose.

## Related Skills

- `requirements-development`
- `solution-review`
