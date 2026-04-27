# Super Desktop Assistant 可靠性与恢复规范（V0/V1）

本文定义任务执行中的重试、补偿、恢复和 SLO 基线，确保多执行器协作在失败情况下可控可恢复。

## 1. 设计目标

- 失败后优先“局部恢复”，避免全任务重跑
- 对外部副作用操作强制幂等与补偿策略
- 审批等待和长任务恢复具备耐久性
- 所有恢复动作可审计、可回放

## 2. 节点分类与策略矩阵

### 2.1 节点类型

- `ReadOnly`：读取查询类（如 MCP 查询日志）
- `Compute`：纯计算类（如 Skill 分析）
- `MutatingLocal`：本地可变更（如代码修改、文件写入）
- `MutatingRemote`：远端副作用（如发布、push、创建工单）

### 2.2 重试与补偿策略

| 节点类型 | 默认重试 | 幂等要求 | 失败补偿 | 说明 |
|---|---|---|---|---|
| ReadOnly | 3 次指数退避 | 可选 | 无 | 查询失败可直接重试 |
| Compute | 2 次 | 可选 | 无 | 推理失败可切模型/执行器 |
| MutatingLocal | 1 次 + 人工确认 | 建议 | 回滚到快照 | 避免重复写文件 |
| MutatingRemote | 默认不自动重试 | 必须 | 必须 | 防止重复副作用 |

> 对 `MutatingRemote` 节点，若缺少幂等键则必须进入人工确认。

## 3. 幂等键规范

幂等键建议格式：

`{task_id}:{node_id}:{plan_revision}:{attempt}`

要求：

- 所有远端副作用调用必须带幂等键
- 连接器层需透传或模拟幂等语义
- 幂等冲突返回 `E_PLAN_CONFLICT` 或等价错误，交由编排层处理

## 4. 补偿动作规范

每个 `MutatingRemote` 节点必须定义 `compensation_action`，例如：

- `git push` -> `git revert` 或撤销 PR
- 创建发布任务 -> 调用取消发布 API
- 创建工单 -> 关闭工单并标记来源任务

补偿触发时机：

- 下游关键节点失败且策略为“强一致回滚”
- 用户手动触发“回滚任务”
- 审批拒绝导致不可继续

## 5. 恢复模式

- `ResumeFromNode`：从失败节点继续
- `ReplayDownstream`：失败节点及其下游重跑
- `SwitchExecutorAndRetry`：切执行器后重跑
- `RetryInSandbox`：复制上下文后沙箱重跑
- `ManualTakeover`：人工完成后回填结果再推进 DAG

## 6. 审批等待可靠性

- 审批状态必须持久化（Temporal durable wait）
- 审批超时后进入 `Expired`，并按策略：
  - 中断当前节点
  - 或降级为沙箱 dry-run
- 审批恢复后必须记录 `resolved_by`、`resolved_at`、`decision_reason`

## 7. PTY 会话故障恢复

- 前端断连：PTY 进入 `Detached`，默认保活 N 分钟
- 重连后补发断连期间输出摘要
- 进程卡死：支持 `SIGINT -> SIGTERM -> kill` 三级处理
- 无法恢复时切换到 `managed` 模式或建议人工接管

## 8. 计划修订冲突处理

- Patch 基于 `from_revision` 乐观并发控制
- 不匹配当前 revision 时拒绝提交并返回冲突
- 用户可选择：
  - 重新基于最新 revision 生成 patch
  - 锁定当前 plan 暂停自动修订

## 9. SLO 建议（首版）

- 任务启动时延 P95 < 3s
- 节点状态变更到 UI 可见时延 P95 < 1s
- 审批通过后恢复执行时延 P95 < 2s
- 节点级恢复成功率 >= 95%
- PTY 会话重连成功率 >= 98%

## 10. 可观测性字段（最低要求）

每个节点事件必须带：

- `task_id`、`trace_id`、`node_id`
- `executor_type`、`connector_id`
- `attempt`、`plan_revision`
- `idempotency_key`（如适用）
- `error_code`、`error_message`（失败时）

## 11. 运行手册（值班最小清单）

- 审批积压超过阈值自动告警
- 连接器健康检查失败率超过阈值自动降级
- 任务失败进入三类归因：策略问题/连接器问题/模型问题
- 一键导出失败链路（事件流 + 节点输入输出 + 审批记录）
