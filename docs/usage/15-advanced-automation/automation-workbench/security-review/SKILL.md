---
name: security-review
description: Use when the user needs security baseline review for implementation, configuration, data handling, dependency usage, permission boundaries, or external interfaces before release.
---

# 安全审查

## When To Use

- 需要从安全视角复核实现或方案
- 需要检查敏感配置、权限和接口暴露
- 需要发布前做安全基线核对

## Preconditions

- Relevant implementation or design context should exist.

## Inputs

- implementation or solution scope
- involved data and permissions
- external dependencies or interfaces

## Workflow

1. Identify sensitive data, privilege boundaries, and exposed interfaces.
2. Check configuration, secret handling, dependency trust, and auditability.
3. Flag baseline violations and risk scenarios.
4. Recommend concrete remediations and residual risk notes.

## Typical R&D Scenarios

### Scenario 1: 发布前安全复核

- Trigger: 功能已完成，准备上线。
- Focus: 权限、密钥、敏感数据、外部接口暴露。
- Output: 可放行项、阻塞项、后续整改项。

### Scenario 2: 方案阶段安全前置审查

- Trigger: 方案涉及新依赖、新接口或高敏感数据处理。
- Focus: 在开发前把明显安全债挡住。
- Output: 设计层面的安全约束和例外项。

## Core MCP Usage

Typical alias usage:

- `gitlab`: repository, merge request, CI variables, code context
- `kubernetes`: runtime permissions and secret references
- `grafana`: audit or alert coverage verification

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call gitlab <repo_tool> '{"project":"<project>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call kubernetes <cluster_tool> '{"namespace":"prod","labelSelector":"app=order"}'
```

## Output Contract

- security findings
- impacted areas
- remediation actions
- residual risk

## Guardrails

- Prioritize exploitable or high-impact issues.
- Keep recommendations actionable and specific.

## Related Skills

- `resource-management`
- `solution-review`
