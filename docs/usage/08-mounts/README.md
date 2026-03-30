# Mounts

这一节讲的是 mount 设计本身，而不是 provider 接入。

provider 主要回答：

- 能力从哪里来
- operation 是怎么发现或定义的

mount 主要回答：

- 这个能力的稳定 ID 是什么
- 它应该挂在命令树的哪里
- 用户最终看到的 help 应该长什么样
- 哪些 surface 应该暴露它

## 手工添加一个 mount

示例：

```bash
cts --config cts.yaml mount add demo_cli echo_json \
  --id demo-echo \
  --path "demo echo" \
  --summary "Echo structured JSON"
```

适合场景：

- operation 不多，只有几个
- 你很在意命令命名质量
- 你希望逐个控制 help、policy 和暴露方式

## 批量导入 mounts

示例：

```bash
cts --config cts.yaml mount import my_mcp --under my
```

适合场景：

- source 能发现很多 operations
- 你想先快速接入一批能力
- 你准备后面再慢慢优化命名

常用参数：

- `--under`：统一加一个命令前缀
- `--prefix`：控制生成的 mount ID 前缀
- `--filter`：只导入匹配的 operation
- `--exclude`：排除部分 operation
- `--dry-run`：只预览，不落盘

## 命令路径怎么设计

常见模式：

- 资源导向：`jira issue get`
- provider 导向：`github issues list`
- 任务导向：`ops db backup`

建议：

- 尽量用稳定名词，而不是临时动作词
- 命令层级别太深
- 除非上游名字本身就适合用户，否则不要机械暴露底层原名

## 为什么稳定 mount ID 很重要

很多时候，mount ID 比命令路径更适合给脚本或系统依赖。

原因：

- 命令路径以后可能会重构
- mount ID 可以长期保持稳定
- `invoke` 和 `explain` 都是围绕 mount ID 设计的

## mount 还能定制什么

mount 还可以进一步调整：

- summary 和 description
- examples 和 notes
- 参数帮助和默认值
- risk 等级
- `cli`、`invoke`、`http`、`mcp` 等 surface 的暴露策略
