---
name: log-query
description: Use when the user needs log-based evidence through CTS, including error clustering, time-window analysis, release regression checks, trace lookup, or incident evidence collection.
---

# 日志查询

## When To Use

- 需要按时间窗搜日志
- 需要定位错误模式或异常峰值
- 需要发布前后日志对比

## Preconditions

- Run `app-context-init` if the environment is not initialized.

## Inputs

- environment
- service
- time window
- keywords or trace id

## Workflow

1. Anchor the time window first.
2. Search for the main error or symptom keywords.
3. Group by service, instance, or error pattern when possible.
4. Extract representative evidence and likely next checks.

## Typical R&D Scenarios

### Scenario 1: 发布后错误日志对比

- Trigger: 发布刚结束，需要判断是否出现回归。
- Focus: 同一接口在发布前后错误模式、错误率、实例分布是否变化。
- Output: 代表性异常模式和是否建议继续观察、回滚或放行。

### Scenario 2: 线上问题初筛

- Trigger: 收到告警或业务投诉，但问题还很模糊。
- Focus: 用最小时间窗和关键词先建立事实面，不急着下结论。
- Output: 主要错误模式、影响服务、下一步应该查数据还是查资源。

### Scenario 3: Trace 定位单次故障

- Trigger: 已知 trace id、request id 或订单号。
- Focus: 快速拼出单次请求的异常链路。
- Output: 单次故障路径和关键证据。

## Core MCP Usage

Prepare the server alias in `app-context-init` first, then use:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json info grafana
mcp-cli -c ~/.config/mcp/mcp_servers.json grep "*log*"
mcp-cli -c ~/.config/mcp/mcp_servers.json call grafana <log_tool> '{"service":"order","from":"2026-05-16T10:00:00+08:00","to":"2026-05-16T11:00:00+08:00","query":"error"}'
```

Core scenes:

- 按时间窗检索错误日志
- 按服务或实例聚类异常
- 按 trace id 或关键词提取代表性证据

## Output Contract

- time window
- key patterns
- affected services or instances
- representative evidence

## Guardrails

- Do not paste excessive raw logs.
- Prefer clustered findings over long raw dumps.

## Related Skills

- `incident-diagnosis`
- `release-verify`
