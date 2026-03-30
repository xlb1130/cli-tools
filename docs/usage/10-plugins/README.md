# Plugins

plugin 的作用是扩展 `cts` 内核。

它不只是另一种“挂业务命令”的方式，更主要的价值在于：

- 注册新的 provider type
- 提供 hook handler
- 把公司内部或项目专属逻辑放在 core 之外

## 什么时候应该用 plugin

这些情况下适合考虑 plugin：

- 内置 provider 不够，需要新的 provider type
- 你有一套可复用的内部集成逻辑
- 你希望把组织内部代码和 `cts` 核心仓库隔离开

## 最小 plugin provider 示例

这个示例会注册一个新的 provider type，叫 `plugin_echo`。

配置：

```yaml
plugins:
  demo:
    path: ./demo_plugin.py

sources:
  plugin_source:
    type: plugin_echo
    operations:
      echo:
        title: Plugin Echo
        description: Echo from plugin provider.
        input_schema:
          type: object
          properties:
            text:
              type: string
          required: [text]

mounts:
  - id: plugin-echo
    source: plugin_source
    operation: echo
    command:
      path: [plugin, echo]
```

相关文件：

- [examples/cts.yaml](./examples/cts.yaml)
- [examples/demo_plugin.py](./examples/demo_plugin.py)

## 这类 plugin 的意义

一旦 plugin 被加载：

- `source.type` 就可以直接使用 plugin 注册出来的 provider type
- 这个 provider 会进入 discovery、help、explain、invoke、healthcheck 链路
- mount 使用方式和内置 provider 没有本质区别

## 常见流程

1. 先写一个 plugin 模块
2. 注册一个或多个 provider
3. 在 `plugins` 顶层加载它
4. 创建一个 source，让 `type` 指向 plugin 注册的 provider type
5. 再像普通 source 一样定义 operations 和 mounts
