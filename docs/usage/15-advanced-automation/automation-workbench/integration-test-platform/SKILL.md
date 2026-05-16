---
name: integration-test-platform
description: Use when the user needs integration test environment preparation, dependency validation, test data setup, execution orchestration, or structured integration test evidence.
---

# 集成测试平台

## When To Use

- 需要准备或校验集成测试环境
- 需要执行跨服务联调验证
- 需要整理集成测试结果

## Preconditions

- Run `app-context-init` if test config assets are required.

## Inputs

- environment
- test scope
- dependent services
- data or fixture requirements

## Workflow

1. Confirm environment, scope, and dependencies.
2. Validate configuration, switches, and test data readiness.
3. Execute the agreed integration scenarios.
4. Summarize pass, fail, blocked, and evidence.

## Typical R&D Scenarios

### Scenario 1: 需求提测前联调检查

- Trigger: 开发认为功能已完成，准备转测。
- Focus: 环境、依赖、测试数据和关键链路是否真的 ready。
- Output: 可转测 / 阻塞项 / 需补环境项。

### Scenario 2: 多服务改动后的回归验证

- Trigger: 一次需求同时改了多个服务或多个存储。
- Focus: 不是只测 happy path，而是检查跨服务边界和失败回退。
- Output: 关键场景通过情况和残余风险。

### Scenario 3: 发布前模拟生产验证

- Trigger: 风险较高，需要在测试环境尽量靠近真实流量行为验证。
- Focus: 配置、兼容性、缓存、异步链路。
- Output: 是否建议进入发布窗口。

## Core MCP Usage

Typical alias usage:

- `playwright`: browser and UI flows
- `mysql`: data setup or validation
- `redis`: cache or session validation

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json info playwright
mcp-cli -c ~/.config/mcp/mcp_servers.json call playwright <browser_tool> '{"url":"https://test.example.com"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call mysql <query_tool> '{"sql":"select ..."}'
```

## Output Contract

- test scope
- environment readiness
- scenario results
- blockers
- next action

## Guardrails

- Separate environment issues from implementation issues.
- Keep the scenario list explicit and reproducible.

## Related Skills

- `implementation-acceptance`
- `release-verify`
