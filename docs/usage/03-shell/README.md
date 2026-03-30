# Shell Provider

当你想把 shell 脚本、命令串或小型自动化任务挂进 `cts` 时，可以用 `shell` provider。

和 `cli` 相比：

- `cli` 更适合已有的、参数结构稳定的可执行程序
- `shell` 更适合脚本、流水线或轻量任务封装

当前最推荐的入口，不再是先手写配置文件，而是先用 `cts import shell` 跑通。

## 最快路径：直接导入一条 shell 命令

这是最快的用法，不需要你先写配置文件。

```bash
cts import shell hello --exec 'echo Hello cts!' --apply
cts hello
```

导入后建议马上看一下：

```bash
cts hello --help
cts explain hello
cts manage source show hello --format json
```

这时候你会看到：

- source: `hello`
- operation: `run`
- mount: `hello`
- command path: `hello`

## 导入本地脚本文件

如果你已经有一个 `.sh` 文件，可以直接导入：

```bash
cts import shell hello-file --script-file ./hello.sh --apply
cts hello-file
```

也可以配合 `--under` 调整命令路径：

```bash
cts import shell hello-file --script-file ./hello.sh --under tools --apply
cts tools hello-file
```

默认用 `/bin/sh` 执行；如果你想换成别的 shell：

```bash
cts import shell hello-file --script-file ./hello.sh --shell-bin /bin/bash --apply
```

## 什么时候继续用配置文件

当下面这些需求出现时，再从“命令行导入”升级成配置文件：

- 你需要多个 shell operation
- 你需要更稳定的命名和版本管理
- 你需要团队共享配置
- 你需要更复杂的输入 schema

最小配置示例：

```yaml
version: 1

sources:
  shell_tasks:
    type: shell
    executable: /bin/sh
    operations:
      say_hello:
        title: Say Hello
        description: A tiny shell-backed operation.
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
          output:
            mode: text

mounts:
  - id: shell-hello
    source: shell_tasks
    operation: say_hello
    command:
      path: [shell, hello]
```

对应文件：

- [examples/cts.yaml](./examples/cts.yaml)

## 常见场景

下面这些情况很适合继续用 `shell`：

- 你想快速包一个本地脚本
- 逻辑本来就已经写在 bash 或 sh 里
- 只想先把一段小任务挂成稳定命令
- 需要一个零配置文件的快速入口

## 什么时候应该升级成别的方式

- 如果契约开始变复杂，优先考虑正式的 CLI manifest
- 如果你要做强 schema 导入，优先考虑 `openapi`、`graphql`、`mcp`
- 如果你要导入一个已有复杂 CLI，优先看 [本地 CLI](../02-local-cli/README.md)
- 如果你需要复用的内部协议适配，考虑写成 plugin provider
