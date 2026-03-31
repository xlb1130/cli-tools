# Hooks

Hook 用来在核心生命周期节点上插入、观察或改写行为。

## 快速上手

### 1. 创建带 Hooks 的插件

创建 `my_hooks_plugin.py`：

```python
from cts.models import ExecutionPlan, InvokeResult, OperationDescriptor, HelpDescriptor


class EchoProvider:
    provider_type = "hook_echo"

    def discover(self, source_name, source_config, app):
        operations = []
        for op_id, op in source_config.operations.items():
            operations.append(
                OperationDescriptor(
                    id=op_id,
                    source=source_name,
                    provider_type=self.provider_type,
                    title=op.title or op_id,
                    description=op.description,
                    input_schema=dict(op.input_schema),
                )
            )
        return operations

    def get_operation(self, source_name, source_config, operation_id, app):
        return app.source_operations.get(source_name, {}).get(operation_id)

    def get_schema(self, source_name, source_config, operation_id, app):
        op = self.get_operation(source_name, source_config, operation_id, app)
        return (op.input_schema, {"strategy": "declared"}) if op else None

    def get_help(self, source_name, source_config, operation_id, app):
        op = self.get_operation(source_name, source_config, operation_id, app)
        return HelpDescriptor(summary=op.title, description=op.description) if op else None

    def refresh_auth(self, source_name, source_config, app):
        return None

    def plan(self, source_name, source_config, request, app):
        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk="read",
        )

    def invoke(self, source_name, source_config, request, app):
        return InvokeResult(
            ok=True,
            status_code=0,
            data={"args": dict(request.args)},
        )

    def healthcheck(self, source_name, source_config, app):
        return {"ok": True}


class Plugin:
    def __init__(self, plugin_name=None, config=None):
        self.plugin_name = plugin_name or "my_hooks"
        self.config = config or {}

    def register_providers(self):
        return {"hook_echo": EchoProvider()}

    def get_hook_handlers(self):
        """注册所有 Hook 处理函数"""
        return {
            "add_suffix": self.add_suffix,
            "mark_result": self.mark_result,
            "append_help_note": self.append_help_note,
            "log_error": self.log_error,
        }

    # ============ Hook 处理函数 ============

    def add_suffix(self, ctx):
        """Hook: 在执行前给参数添加后缀"""
        payload = dict(ctx.payload)
        args = dict(payload.get("args", {}))
        if "text" in args:
            suffix = self.config.get("suffix", "!")
            args["text"] = args["text"] + suffix
        payload["args"] = args
        return payload  # 返回修改后的 payload

    def mark_result(self, ctx):
        """Hook: 在结果中添加标记"""
        payload = dict(ctx.payload)
        result = dict(payload.get("result", {}))
        data = dict(result.get("data") or {})
        data["hooked"] = True
        data["hook_plugin"] = self.plugin_name
        result["data"] = data
        payload["result"] = result
        return payload

    def append_help_note(self, ctx):
        """Hook: 在帮助信息后追加说明"""
        payload = dict(ctx.payload)
        help_obj = dict(payload.get("help", {}))
        note = self.config.get("help_note", "")
        if note:
            existing = help_obj.get("description", "")
            help_obj["description"] = f"{existing}\n\n{note}".strip()
        payload["help"] = help_obj
        return payload

    def log_error(self, ctx):
        """Hook: 记录错误信息"""
        payload = dict(ctx.payload)
        error = payload.get("error")
        print(f"[Hook] Error occurred: {error}")
        # 不返回 payload，表示不做修改
```

### 2. 配置 cts.yaml

