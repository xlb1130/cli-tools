---
name: release-checklist-generator
description: Use when the user needs a release checklist generated from change scope, dependencies, environments, test evidence, rollback expectations, and release-time operational constraints.
---

# 发布检查清单生成

## When To Use

- 需要产出发布前检查清单
- 需要把变更点转成可执行核对项
- 需要统一发布/回滚检查模板

## Preconditions

- Requirement and change scope should be known.

## Inputs

- change scope
- environments
- dependencies
- test evidence
- rollback notes

## Workflow

1. Read the scope, dependencies, and environments.
2. Generate pre-release, release-window, and post-release checks.
3. Add rollback and notification checkpoints where relevant.
4. Mark owner and evidence expectations for each item.

## Typical R&D Scenarios

### Scenario 1: 常规版本发布清单生成

- Trigger: 一次标准版本即将进入发布窗口。
- Focus: 把需求、配置、依赖、验证项转成可执行清单。
- Output: 发布前、中、后检查项。

### Scenario 2: 高风险版本专项清单

- Trigger: 涉及多服务、多配置、大量数据或灰度策略。
- Focus: 增加回滚、监控、灰度和止血检查项。
- Output: 专项版清单和责任人分配建议。

## Core MCP Usage

Typical alias usage:

- `yunxiao`: release or work-item scope
- `gitlab`: merge request and pipeline context
- `grafana`: post-release verification expectations

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <release_tool> '{"id":"<release_id>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call gitlab <mr_tool> '{"project":"<project>","merge_request":"<mr_id>"}'
```

## Output Contract

- pre-release checklist
- release-window checklist
- post-release checklist
- rollback checklist

## Guardrails

- Prefer concrete verifiable checks.
- Keep the checklist executable, not descriptive only.

## Related Skills

- `release-verify`
- `requirements-development`
