# Quickstart

这一节只有一个目标：最快先跑通一次。

要求尽量低：

- 不先手写配置文件
- 先创建一个 source
- 再挂一个 operation
- 然后直接执行

默认情况下，如果你不传 `--config`，`cts` 会使用 `~/.cts/config.yaml`。如果这个文件还不存在，像 `source add`、`mount add` 这样的命令会自动创建它。

## 最快路径

在仓库根目录执行：

```bash
cts source add cli demo_cli \
  --bin python3 \
  --manifest ./examples/demo/echo-manifest.yaml \
  --discover-mode manifest
```

```bash
cts mount add demo_cli echo_json \
  --id demo-echo \
  --path "demo echo" \
  --summary "Echo structured JSON"
```

```bash
cts demo echo --text hello --upper --output json
```

```bash
cts invoke demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

```bash
cts explain demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

## 这几步做了什么

- `source add` 创建了一个 `cli` source，名字叫 `demo_cli`
- 这个 source 指向一个 manifest 文件，里面定义了 operation
- `mount add` 把其中一个 operation 挂到了 `demo echo`
- `cts demo echo ...` 通过动态命令路径执行它
- `cts invoke ...` 通过稳定 mount ID 执行同一个能力
- `cts explain ...` 用来看执行计划，而不需要先去翻源码

## 看看当前状态

```bash
cts source list
cts mount list
cts inspect mount demo-echo --format json
```

## 下一步看什么

- 想理解本地命令怎么接入，看 [02-local-cli](../02-local-cli/README.md)
- 想理解 mount 怎么设计，看 [08-mounts](../08-mounts/README.md)
- 想理解执行链路和运行方式，看 [09-execution](../09-execution/README.md)
