---
name: performance-baseline
description: Use when the user needs performance baseline definition, latency comparison, throughput drift analysis, or stage duration regression checks across automation or delivery workflows.
---

# 性能基线

## When To Use

- 需要定义或校验耗时基线
- 怀疑发布后出现性能回归
- 需要对比版本或阶段耗时差异

## Preconditions

- Prefer `app-context-init` if common tracking assets are required.

## Inputs

- environment
- service or workflow name
- metric names
- baseline window and comparison window

## Workflow

1. Confirm the metric and time window.
2. Read the baseline definition and current measurement.
3. Compare current values against threshold and variance.
4. Highlight regressions, outliers, and likely bottlenecks.

## Typical R&D Scenarios

### Scenario 1: 发布前建立性能基线

- Trigger: 核心服务准备进入高风险发布或大版本切换。
- Focus: 先定义正常值区间，再谈是否退化。
- Output: 基线值、阈值、发布后观察指标。

### Scenario 2: 发布后性能回归判断

- Trigger: 功能正确，但耗时或吞吐出现明显变化。
- Focus: 区分正常波动和真实退化。
- Output: 是否回归、影响程度、可能瓶颈点。

## Core MCP Usage

Typical alias usage:

- `grafana`: metrics, dashboards, alerts
- `mysql`: data-side volume or latency correlation

Example patterns:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json info grafana
mcp-cli -c ~/.config/mcp/mcp_servers.json grep "*metric*"
mcp-cli -c ~/.config/mcp/mcp_servers.json call grafana <metric_tool> '{"service":"order","metric":"p95_latency","window":"1h"}'
```

## Output Contract

- baseline
- current measurement
- deviation
- conclusion
- next check

## Guardrails

- Separate measurement noise from real regression.
- State the confidence level when the sample is small.

## Related Skills

- `resource-management`
- `release-verify`
