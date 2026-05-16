---
name: incident-diagnosis
description: Use when the user needs end-to-end production or test issue diagnosis, including symptom confirmation, evidence collection, root-cause analysis, impact validation, and repair or mitigation guidance.
---

# 问题诊断与排查

## When To Use

- 线上或测试环境出现故障
- 需要定位根因和影响范围
- 需要形成修复或止血建议

## Preconditions

- Run `app-context-init` if CTS environment is not ready.

## Inputs

- environment
- service
- time window
- symptom

## Workflow

1. Confirm environment, service, time window, and symptom.
2. Use `log-query` first to anchor evidence.
3. Use `data-management` to verify scope and samples.
4. Use `resource-management` for config, cache, jvm, and health evidence.
5. State root cause only after evidence converges.
6. Recommend fix, mitigation, or next discriminating check.

## Typical R&D Scenarios

### Scenario 1: 发布后核心接口报错率陡增

- Trigger: 发布后 5 到 15 分钟内错误率显著上升。
- Primary path: 先查日志，再对照发布批次、配置变更、缓存状态。
- Key questions:
  - 是所有流量都受影响，还是部分实例、部分租户受影响
  - 是代码回归、配置漂移，还是脏缓存导致
- Expected output: 根因结论、影响范围、回滚还是修复的建议。

### Scenario 2: 偶发超时但无法稳定复现

- Trigger: 用户反馈偶发超时，压测和联调环境无法复现。
- Primary path: 用时间窗聚合日志，交叉验证慢 SQL、缓存命中、线程或连接池状态。
- Key questions:
  - 问题是否与流量峰值、特定请求参数、特定实例有关
  - 是性能瓶颈还是下游依赖抖动
- Expected output: 竞争性假设列表和下一步判别手段。

### Scenario 3: 单租户或单客户异常

- Trigger: 问题只发生在单租户、单渠道或少量账号。
- Primary path: 以业务键为中心串数据、缓存、配置。
- Key questions:
  - 是否存在租户级配置差异
  - 是否存在历史脏数据或缓存污染
- Expected output: 精确影响对象和最小化修复路径。

## Core MCP Usage

This skill should orchestrate calls instead of owning config:

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json call grafana <log_tool> '{"service":"order","query":"timeout"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call mysql <query_tool> '{"sql":"select id,status from orders where id=123"}'
mcp-cli -c ~/.config/mcp/mcp_servers.json call redis <cache_tool> '{"key":"order:123"}'
```

Core scenes:

- 先用日志定位异常时间窗
- 再用数据确认影响范围
- 再用缓存、配置或运行资源交叉验证根因

## Output Contract

- symptom
- impact scope
- evidence
- root cause or hypotheses
- fix or mitigation

## Guardrails

- Do not claim root cause without direct evidence.
- Separate facts, hypotheses, and mitigation clearly.

## Related Skills

- `log-query`
- `data-management`
- `resource-management`
- `alert-response-containment`
