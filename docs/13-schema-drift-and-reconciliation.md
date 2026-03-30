# Schema 漂移与对账

## 1. 为什么“导入”之后还需要单独一层“漂移治理”

导入只回答一个问题：

- 今天我们拿到了什么 operation 和参数 schema

但平台真正长期运行后，会遇到另一个问题：

- 明天上游变了怎么办

对于 `cts` 这种会长期挂载 API、MCP、CLI、plugin 的平台，schema 漂移不是偶发现象，而是常态。

## 2. 什么叫 schema 漂移

不仅仅是 JSON Schema 改了才算漂移。

建议把下面这些都视为 drift：

- operation 被删除
- operation 重命名
- 新增必填参数
- 参数类型变化
- 默认值变化
- 返回结构 breaking change
- CLI 参数名称变化
- CLI `--help` 文案和实际行为不一致
- MCP tool 描述、schema 或 server identity 变化

## 3. 漂移来源分类

## 3.1 上游 API 变更

例如：

- OpenAPI spec 升级
- GraphQL schema 增删字段
- 手工 HTTP endpoint 改参数要求

## 3.2 CLI 版本变更

例如：

- `gh` 升级后参数变化
- `kubectl` 某子命令行为变化
- 某内部 CLI 新增强制 flag

## 3.3 MCP server 变更

例如：

- tool 名称变化
- input schema 变化
- prompt/resource 行为变化

## 3.4 本地配置与缓存失配

例如：

- mount 仍引用旧 operation id
- 本地 cache 还是旧 schema
- 手工 override 已经过时

## 4. 应记录哪些指纹

为了做 drift detection，建议从第一天起记录 fingerprint。

例如：

- `operation_fingerprint`
- `input_schema_hash`
- `output_schema_hash`
- `provider_version`
- `api_version`
- `binary_version`
- `spec_etag`
- `server_identity`

对于 CLI，还建议记录：

- 可执行文件路径
- `--version` 输出摘要
- manifest 版本

## 5. 漂移检测流程建议

## 5.1 Snapshot

每次 `sync`、`discover` 或 schema probe 后，保存最新 snapshot。

## 5.2 Diff

和上一版 snapshot 对比，识别：

- additive change
- compatible change
- potentially breaking change
- confirmed breaking change

当前 MVP 已落地：

- `cts sync` 会在每个 source 上输出基础 drift 分类
- `cts inspect drift [source]` 可读取最近一次 sync report 中的 drift 结果
- breaking drift 已支持 mount 级治理决策
- 已支持基础 `cts reconcile drift <source>`
- 当前已支持：
  - `initial`
  - `unchanged`
  - `compatible`
  - `additive`
  - `breaking`
- 当前 diff 规则已覆盖：
  - operation 新增 / 删除
  - `stable_name` 变化
  - risk 变化
  - `supported_surfaces` 增删
  - input schema 中的参数新增 / 删除
  - 参数 required 状态变化
  - 参数类型变化
  - enum/default 变化
- 当前治理规则已覆盖：
  - 顶层 `drift.defaults.on_breaking_change`
  - 顶层 `drift.defaults.on_additive_change`
  - 顶层 `drift.defaults.on_compatible_change`
  - source 级 `drift_policy.on_breaking_change`
  - source 级 `drift_policy.on_additive_change`
  - source 级 `drift_policy.on_compatible_change`
  - mount 级 `drift_policy.on_breaking_change`
  - mount 级 `drift_policy.on_additive_change`
  - mount 级 `drift_policy.on_compatible_change`
  - `accept_additive_changes`
  - `accept_compatible_changes`
  - `freeze_mount`
  - `require_manual_review`
  - `warn`
  - `auto_accept`
- 当前运行时效果：
  - `inspect mount` / `--help` 会显示 mount 的 drift 状态
  - `invoke` 会对 `frozen` / `review_required` mount 返回 `PolicyError`
  - `reconcile drift` 可把当前 source 的 breaking drift 标记为已接受，并解除运行时阻断
  - `catalog export` / `/api/catalog` / `/api/drift` 会暴露 drift 与治理状态
  - additive / compatible drift 已可按 top-level、source、mount 三层策略自动接受
  - 自动接受后 mount 会显示 `status=accepted`
  - 当一个 source 的本轮 drift 全部被自动接受时，source 会显示 `status=accepted`