```yaml
version: 1

plugins:
  my_hooks:
    path: ./my_hooks_plugin.py
    config:
      suffix: " 🎉"
      help_note: "Powered by my_hooks plugin"

hooks:
  # 执行前改写参数
  - event: invoke.before
    plugin: my_hooks
    handler: add_suffix

  # 执行后标记结果
  - event: invoke.after
    plugin: my_hooks
    handler: mark_result

  # 帮助信息追加说明
  - event: help.after
    plugin: my_hooks
    handler: append_help_note

  # 错误处理
  - event: invoke.error
    plugin: my_hooks
    handler: log_error

sources:
  my_source:
    type: hook_echo
    operations:
      echo:
        title: Echo
        description: Echo your text
        input_schema:
          type: object
          properties:
            text:
              type: string
          required: [text]

mounts:
  - id: my-echo
    source: my_source
    operation: echo
    command:
      path: [test, echo]
```

### 3. 测试

```bash
# 查看帮助（会追加 help_note）
cts test echo --help

# 执行命令（会添加后缀和标记）
cts test echo --text "Hello"
# 输出: {"args": {"text": "Hello 🎉"}, "hooked": true, "hook_plugin": "my_hooks"}
```

## Hook 事件一览

| 事件 | 阶段 | 描述 | 可修改字段 |
|------|------|------|------------|
| `discovery.before` | before | Provider discovery 开始前 | `source_config`, `provider`, `runtime` |
| `discovery.after` | after | Provider discovery 完成后 | `operations` |
| `discovery.error` | error | Provider discovery 失败时 | - |
| `help.before` | before | 命令帮助编译前 | `provider_help`, `schema_info` |
| `help.after` | after | 帮助编译完成后 | `help` |
| `explain.before` | before | explain 计划生成前 | `args`, `runtime` |
| `explain.after` | after | explain 成功后 | `result` |
| `explain.error` | error | explain 失败后 | - |
| `invoke.before` | before | 实际执行前 | `args`, `runtime` |
| `invoke.after` | after | 执行成功后 | `result` |
| `invoke.error` | error | 执行失败后 | - |
| `surface.http.request.before` | before | HTTP 请求路由前 | - |
| `surface.http.request.after` | after | HTTP 请求完成后 | - |
| `surface.http.request.error` | error | HTTP 请求失败时 | - |

## Hook 配置详解

### 完整配置项

```yaml
hooks:
  - event: invoke.before          # 必填：事件名
    plugin: my_hooks              # 必填：插件名
    handler: add_suffix           # 必填：处理函数名
    enabled: true                 # 可选：是否启用，默认 true
    priority: 100                 # 可选：优先级，数字越小越早执行，默认 100
    fail_mode: warn               # 可选：失败处理方式，默认 warn
    when:                         # 可选：条件过滤
      mount_id: my-echo
      source: my_source
    config:                       # 可选：传给 handler 的配置
      extra: value
```

### fail_mode 选项

| 值 | 说明 |
|----|------|
| `raise` | 抛出异常，中断执行链 |
| `warn` | 打印警告，继续执行下一个 hook |
| `ignore` | 静默忽略，继续执行 |

### when 条件过滤

支持多种匹配模式：

```yaml
hooks:
  # 精确匹配
  - event: invoke.before
    plugin: my_plugin
    handler: my_handler
    when:
      mount_id: my-mount
      source: my_source
      provider_type: http

  # 通配符匹配
  - event: invoke.before
    plugin: my_plugin
    handler: my_handler
    when:
      mount_id:
        glob: "demo-*"

  # 列表匹配
  - event: invoke.before
    plugin: my_plugin
    handler: my_handler
    when:
      source:
        in: [source1, source2, source3]

  # 存在性检查
  - event: invoke.before
    plugin: my_plugin
    handler: my_handler
    when:
      runtime:
        exists: true

  # 否定匹配
  - event: invoke.before
    plugin: my_plugin
    handler: my_handler
    when:
      provider_type:
        not: cli
```

## Hook 上下文 (HookContext)

Hook 处理函数接收一个 `HookContext` 对象：

