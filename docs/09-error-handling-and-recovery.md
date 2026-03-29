# 错误处理与恢复

## 1. 为什么要单独设计

对于 `cts` 这种多协议、多 provider、可被人类和 AI 同时调用的平台，错误处理不能只理解成：

- 抛异常
- 打印一段报错
- 返回非 0 退出码

它至少还要回答这些问题：

- 这是什么类型的错误
- 是用户问题、配置问题、上游问题，还是平台 bug
- 可不可以重试
- 应该自动重试还是提示人工处理
- 工作流跑到一半失败怎么办
- CLI、HTTP、MCP、前端看到的错误是否一致

## 2. 现有设计已经有的基础

当前文档里已经有：

- 统一错误分类基础
- 结构化错误 JSON
- run_id / trace_id
- 日志与审计

但还缺少“恢复语义”和“错误合同”的细化。

## 3. 错误处理要覆盖的 5 层

### 3.1 Config 层

例如：

- YAML 语法错误
- profile 不存在
- source 引用缺失
- mount 冲突

### 3.2 Discovery / Import 层

例如：

- schema 拉取失败
- probe 被策略阻止
- 上游接口 metadata 不可用
- schema 漂移导致旧映射失效

### 3.3 Execution 层

例如：

- 参数校验失败
- 鉴权失败
- provider 调用失败
- 超时
- 限流

### 3.4 Workflow 层

例如：

- 第 3 步失败但前 2 步已经成功
- 补偿失败
- 中间结果不满足下一步输入要求

### 3.5 Surface 层

例如：

- HTTP gateway 返回 500
- MCP bridge tool call 失败
- 前端调用 explain 失败

## 4. 建议的统一错误模型

建议把错误对象稳定成下面这类结构：

```python
class ErrorEnvelope(BaseModel):
    ok: bool = False
    error: "ErrorInfo"
    run_id: str | None = None
    trace_id: str | None = None

class ErrorInfo(BaseModel):
    type: str
    code: str
    message: str
    retryable: bool = False
    user_fixable: bool = False
    stage: str | None = None
    source: str | None = None
    mount_id: str | None = None
    operation_id: str | None = None
    provider_type: str | None = None
    details: dict = {}
    suggestions: list[str] = []
    raw_cause: dict | None = None
```

这里最关键的是：

- `type` 适合程序分类
- `code` 必须稳定
- `retryable` 决定是否自动重试
- `user_fixable` 决定是否直接给用户修复建议
- `suggestions` 给 CLI/前端/AI 统一展示

## 5. 错误分类建议

建议细分为：

- `ConfigError`
- `ProfileError`
- `RegistryError`
- `DiscoveryError`
- `SchemaImportError`
- `SchemaDriftError`
- `ValidationError`
- `PolicyError`
- `AuthError`
- `RateLimitError`
- `TimeoutError`
- `ProviderError`
- `ExecutionError`
- `WorkflowError`
- `PartialFailureError`
- `HookError`
- `SurfaceError`
- `CatalogError`
- `InternalError`

## 6. 不只是类型，还要有恢复属性

错误除了类型，还应带恢复维度：

### 6.1 是否可重试

- `retryable=true/false`

### 6.2 谁来修

- `user_fixable`
- `operator_fixable`
- `system_bug`

### 6.3 是否可降级

例如：

- schema 拉取失败，但还能用旧 cache
- help 编译失败，但仍可执行

### 6.4 是否部分成功

对于 workflow，必须能表达：

- 哪些步骤成功
- 哪些步骤失败
- 是否进行了补偿

## 7. 退出码设计

CLI 层建议给稳定退出码，不然脚本和 CI 很难依赖。

建议例如：

- `2` 配置错误
- `3` 参数错误
- `4` 鉴权错误
- `5` 策略阻止
- `6` 上游 provider 错误
- `7` 超时
- `8` 部分失败
- `9` hook / 内部执行错误

具体值可以后面调整，但要尽早固定。

当前 MVP 已落地：

- `ConfigError -> 2`
- `RegistryError -> 2`
- `ValidationError -> 3`
- `AuthError -> 4`
- `PolicyError -> 5`
- `ProviderError -> 6`
- `TimeoutError -> 7`
- `HookError -> 9`
- 未分类内部错误 -> 9

## 8. 人类、机器、前端三种错误输出

### 8.1 人类 CLI

要求：

- 短消息
- 明确下一步建议
- 显示 run_id

### 8.2 AI / 机器模式

要求：

- 结构化 JSON
- 稳定 `type/code`
- 不混入多余提示文案

### 8.3 前端页面

要求：

- 展示主错误
- 展示 `suggestions`
- 能看到 run_id
- 能链接到近期日志/历史

## 9. 原始错误保留策略

Provider 原始错误不能直接丢给用户，但也不能完全丢掉。

建议：

- 归一化为统一错误对象
- 同时在 `raw_cause` 或日志里保留摘要
- 对敏感字段做脱敏

## 10. 自动重试边界

错误处理必须和可靠性策略配套。

建议默认：

- `TimeoutError` 可选自动重试
- `RateLimitError` 按 backoff 重试
- `AuthError` 可尝试 refresh 后重试一次
- `ValidationError` 不重试
- `PolicyError` 不重试
- `ConfigError` 不重试
- `HookError` 默认不重试，是否中断主流程取决于 hook `fail_mode`

当前实现补充：

- `fail_mode=warn` 会记录 hook failure 日志并继续主流程
- `fail_mode=ignore` 会吞掉 hook 异常但不改主流程结果
- `fail_mode=raise` 会返回结构化 `HookError`

## 11. Workflow / Composite 的特别处理

这是最容易被忽略的一块。

建议 workflow 错误额外包含：

- `failed_step`
- `completed_steps`
- `compensation_attempted`
- `compensation_status`

例如：

```json
{
  "ok": false,
  "error": {
    "type": "PartialFailureError",
    "code": "workflow_step_failed",
    "message": "Step 3 failed after 2 successful steps",
    "details": {
      "failed_step": "jira.create_issue",
      "completed_steps": ["github.list_issues", "filter.issues"],
      "compensation_attempted": false
    }
  }
}
```

## 12. 配置和导入失败也要可恢复

这类错误常被忽略，但对平台很重要。

例如：

- 配置文件损坏时，是否还能加载全局配置
- schema probe 失败时，是否回退到缓存
- OpenAPI 拉取失败时，是否回退到上次成功版本

建议每类错误都明确：

- fail closed
- fail open
- fallback to cache

## 13. 前端 API 需要的错误字段

前端不只需要 `message`，还建议拿到：

- `type`
- `code`
- `retryable`
- `user_fixable`
- `suggestions`
- `run_id`

## 14. Phase 1 最少要补到什么程度

第一版至少建议做到：

- 稳定 `type/code`
- 结构化 JSON 错误
- CLI 稳定退出码
- run_id
- `retryable` / `user_fixable`
- workflow 先支持 `PartialFailureError` 结构预留

## 15. 最终结论

错误处理这一块不仅需要额外考虑，而且应该被视为平台级能力。

对 `cts` 来说，真正成熟的标准不是“成功时能跑起来”，而是：

- 失败时能解释
- 失败时能定位
- 失败时能恢复
- 失败时不会把不同 surface 搞成不同语义
