---
name: implementation-plan-writing
description: Use when the user needs an implementation plan with task breakdown, milestones, dependency ordering, validation points, rollback considerations, and owner-oriented execution steps.
---

# 编写实现计划

## When To Use

- 需要把需求拆成实现步骤
- 需要安排里程碑和依赖顺序
- 需要形成开发、测试、发布计划

## Preconditions

- Requirement context should already be built.

## Inputs

- requirement summary
- affected components
- constraints and risks

## Workflow

1. Break the work into implementation slices.
2. Order tasks by dependency and risk.
3. Add validation points, test points, and release checkpoints.
4. Include rollback and fallback notes where relevant.

## Typical R&D Scenarios

### Scenario 1: 需求拆解为研发执行计划

- Trigger: 需求和方案已基本清楚，需要落到执行层。
- Focus: 把工作拆成可交付、可验证、可串行/并行推进的任务。
- Output: 里程碑、依赖顺序、测试和发布计划。

### Scenario 2: 高风险改造的分阶段推进计划

- Trigger: 一次性上线风险过高。
- Focus: 拆阶段、拆灰度、拆验证点。
- Output: 分阶段计划和每阶段的放行条件。

## Core MCP Usage

Typical alias usage:

- `yunxiao`: source requirement and task breakdown destination
- `gitlab`: current implementation context
- `grafana`: release and observability checkpoints

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <workitem_tool> '{"id":"<ticket>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call gitlab <repo_tool> '{"project":"<project>"}'
```

## Output Contract

- task breakdown
- ordering and milestones
- validation plan
- release notes

## Guardrails

- Prefer small verifiable steps.
- Keep hidden dependencies explicit.

## Related Skills

- `requirements-development`
- `release-checklist-generator`