```python
from cts.plugins import HookContext

def my_handler(ctx: HookContext):
    ctx.event          # 事件名，如 "invoke.before"
    ctx.plugin_name    # 插件名
    ctx.plugin_config  # 插件配置 (PluginConfig)
    ctx.hook_config    # Hook 配置 (HookConfig)
    ctx.payload        # 当前 payload (可变字典)
    ctx.app            # CTSApp 实例
```

### 返回值约定

```python
def my_handler(ctx):
    # 方式1: 返回修改后的 payload（链式传递）
    payload = dict(ctx.payload)
    payload["args"]["extra"] = "value"
    return payload

    # 方式2: 返回 None 或不返回（不做修改）
    # return None
```

## 常见使用场景

### 1. 参数预处理

```yaml
hooks:
  - event: invoke.before
    plugin: my_plugin
    handler: normalize_args
    when:
      mount_id: api-call
```

```python
def normalize_args(self, ctx):
    payload = dict(ctx.payload)
    args = payload.get("args", {})
    # 统一转换参数格式
    if "date" in args:
        args["date"] = self._parse_date(args["date"])
    payload["args"] = args
    return payload
```

### 2. 结果增强

```yaml
hooks:
  - event: invoke.after
    plugin: my_plugin
    handler: add_metadata
```

```python
def add_metadata(self, ctx):
    payload = dict(ctx.payload)
    result = dict(payload.get("result", {}))
    result["metadata"] = {
        "plugin": self.plugin_name,
        "timestamp": datetime.now().isoformat(),
    }
    payload["result"] = result
    return payload
```

### 3. 审计日志

```yaml
hooks:
  - event: invoke.before
    plugin: audit
    handler: log_request
    priority: 1  # 最先执行

  - event: invoke.after
    plugin: audit
    handler: log_response

  - event: invoke.error
    plugin: audit
    handler: log_error
```

### 4. 帮助信息增强

```yaml
hooks:
  - event: help.after
    plugin: my_plugin
    handler: add_risk_warning
```

```python
def add_risk_warning(self, ctx):
    payload = dict(ctx.payload)
    help_obj = dict(payload.get("help", {}))
    mount = ctx.payload.get("mount")

    if mount and hasattr(mount, "operation"):
        op = mount.operation
        if op.risk == "write":
            warning = "\n\n⚠️ WARNING: This operation modifies data."
            help_obj["description"] = help_obj.get("description", "") + warning

    payload["help"] = help_obj
    return payload
```

### 5. 条件执行

```yaml
hooks:
  # 只对特定 mount 生效
  - event: invoke.before
    plugin: my_plugin
    handler: inject_auth
    when:
      mount_id: protected-api

  # 只对特定 provider 生效
  - event: invoke.after
    plugin: my_plugin
    handler: cache_result
    when:
      provider_type: http
```

## 执行顺序

Hook 按 `priority` 从小到大执行，相同 priority 按配置文件顺序：

```yaml
hooks:
  - event: invoke.before
    plugin: a
    handler: h1
    priority: 100  # 第2个执行

  - event: invoke.before
    plugin: b
    handler: h2
    priority: 50   # 第1个执行

  - event: invoke.before
    plugin: c
    handler: h3
    priority: 100  # 第3个执行（同 priority，按配置顺序）
```

## 什么时候用 Hook

适合场景：
- 执行前改写参数
- 给帮助信息追加说明
- 加治理、审计或标记逻辑
- 在结果出来后再做补充处理
- 在不改 core provider 的情况下扩展行为

不适合场景：
- 需要全新的 provider type → 用 [Plugin Provider](../10-plugins/README.md)
- 简单的命令调用 → 用内置 Provider

## 示例文件

- [examples/cts.yaml](./examples/cts.yaml) - 完整配置示例
- [examples/demo_plugin.py](./examples/demo_plugin.py) - 带 Hooks 的插件示例

## 相关文档

- [Plugins](../10-plugins/README.md) - 插件开发指南
- [Hook 事件合约](../../../src/cts/plugins/contracts.py) - 所有事件的详细定义