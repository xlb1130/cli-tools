# Plugins

Plugin 的作用是扩展 `cts` 内核。

主要价值：
- 注册新的 provider type
- 提供 hook handler
- 把公司内部或项目专属逻辑放在 core 之外

## 快速上手

### 1. 创建插件文件

创建 `my_plugin.py`：

```python
from cts.models import (
    ExecutionPlan, HelpDescriptor, InvokeResult, OperationDescriptor
)


class MyProvider:
    """自定义 Provider，注册一个新的 provider type"""
    provider_type = "my_echo"  # 这就是 source.type 可用的值

    def discover(self, source_name, source_config, app):
        """发现并返回所有操作"""
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
        if op is None:
            return None
        return op.input_schema, {"strategy": "declared", "origin": "plugin"}

    def get_help(self, source_name, source_config, operation_id, app):
        op = self.get_operation(source_name, source_config, operation_id, app)
        if op is None:
            return None
        return HelpDescriptor(summary=op.title, description=op.description)

    def refresh_auth(self, source_name, source_config, app):
        return None

    def plan(self, source_name, source_config, request, app):
        """生成执行计划"""
        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk="read",
        )

    def invoke(self, source_name, source_config, request, app):
        """执行操作"""
        return InvokeResult(
            ok=True,
            status_code=0,
            data={"echo": dict(request.args)},
        )

    def healthcheck(self, source_name, source_config, app):
        return {"ok": True, "provider_type": self.provider_type}


class Plugin:
    """插件主类 - 必须命名为 Plugin"""

    def __init__(self, plugin_name=None, config=None):
        self.plugin_name = plugin_name or "my_plugin"
        self.config = config or {}

    def register_providers(self):
        """注册 Provider，返回 {provider_type: Provider实例}"""
        return {"my_echo": MyProvider()}

    def get_hook_handlers(self):
        """注册 Hook 处理函数（可选）"""
        return {}
```

### 2. 配置 cts.yaml

```yaml
version: 1

plugins:
  my_plugin:
    path: ./my_plugin.py    # 本地文件路径
    enabled: true
    config:                 # 传给插件的配置
      greeting: "Hello"

sources:
  my_source:
    type: my_echo           # 使用 plugin 注册的 provider type
    operations:
      say:
        title: Say Something
        description: Echo your message
        input_schema:
          type: object
          properties:
            message:
              type: string
          required: [message]

mounts:
  - id: my-mount
    source: my_source
    operation: say
    command:
      path: [my, say]
```

### 3. 使用

```bash
# 查看帮助
cts my say --help

# 执行命令
cts my say --message "Hello World"
```

## 插件配置详解

### 加载方式

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `path` | 本地 Python 文件路径 | `./plugins/my_plugin.py` |
| `module` | Python 模块名（已安装的包） | `mycompany.cts_plugin` |
| `executable` | 外部可执行文件（subprocess 协议） | `/usr/local/bin/my-plugin` |
| `factory` | 工厂函数名 | `create_plugin` |

### 配置项说明

```yaml
plugins:
  my_plugin:
    # 加载方式三选一
    path: ./my_plugin.py       # 方式1: 本地文件
    # module: my_package.plugin # 方式2: 已安装的 Python 模块
    # executable: /path/to/bin  # 方式3: 外部可执行文件

    enabled: true              # 是否启用
    protocol: inprocess        # inprocess 或 subprocess
    factory: create_plugin     # 可选，指定工厂函数名

    config:                    # 自定义配置，传给 Plugin.__init__
      api_key: xxx
      timeout: 30
```

### 插件入口约定

插件模块必须暴露以下之一：

```python
# 方式1: Plugin 类（推荐）
class Plugin:
    def __init__(self, plugin_name=None, config=None): ...
    def register_providers(self): ...
    def get_hook_handlers(self): ...

# 方式2: factory 函数
def create_plugin(plugin_name, config):
    return Plugin(plugin_name, config)

# 方式3: get_plugin 函数
def get_plugin(plugin_name, config):
    return Plugin(plugin_name, config)

# 方式4: plugin 实例
plugin = Plugin()
```

## Provider 接口完整定义

```python
class MyProvider:
    provider_type = "my_type"  # 必须定义

    def discover(self, source_name, source_config, app) -> list[OperationDescriptor]:
        """发现操作列表"""
        pass

    def get_operation(self, source_name, source_config, operation_id, app):
        """获取单个操作"""
        pass

    def get_schema(self, source_name, source_config, operation_id, app):
        """获取输入 schema，返回 (input_schema, schema_info) 元组"""
        pass

    def get_help(self, source_name, source_config, operation_id, app) -> HelpDescriptor:
        """获取帮助信息"""
        pass

    def refresh_auth(self, source_name, source_config, app):
        """刷新认证，返回 None 或新的认证信息"""
        pass

    def plan(self, source_name, source_config, request, app) -> ExecutionPlan:
        """生成执行计划"""
        pass

    def invoke(self, source_name, source_config, request, app) -> InvokeResult:
        """执行操作"""
        pass

    def healthcheck(self, source_name, source_config, app):
        """健康检查"""
        pass
```

## 什么时候用 Plugin

适合场景：
- 内置 provider 不够，需要新的 provider type
- 有一套可复用的内部集成逻辑
- 希望把组织内部代码和 `cts` 核心隔离开
- 需要在多个生命周期节点插入自定义逻辑（配合 Hooks）

不适合场景：
- 只是调用一个 HTTP API → 用 [HTTP Provider](../04-http/README.md)
- 只是调用一个 CLI 工具 → 用 [CLI Provider](../02-local-cli/README.md)
- 只是调用 OpenAPI → 用 [OpenAPI Provider](../05-openapi/README.md)

## 安装和发布

### 本地开发

```bash
# 直接使用本地文件
# cts.yaml 中配置 path: ./my_plugin.py
```

### 发布为 Python 包

1. 创建包结构：
```
my-cts-plugin/
├── pyproject.toml
└── my_cts_plugin/
    └── __init__.py  # 包含 Plugin 类
```

2. 发布到 PyPI：
```bash
pip install build
python -m build
pip install twine
twine upload dist/*
```

3. 使用：
```bash
pip install my-cts-plugin
```

```yaml
plugins:
  my_plugin:
    module: my_cts_plugin
```

## 示例文件

- [examples/cts.yaml](./examples/cts.yaml) - 完整配置示例
- [examples/demo_plugin.py](./examples/demo_plugin.py) - 插件实现示例

## 相关文档

- [Hooks](../11-hooks/README.md) - 如何在插件中定义和使用 Hooks
- [Provider 类型](../README.md) - 所有内置 Provider 类型