# Shell Provider

当你想把 shell 脚本、命令串或小型自动化任务挂进 `cts` 时，可以用 `shell` provider。

和 `cli` 相比：

- `cli` 更适合已有的、参数结构稳定的可执行程序
- `shell` 更适合脚本、流水线或轻量任务封装

当前实现里，`shell` 和 `cli` 在执行模型上非常接近，核心区别通常在于底层命令怎么组织。

## 最小示例

```yaml
version: 1

sources:
  shell_tasks:
    type: shell
    executable: /bin/sh
    operations:
      say_hello:
        title: Say Hello
        input_schema:
          type: object
          required: [name]
          properties:
            name:
              type: string
        provider_config:
          argv_template:
            - /bin/sh
            - -c
            - 'printf "hello %s\n" "$1"'
            - shell-task
            - "{name}"

mounts:
  - id: shell-hello
    source: shell_tasks
    operation: say_hello
    command:
      path: [shell, hello]
```

对应文件：

- [examples/cts.yaml](./examples/cts.yaml)

## 什么时候适合用 shell

- 你想快速包一个本地脚本
- 逻辑本来就已经写在 bash 或 sh 里
- 执行契约比较简单，且只在本地运行

## 什么时候应该升级成别的方式

- 如果契约开始变复杂，优先考虑正式的 CLI manifest
- 如果你要做强 schema 导入，优先考虑 `openapi`、`graphql`、`mcp`
- 如果你需要复用的内部协议适配，考虑写成 plugin provider