- 当前 impact analysis 已覆盖：
  - `affected_mount_ids`
  - `affected_aliases`
  - `blocked_mount_ids`
  - `accepted_mount_ids`
  - `affected_mount_count`
  - `blocked_mount_count`
  - `accepted_mount_count`

当前仍未完成：

- 更完整的 workflow / cross-surface 影响分析
- 更细粒度的人工对账工作流

## 5.3 Impact Analysis

继续分析：

- 哪些 source 受影响
- 哪些 mount 受影响
- 哪些 alias / workflow 步骤受影响
- 哪些 northbound surface 受影响

## 5.4 Reconcile

根据策略决定：

- 自动接受
- 标记 warning
- 冻结执行
- 等待人工确认

## 6. 漂移策略建议

建议顶层增加：

```yaml
drift:
  defaults:
    detect_on_sync: true
    classify_breaking_changes: true
    on_breaking_change: freeze_mount
    on_additive_change: auto_accept
```

source 级可以覆盖：

```yaml
sources:
  github_mcp:
    type: mcp
    drift_policy:
      detect_via:
        - discovery
        - schema_probe
      on_missing_operation: warn_and_keep_cached
      on_breaking_change: require_manual_review
```

mount 级也建议支持：

```yaml
mounts:
  - id: gh-repo-list
    source: gh_cli
    operation: repo_list
    drift_policy:
      pin_operation_fingerprint: "sha256:abcd..."
      accept_additive_changes: true
      accept_compatible_changes: true
      on_breaking_change: disable_mount
```

## 7. 自动对账的边界

不是所有 drift 都适合自动修。

## 7.1 可自动接受的变化

例如：

- 新增可选参数
- 补充 description / examples
- 非破坏性的 help 文案改动

## 7.2 需要人工确认的变化

例如：

- 新增必填参数
- 参数类型改变
- operation 风险级别改变
- 写操作变成 destructive

## 7.3 默认冻结的变化

例如：

- operation 删除
- stable_name 语义改变
- workflow 依赖步骤缺失

## 8. CLI、MCP、HTTP 的特别策略

## 8.1 CLI

因为 CLI 缺乏统一 schema 标准，建议：

- manifest-first
- `--help` / completion 只作为辅助证据
- 二进制版本变化时优先触发 drift check

## 8.2 MCP

建议：

- 区分 tool、prompt、resource 三类漂移
- 对 write/destructive tool 的 drift 更保守
- 支持通过 `mcp-cli` 重新 probe 获取新 schema

## 8.3 手工 HTTP

手工 HTTP 最难自动对账。

建议：

- 依赖人工维护的 schema override
- 当返回 400/422 模式突然变化时标记 suspected drift
- 支持把真实失败样本回灌给导入层

## 9. 对动态 `--help` 和前端页面的影响

漂移不只是执行问题，也会影响：

- 帮助信息
- 表单生成
- capability card
- catalog export

所以当 drift 发生时，前端和 `--help` 都应显示：

- 当前 schema 状态
- 来源
- 置信度
- 是否与最新上游一致

## 10. 建议的命令

- `cts sync`
- `cts inspect drift`
- `cts reconcile drift`

按当前代码状态，更贴近现状的检查入口是：

- `cts inspect operation <source> <operation>`
- `cts inspect mount <mount-id>`
- `cts doctor`

未来还可以加：

- `cts sync --check-drift`
- `cts inspect schema <mount-id>`
- `cts doctor mounts`
- `cts sync --accept-additive`

## 11. 日志与审计要求

建议新增事件：

- `drift_check_start`
- `drift_detected`
- `drift_classified`
- `drift_auto_accepted`
- `drift_mount_frozen`
- `drift_manual_review_required`
- `drift_reconciled`

建议记录字段：

- `previous_fingerprint`
- `current_fingerprint`
- `drift_type`
- `severity`
- `affected_mounts`
- `reconcile_action`

## 12. 对 AI 与自动化系统的特殊要求

AI 最怕的一类问题是：

- 昨天还能调，今天悄悄坏了

因此建议 northbound 输出里明确暴露：

- schema 是否 stale
- 最近一次 drift check 时间
- 当前 mount 是否被冻结
- 如果被冻结，替代 mount 是什么

## 13. 最终建议

漂移治理的关键不是“多做一次 sync”，而是把上游变化纳入正式生命周期：

- 发现
- 分类
- 影响分析
- 决策
- 对账

只有这样，`cts` 才能长期承载多种 API、MCP、CLI 和 plugin，而不是越接越脆。
