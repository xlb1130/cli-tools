# Execution

当 source 和 mount 已经存在后，执行通常有三种主要方式：

- 通过动态命令路径执行
- 通过稳定 mount ID 用 `invoke` 执行
- 通过 `explain` 先看执行计划

## 通过命令路径执行

这是最适合人类直接使用的一种方式。

示例：

```bash
cts --config cts.yaml demo echo --text hello --upper --output json
```

适合场景：

- 你想像普通 CLI 一样交互使用
- 你需要动态 `--help`
- 你希望命令树本身就是产品体验的一部分

## 通过 mount ID 执行

示例：

```bash
cts --config cts.yaml invoke demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

适合场景：

- 脚本依赖稳定入口
- 命令路径未来可能调整
- 你希望直接传 JSON 输入

## 先 explain 再决定要不要执行

示例：

```bash
cts --config cts.yaml explain demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

`explain` 适合用来：

- 看最终渲染出来的 argv 或 HTTP 请求
- 排查参数映射问题
- 在真正执行前理解这个 mount 会做什么

## dry-run

有些 provider 也支持通过统一执行模型做 dry-run。

示例：

```bash
cts --config cts.yaml invoke demo-echo --input-json '{"text":"hello"}' --dry-run --format json
cts --config cts.yaml explain demo-echo --input-json '{"text":"hello"}' --format json
```

## 配合 inspect 和运行信息一起看

和执行常一起搭配的命令有：

```bash
cts --config cts.yaml inspect source demo_cli --format json
cts --config cts.yaml inspect mount demo-echo --format json
cts --config cts.yaml runs list --format json
cts --config cts.yaml doctor --format json
```

## 对外以 northbound surface 形式提供

执行并不只局限在本地 CLI。

例如：

```bash
cts --config cts.yaml serve http
cts --config cts.yaml serve http --ui --open
cts --config cts.yaml serve mcp
```

适合场景：

- 你想让其他工具也调用同一套 mounts
- 你想通过 UI 浏览相同 catalog
- 你希望 `cts` 反过来以 MCP 工具集的形式对外提供能力
