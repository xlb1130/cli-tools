---
name: self-evolution
description: Use when the user needs retrospective capture, rule updates, incident learnings, reusable patterns, or structured experience accumulation after engineering work completes.
---

# 自进化

## When To Use

- 任务结束后需要沉淀经验
- 故障或发布后需要复盘
- 需要更新规则、检查项或知识模板

## Preconditions

- Prefer `app-context-init` if shared scripts and settings are required.

## Inputs

- task summary
- lessons learned
- reusable patterns
- rule updates

## Workflow

1. Summarize what happened, what worked, and what failed.
2. Extract reusable rules, anti-patterns, and missing checks.
3. Map findings to docs, scripts, or process updates.
4. Record the result in a structured form.

## Typical R&D Scenarios

### Scenario 1: 线上事故后的经验沉淀

- Trigger: 故障已经恢复，但团队不希望同类问题再次发生。
- Focus: 从事实中抽出可以固化的规则、脚本和检查项。
- Output: 复盘结论和规则更新建议。

### Scenario 2: 高价值优化成功后的模式提炼

- Trigger: 一次优化显著改善了交付效率或稳定性。
- Focus: 把成功经验抽象成可复用做法。
- Output: 最佳实践和复用条件。

## Core MCP Usage

Typical alias usage:

- `yunxiao`: task or incident context
- `grafana`: objective evidence for retrospective
- `dingtalk`: summary broadcast when needed

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <workitem_tool> '{"id":"<ticket>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call grafana <metric_tool> '{"service":"order","metric":"error_rate","window":"24h"}'
```

## Output Contract

- incident or task summary
- lessons learned
- proposed rule changes
- follow-up actions

## Guardrails

- Convert opinions into reusable rules only when evidence exists.
- Prefer small concrete updates over broad generic conclusions.

## Related Skills

- `app-context-init`
- `implementation-acceptance`
