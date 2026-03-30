# OpenAPI Provider

当上游服务已经有 OpenAPI 文档时，优先考虑 `openapi` provider。

相比手工写 `http` operations，它通常更适合：

- API 已经有比较完整的 spec
- 你希望自动导入请求 schema
- 你希望 discovery 和 sync 可重复
- 你预计上游 API 会持续演进

## 最小示例

```yaml
version: 1

sources:
  petstore:
    type: openapi
    spec:
      file: ./petstore-mini.yaml
    discovery:
      mode: live

mounts:
  - id: petstore
    source: petstore
    select:
      include: ["*"]
    command:
      under: [petstore]
```

相关文件：

- [examples/cts.yaml](./examples/cts.yaml)
- [examples/petstore-mini.yaml](./examples/petstore-mini.yaml)

## 常见流程

1. 定义一个 `openapi` source
2. 指向 `spec.file`、`spec.path` 或 `spec.url`
3. 运行 `source test --discover` 或 `sync`
4. 用 `mount import` 批量导入 mounts
5. 再回头微调命令路径和帮助信息

示例：

```bash
cts --config cts.yaml source test petstore --discover --format json
cts --config cts.yaml mount import petstore --under petstore
```

## 它和手工 HTTP 的主要差别

通过 `openapi`，`cts` 可以导入：

- HTTP method 和 path
- 参数位于 path/query/header/body 的信息
- request body 结构
- 部分 response 元信息
- 来自 spec 的帮助说明

对于稳定的 REST API，这通常是最佳接入方式之一。
