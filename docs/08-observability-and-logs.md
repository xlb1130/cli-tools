# 日志与可观测性

## 1. 目标

`cts` 不是一个单纯执行命令的薄壳，而是一个统一能力平面。因此日志设计不能只考虑“命令执行成功没”，还要覆盖：

- 配置加载
- profile 解析
- source discover
- schema import / probe
- help 编译
- 执行与审计
- northbound surface 请求

## 2. 三类记录要分开

建议从第一天就区分三类。

### 2.1 App Log

用于研发调试和运行诊断。

特点：

- 结构化
- 记录更多上下文
- 支持 debug/trace

### 2.2 Audit Log

用于重要执行留痕和安全审计。

特点：

- 只记录关键事件
- 强调谁、何时、执行了什么
- 默认长期保留

### 2.3 Run History

用于前端页面和用户查看近期执行。

特点：

- 更接近“任务历史”
- 面向可视化查询
- 可存 SQLite

## 3. 日志事件模型

建议统一：

```python
class LogEvent(BaseModel):
    ts: datetime
    level: Literal["DEBUG", "INFO", "WARN", "ERROR", "AUDIT"]
    event: str
    run_id: str | None = None
    trace_id: str | None = None
    surface: str | None = None
    profile: str | None = None
    source: str | None = None
    mount_id: str | None = None
    operation_id: str | None = None
    message: str | None = None
    data: dict = {}
```

## 4. 必须记录的事件

## 4.1 配置阶段

- `config_load_start`
- `config_file_loaded`
- `config_file_failed`
- `config_merge_complete`
- `profile_resolved`

## 4.2 导入阶段

- `discover_start`
- `discover_complete`
- `schema_import_start`
- `schema_import_complete`
- `schema_probe_start`
- `schema_probe_blocked`
- `cache_hit`
- `cache_miss`

## 4.3 帮助编译阶段

- `help_compile_start`
- `help_compile_complete`

## 4.3.1 Hook 阶段

- `hook_dispatch_start`
- `hook_dispatch_complete`
- `hook_failed`

## 4.4 执行阶段

- `invoke_start`
- `invoke_complete`
- `invoke_failed`
- `policy_blocked`
- `timeout`

## 4.5 Surface 阶段

- `surface_request_start`
- `surface_request_complete`
- `surface_request_failed`

## 5. 日志字段建议

除了通用字段，建议补充：

- `config_files`
- `config_hash`
- `schema_strategy`
- `schema_confidence`
- `provider_type`
- `argv_preview`
- `request_preview`
- `duration_ms`
- `exit_code`
- `result_summary`

## 6. 日志输出格式

推荐：

- 控制台：人类友好的简洁文本
- 文件：`jsonl`
- 审计：`jsonl` 或 SQLite

默认文件建议：

- `app.jsonl`
- `audit.jsonl`
- `history.db`

## 7. 日志目录

建议使用：

- `~/.local/state/cts/logs/app.jsonl`
- `~/.local/state/cts/logs/audit.jsonl`
- `~/.local/share/cts/history.db`

## 8. 脱敏策略

必须默认脱敏：

- `Authorization`
- `X-API-Key`
- `token`
- `password`
- `secret`
- `api_key`

推荐规则：

- 保留字段名
- 值替换成 `***`
- 对长字符串做部分掩码

## 9. run_id 与 trace_id

每次用户触发的一次完整操作建议生成：

- `run_id`
- `trace_id`

如果有 workflow/composite operation：

- 整个 workflow 共用一个 `trace_id`
- 每个步骤可以有自己的 `run_id`

## 10. 前端怎么用

前端第一版不必做完整日志中心，但建议支持：

- Dashboard 展示最近一次 config reload
- 展示最近一次 sync
- 某条 mount 最近一次执行状态
- 按 `run_id` 查看最近一次 explain/invoke 摘要

第二版再考虑日志页。

## 11. 建议的前端接口

当前已经有的 northbound 查询入口：

```http
GET /api/runs
GET /api/runs/{run_id}
GET /api/logs/config
GET /api/logs/discovery
GET /api/logs/app
```

后续仍可再补更细的日志子资源和统一分页/过滤合同，但“前端完全不能查日志”这一点已经不成立。

## 12. 最终结论

`cts` 的日志不能只做“命令输出保存”，而应做成：

- 配置日志
- 导入日志
- 执行日志
- 审计日志
- 前端可查询的 run history

只有这样，`cts` 才真的适合作为长期可扩展的集成平台。
