# 本地 CLI Provider

这一篇解决的是：怎么把一个已有 CLI 命令，变成 `cts` 里的稳定命令。

---

## 先记住最常见命令

```bash
cts import cli <source-name> <command> [subcommand...] --apply
```

例如导入 `git status`：

```bash
cts import cli git-status git status --apply

# 看生成的命令
cts git-status --help

# 执行
cts git-status
```

这里的含义是：

- `git-status` 是 `cts` 里的 source 名
- `git status` 是被导入的原始命令

---

## 一条命令导入单个操作

适合：

- 先试一个已有 CLI
- 先导入一个最常用子命令
- 先确认 help/schema 能不能被正确识别

```bash
cts import cli git-status git status --apply
```

导入后，建议立刻做三件事：

```bash
cts git-status --help
cts explain git-status-status
cts manage source show git-status --format json
```

---

## 一次导入整棵子命令树

适合：

- 你已经确认这个 CLI 的 help 结构比较稳定
- 你希望把整个工具族挂进来

```bash
cts import cli git git --all --apply --under git
```

导入后你会得到类似这样的命令路径：

```text
cts git status
cts git branch
cts git log
...
```

如果你只想控制命令路径前缀和 mount id 前缀，可以用：

```bash
cts import cli git git --all --apply --under tools --prefix git
```

---

## 四种导入策略

`cts import cli` 支持四种 schema/help 来源：

1. `--from help`
2. `--from completion`
3. `--from manpage`
4. `--from schema`

默认是 `--from help`，也是最推荐的起点。

### 1. help 导入

适合大多数普通 CLI：

```bash
cts import cli git-status git status --from help --apply
```

### 2. completion 导入

适合补全信息比 help 更完整的命令：

```bash
cts import cli mycli mycli sub --from completion --completion-command 'mycli completion zsh'
```

### 3. manpage 导入

适合 man 文档比 `--help` 更完整的工具：

```bash
cts import cli curl-get curl --from manpage --man-command 'man curl'
```

### 4. schema 导入

适合你自己已经有 JSON schema 的场景：

```bash
cts import cli demo-op python3 -m http.server \
  --from schema \
  --schema-file ./operation-schema.json \
  --apply
```

---

## 什么时候应该切到配置文件

下面这些情况，不建议一直停留在“命令行导入”：

- 你要管理多个 operation
- 你要团队共享配置
- 你要稳定维护 manifest
- 你要做 drift、auth、plugin、hook

这时建议切到：

- [examples/demo/cts.yaml](../../examples/demo/cts.yaml)
- [examples/demo/echo-manifest.yaml](../../examples/demo/echo-manifest.yaml)

或者继续读：

- [Mount 设计](../08-mounts/README.md)
- [执行方式](../09-execution/README.md)

---

## 常见检查命令

```bash
# 看 source 编译结果
cts manage source show <source> --format json

# 看所有 mount
cts manage mount list --format json

# 看执行计划
cts explain <mount-id>

# 通过稳定 id 调用
cts manage invoke <mount-id> --input-json '{"key":"value"}' --format json
```

---

## 如何选择

| 场景 | 推荐方式 |
|------|----------|
| 先试一个命令 | 单操作导入 |
| 先导入整个 CLI | `--all` |
| help 信息不完整 | 换 `completion` 或 `manpage` |
| 你已经有 schema | `--from schema` |
| 要长期维护 | 配置文件 + manifest |
