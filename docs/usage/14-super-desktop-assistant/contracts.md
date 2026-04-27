# Super Desktop Assistant 契约规范（V0）

本文定义客户端与编排层共享的数据契约，目标是统一多执行器任务的结构、事件和审批语义。  
约定：所有时间使用 ISO 8601 UTC，所有 ID 使用 UUIDv7（或等价全局唯一方案）。

## 1. Task Contract

```json
{
  "task_id": "task_01J...",
  "trace_id": "trace_01J...",
  "goal": "修复线上报错并提交 PR",
  "workspace_id": "ws_main_app",
  "status": "Running",
  "plan_revision": 3,
  "routing_policy": {
    "mode": "auto",
    "prefer_level_order": ["L3", "L2", "L1"],
    "allow_gui_fallback": false
  },
  "created_at": "2026-04-19T10:00:00Z",
  "updated_at": "2026-04-19T10:05:00Z"
}
```

`status` 枚举：

- `Draft`
- `Planned`
- `Running`
- `WaitingApproval`
- `Blocked`
- `Failed`
- `Succeeded`
- `RolledBack`

## 2. Node Contract

```json
{
  "node_id": "node_n3_fix_code",
  "task_id": "task_01J...",
  "name": "使用 qodercli 修复代码",
  "executor_type": "mature_cli",
  "connector_id": "qodercli_local",
  "mode": "interactive_pty",
  "depends_on": ["node_n2_root_cause"],
  "workspace_binding": "ws_main_app",
  "risk_level": "medium",
  "idempotency_key": "task_01J...:node_n3_fix_code:v3",
  "input_contract_ref": "schema://node/n3/input",
  "output_contract_ref": "schema://node/n3/output",
  "state": "Running"
}
```

`executor_type` 枚举：

- `desktop`
- `mature_cli`
- `mcp`
- `skill`
- `cts_cli`

`mode` 枚举：

- `managed`
- `interactive_pty`

`state` 枚举：

- `Pending`
- `Running`
- `WaitingApproval`
- `Blocked`
- `Failed`
- `Succeeded`
- `Skipped`

## 3. Handoff Packet Contract

```json
{
  "handoff_id": "handoff_01J...",
  "producer_node": "node_n2_root_cause",
  "consumer_nodes": ["node_n3_fix_code", "node_n4_precheck"],
  "payload_json": {
    "root_cause": "pydantic v1 validator incompatible",
    "fix_hints": ["migrate to field_validator"]
  },
  "artifacts": [
    {
      "type": "file",
      "uri": "artifact://task_01J.../root-cause.md",
      "sha256": "..."
    }
  ],
  "summary": "建议先迁移验证器，再运行回归测试",
  "evidence": {
    "event_refs": ["evt_101", "evt_102"],
    "checks_passed": ["schema_validation"]
  },
  "sensitivity": "internal"
}
```

`sensitivity` 枚举建议：

- `public`
- `internal`
- `restricted`
- `secret`

## 4. Approval Contract

```json
{
  "approval_id": "apr_01J...",
  "task_id": "task_01J...",
  "node_id": "node_n6_git_push",
  "action_type": "git_push",
  "risk_level": "high",
  "reason": "push to remote branch",
  "impact_scope": ["repo:main-app", "branch:feature/fix"],
  "rollback_hint": "git revert available",
  "status": "Pending",
  "requested_at": "2026-04-19T10:20:00Z",
  "resolved_at": null,
  "resolved_by": null
}
```

`status` 枚举：

- `Pending`
- `Approved`
- `Rejected`
- `Expired`

## 5. Event Contract

```json
{
  "event_id": "evt_01J...",
  "trace_id": "trace_01J...",
  "task_id": "task_01J...",
  "node_id": "node_n3_fix_code",
  "type": "tool.stdout",
  "ts": "2026-04-19T10:08:11Z",
  "source": "qodercli_local",
  "payload": {
    "chunk": "Applying patch ..."
  },
  "meta": {
    "plan_revision": 3,
    "workspace_id": "ws_main_app"
  }
}
```

`type` 最小集合：

- `task.started`
- `task.succeeded`
- `task.failed`
- `node.started`
- `node.succeeded`
- `node.failed`
- `tool.stdout`
- `tool.stderr`
- `file.patch.proposed`
- `approval.required`
- `approval.resolved`
- `plan.revision.created`

## 6. Plan Patch Contract

```json
{
  "patch_id": "patch_01J...",
  "task_id": "task_01J...",
  "from_revision": 3,
  "to_revision": 4,
  "ops": [
    {
      "op": "replace_executor",
      "node_id": "node_n3_fix_code",
      "from": "qodercli_local",
      "to": "codex_desktop"
    }
  ],
  "reason": "qodercli timeout",
  "requires_reapproval": false,
  "created_by": "system_router",
  "created_at": "2026-04-19T10:25:00Z"
}
```

`op` 建议集合：

- `add_node`
- `remove_node`
- `replace_executor`
- `change_dependency`
- `change_risk_level`
- `change_workspace_binding`

## 7. 错误码约定（最小集）

- `E_AUTH_FAILED`：鉴权失败
- `E_POLICY_DENIED`：策略拒绝
- `E_WORKSPACE_VIOLATION`：工作空间越界
- `E_CONNECTOR_UNAVAILABLE`：连接器不可用
- `E_EXECUTOR_TIMEOUT`：执行超时
- `E_APPROVAL_REJECTED`：审批拒绝
- `E_PLAN_CONFLICT`：计划补丁冲突

## 8. 版本与兼容

- 契约版本字段：`contract_version`，初始 `v1`
- 新增字段保持向后兼容，禁止无迁移删除字段
- 跨端升级策略：先服务端兼容新旧，再升级客户端
