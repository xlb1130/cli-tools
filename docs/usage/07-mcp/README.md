# MCP Provider

当你想接入一个 MCP server，并把发现到的 tools 暴露到统一命令树里时，可以使用 `mcp` provider。

这也是 `cts` 很适合发挥价值的一类场景，因为它可以：

- 把 MCP 作为众多 provider 之一统一纳入平台
- 把 MCP tools 挂成稳定命令路径
- 通过 CLI、mount ID 和 northbound surface 统一调用

## 两种常见连接方式

一个 MCP source 通常至少需要下面二选一：

- `config_file + server`
- 或直接 `url`

## 使用 config file 的例子

```yaml
version: 1

sources:
  my_mcp:
    type: mcp
    adapter: mcp-cli
    config_file: ./mcp-servers.json
    server: my-mcp
    discovery:
      mode: live

mounts:
  - id: my-mcp
    source: my_mcp
    select:
      include: ["*"]
    command:
      under: [my]
```

相关文件：

- [examples/cts.yaml](./examples/cts.yaml)
- [examples/mcp-servers.json](./examples/mcp-servers.json)

## 常见流程

先验证 discovery：

```bash
cts --config cts.yaml source test my_mcp --discover --format json
```

再批量导入 tools：

```bash
cts --config cts.yaml mount import my_mcp --under my
```

导入后，通常就可以这样执行：

```bash
cts --config cts.yaml my <tool-name> ...
```

也可以按 mount ID 执行：

```bash
cts --config cts.yaml invoke my-<tool-name> --input-json '{...}' --format json
```

## 使用直接 URL 的例子

```yaml
sources:
  remote_mcp:
    type: mcp
    url: https://example.com/mcp
    transport_type: streamable_http
    server: remote
    discovery:
      mode: live
```

## 进阶说明

- 对 MCP 来说，`mount import` 往往是最快的接入方式
- `discovery.mode=live` 很适合真实 server 的即时发现
- 如果上游 tools 常变，后面就要结合 cache、sync 和 drift 治理一起看
