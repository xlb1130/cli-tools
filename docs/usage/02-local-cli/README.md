# Local CLI Provider

这一节讲怎么把本地命令或可执行文件通过 `cli` provider 接进 `cts`。

建议按下面的顺序理解：

1. 最简单、最稳的方式：manifest 驱动
2. 不用 manifest：直接把 operation 写在配置里
3. 半自动导入：从已有 CLI 生成 manifest
4. 高度定制：参数、flag、默认值、帮助信息、输出解析

## 先建立心智模型

对 `cli` provider 来说，`mount` 本身并不负责定义底层怎么执行。

你需要先有两层：

- `source`：能力来源
- `operation`：这个来源里具体有哪些操作、参数和执行方式

然后再用：

- `mount`：把某个 operation 绑定成稳定命令路径和 mount ID

## 方式 A：manifest-first

这是当前最推荐的方式，尤其适合真实项目。

优点：

- operation 定义清晰，便于 review
- discovery 更稳定、可重复
- help、schema、drift 等治理能力更容易发挥作用

最小配置：

```yaml
version: 1

sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
      manifest: ./echo-manifest.yaml

mounts:
  - id: demo-echo
    source: demo_cli
    operation: echo_json
    command:
      path: [demo, echo]
```

最小 manifest：

```yaml
version: 1
operations:
  - id: echo_json
    title: Echo JSON
    input_schema:
      type: object
      required: [text]
      properties:
        text:
          type: string
        upper:
          type: boolean
          default: false
    argv_template:
      - python3
      - -c
      - |
        import json, sys
        text = sys.argv[1]
        upper = sys.argv[2].lower() == "true"
        if upper:
            text = text.upper()
        print(json.dumps({"text": text, "upper": upper}))
      - "{text}"
      - "{upper}"
    output:
      mode: json
```

执行：

```bash
cts --config ./docs/usage/02-local-cli/examples/cts.manifest.yaml demo echo --text hello --upper --output json
```

相关文件：

- [examples/cts.manifest.yaml](./examples/cts.manifest.yaml)
- [examples/echo-manifest.yaml](./examples/echo-manifest.yaml)

## 方式 B：直接在配置里定义 operations

如果你不想单独维护一个 manifest，也可以直接把 operation 写在 `sources.<name>.operations` 里。

适合场景：

- operation 很少，只有一两个
- 你希望配置收敛到一个文件里
- 还在快速原型阶段

示例：

```yaml
version: 1

sources:
  demo_cli:
    type: cli
    executable: python3
    operations:
      echo_json:
        title: Echo JSON
        input_schema:
          type: object
          required: [text]
          properties:
            text:
              type: string
            upper:
              type: boolean
              default: false
        provider_config:
          argv_template:
            - python3
            - -c
            - |
              import json, sys
              text = sys.argv[1]
              upper = sys.argv[2].lower() == "true"
              if upper:
                  text = text.upper()
              print(json.dumps({"text": text, "upper": upper}))
            - "{text}"
            - "{upper}"
          output:
            mode: json

mounts:
  - id: demo-echo
    source: demo_cli
    operation: echo_json
    command:
      path: [demo, echo]
```

对应文件：

- [examples/cts.operations.yaml](./examples/cts.operations.yaml)

## 方式 C：从已有 CLI 半自动生成 manifest

仓库里已经有这几类导入命令：

- `cts source import-help`
- `cts source import-completion`
- `cts source import-manpage`
- `cts source import-schema`

适合场景：

- 你已经有一个现成 CLI
- 不想手写所有 operation
- 想先生成一个 manifest，再人工修正

典型流程：

1. 先创建 source
2. 生成或更新 manifest
3. 手动挂某个 operation，或者用 `mount import` 批量导入
4. 回头检查帮助信息和参数绑定是否合理

## 高度定制化时常用的字段

比较常调的内容有：

- `input_schema`：决定参数校验和生成的 CLI 参数
- `argv_template`：完全控制最终 argv
- `command_argv + option_bindings`：适合导入型 CLI
- `output.mode`：指定 `text` 或 `json`
- `examples`：把示例带进帮助系统
- `risk`：标记 `read`、`write`、`destructive`

几个关键规则：

- `mount` 只负责挂载 operation
- operation 必须先存在于 `discovery.manifest` 或 `source.operations`
- 真正执行时，底层至少需要：
  - `provider_config.argv_template`
  - 或 `command_argv + option_bindings`

## 相关阅读

- [03-shell](../03-shell/README.md)
- [08-mounts](../08-mounts/README.md)
- [09-execution](../09-execution/README.md)
