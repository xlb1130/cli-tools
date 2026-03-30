# HTTP Provider

当你想手工描述一个或一组 HTTP 接口，而不是直接导入完整 OpenAPI spec 时，可以用 `http` provider。

适合场景：

- 上游 API 很小
- 没有 OpenAPI 文档
- 你只需要少量稳定接口
- 你想完全控制请求映射方式

## 最小示例

```yaml
version: 1

sources:
  demo_http:
    type: http
    base_url: https://api.example.com
    operations:
      get_issue:
        title: Get Issue
        input_schema:
          type: object
          required: [key]
          properties:
            key:
              type: string
        provider_config:
          method: GET
          path: /issues/{key}
          path_params: [key]

mounts:
  - id: issue-get
    source: demo_http
    operation: get_issue
    command:
      path: [issue, get]
```

对应文件：

- [examples/cts.yaml](./examples/cts.yaml)

## 请求映射是怎么工作的

- path 变量来自 `provider_config.path` 和 `path_params`
- `GET` 请求里，剩余参数默认会变成 query params
- `POST`、`PUT`、`PATCH` 中，剩余参数默认会进入 JSON body
- source 级 headers 和 operation 级 headers 会合并
- auth 和 secret 引用会在发请求前统一应用

## 用 CLI 先创建 source

可以先这样建一个 source：

```bash
cts --config cts.yaml source add http jira \
  --base-url https://jira.example.com
```

然后再在 YAML 里补 operation，再把它挂成 mount。

对手工 HTTP source 来说，operation 契约一般还是写在 YAML 里更清晰。
