# GraphQL Provider

当上游系统暴露的是 GraphQL endpoint，并且你想把 query / mutation 导入进 `cts` 时，可以使用 `graphql` provider。

常见有两种方式：

- 从 schema 或 introspection 结果导入
- 手工只定义几个关键 operation

## 最小 schema 驱动示例

```yaml
version: 1

sources:
  github_gql:
    type: graphql
    endpoint: https://api.example.com/graphql
    schema:
      introspection: live

mounts:
  - id: github-gql
    source: github_gql
    select:
      include: ["*"]
    command:
      under: [gql]
```

对应文件：

- [examples/cts.yaml](./examples/cts.yaml)

## 常见流程

```bash
cts --config cts.yaml manage source test github_gql --discover --format json
cts --config cts.yaml manage mount import github_gql --under gql
```

## 导入时能得到什么

当 schema 导入打开后，`cts` 可以推导出：

- query / mutation 字段名
- 参数 schema
- 默认的 GraphQL document
- 和 schema 来源相关的帮助说明

## 什么时候适合手工定义 GraphQL operation

适合这些场景：

- 你只需要一两个 operation
- 上游 schema 不稳定或者不方便访问
- 你想自己完全控制 GraphQL document
