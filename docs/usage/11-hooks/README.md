# Hooks

hook 用来在核心生命周期节点上插入、观察或改写行为。

当前已支持的事件族包括：

- `discovery.before|after|error`
- `help.before|after`
- `explain.before|after|error`
- `invoke.before|after|error`
- `surface.http.request.before|after|error`

## 什么时候应该用 hook

适合这些场景：

- 执行前改写参数
- 给帮助信息追加说明
- 加治理、审计或标记逻辑
- 在结果出来后再做补充处理
- 在不改 core provider 的情况下扩展行为

## 最小示例

下面这个例子做了两件事：

- 在 `explain` 和 `invoke` 前给 `text` 参数追加 `!`
- 在 `invoke` 结果上补一个 `"hooked": true`

配置：

```yaml
plugins:
  demo:
    path: ./demo_plugin.py
    config:
      suffix: "!"

hooks:
  - event: explain.before
    plugin: demo
    handler: suffix_text
  - event: invoke.before
    plugin: demo
    handler: suffix_text
  - event: invoke.after
    plugin: demo
    handler: mark_result
```

相关文件：

- [examples/cts.yaml](./examples/cts.yaml)
- [examples/demo_plugin.py](./examples/demo_plugin.py)

## 治理相关配置

hook 还支持这些控制项：

- `priority`：数字越小越早执行
- `when`：按 `mount_id`、`source`、`provider_type` 等上下文过滤
- `fail_mode`：`raise`、`warn`、`ignore`

这些选项很重要，因为 hook 一旦多起来，影响范围会很大。

## 常见模式

- `help.after`：给帮助输出追加组织级说明或风险提示
- `explain.before`：在计划阶段统一归一化参数
- `invoke.before`：在执行前补运行时信息或改写 args
- `invoke.after`：在标准结果上追加字段
- `*.error`：补充错误分类、日志和告警

## 相关参考

- Hook 事件合同定义在 [src/cts/plugins/contracts.py](../../../src/cts/plugins/contracts.py)
- plugin 相关扩展见 [10-plugins](../10-plugins/README.md)
