---
name: requirements-development
description: Use when the user wants to turn a requirement into implementation-ready context through CTS, including work-item context, data and resource inspection, risk analysis, task breakdown, deployment planning, and optional collaboration updates.
---

# 需求开发

## When To Use

- 用户从需求、工单或特性请求开始
- 需要把业务诉求转成实现上下文
- 需要形成任务拆分、测试点和发布点

## Preconditions

- Run `app-context-init` if CTS environment is not ready.

## Inputs

- requirement or ticket
- target environment
- known constraints
- related task or release id if available

## Workflow

1. Read the requirement and its delivery context when available.
2. Build the current-state model:
- impacted services
- impacted tables
- impacted config
- impacted cache
- backward-compatibility concerns
3. Produce implementation tasks, test points, release points, and rollback notes.
4. If asked to code, implement after the context is complete.
5. Sync task decomposition back to collaboration tooling when useful.
6. Notify only for agreed milestones such as start, testing, or done.

## Typical R&D Scenarios

### Scenario 1: 从业务需求到实现上下文

- Trigger: 用户给出一个新需求或产品变更。
- Focus: 不直接开始写代码，先补齐现状、边界、依赖和风险。
- Output: 影响面、任务拆分、测试点、发布点。

### Scenario 2: 从缺陷修复单到改造方案

- Trigger: 缺陷看似局部，但怀疑牵涉历史逻辑或兼容性。
- Focus: 先确认是补丁修复还是顺手重构。
- Output: 最小修复方案与系统性治理方案的边界。

### Scenario 3: 从模糊需求到技术计划

- Trigger: 业务描述宽泛，缺少明确边界。
- Focus: 把非目标、灰度范围、兼容成本显式化。
- Output: 可以进入方案撰写和实现计划的输入材料。

## Core MCP Usage

Typical sequence:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <workitem_tool> '{"id":"<ticket>"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call mysql <query_tool> '{"sql":"select ..."}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call redis <cache_tool> '{"key":"<pattern>"}'
```

Core scenes:

- 读取需求或工单上下文
- 补齐现状数据和资源证据
- 输出任务拆分、测试点和发布点

## Output Contract

- goal and scope
- current-state findings
- affected components
- risks
- implementation plan
- testing and release plan

## Guardrails

- Do not jump straight to code if the current-state model is missing.
- Prefer evidence from data, config, cache, and recent logs over assumptions.

## Related Skills

- `engineering-collaboration`
- `data-management`
- `resource-management`
- `implementation-plan-writing`
- `technical-solution-writing`
