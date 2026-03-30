# MCP Provider

这一篇解决的是：怎么把一个 MCP server 里的 tools 导进 `cts`，并挂成稳定命令。

---

## 最短路径

如果你只是想先确认一台 MCP server 能不能接通，先用这一条：

```bash
cts import mcp my-mcp \
  --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' \
  --apply
```

导入成功后，建议马上检查：

```bash
cts manage source show my-mcp --format json
cts manage source test my-mcp --discover --format json
cts my-mcp --help
```

---

## 三种方式，从简单到复杂

### 方式 1：直接传 `--server-config`

适合：

- 快速试一个远端 MCP server
- 不想先准备 `servers.json`

```bash
cts import mcp my-mcp \
  --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' \
  --apply
```

### 方式 2：使用现有 `servers.json`

适合：

- 你已经有 MCP 配置文件
- 你要复用已有 server 定义

```bash
cts import mcp my-mcp --server-name my-server --config-file ./servers.json --apply
```

### 方式 3：先写配置文件，再做批量治理

适合：

- 你要管理多个 MCP source
- 你要和别的 source 一起做配置治理
- 你要长期维护 discovery、mount、drift

`cts.yaml`：

```yaml
version: 1
sources:
  my_mcp:
    type: mcp
    adapter: mcp-cli
    config_file: ./servers.json
    server: my-mcp
    discovery:
      mode: live
```

`servers.json`：

```json
{
  "mcpServers": {
    "my-mcp": {
      "type": "sse",
      "url": "https://..."
    }
  }
}
```

然后：

```bash
cts --config cts.yaml manage source test my_mcp --discover --format json
cts --config cts.yaml manage mount import my_mcp --under my
```

---

## 导入后怎么看结果

最重要的不是先执行 tool，而是先确认 discovery 到底拿到了什么。

```bash
# 看 source 当前编译结果
cts manage source show my-mcp --format json

# 重新做一次 discovery
cts manage source test my-mcp --discover --format json

# 看 mount 列表
cts manage mount list --format json
```

建议重点看这些字段：

- `operation_count`
- `discovery_state`
- `schema_provenance`
- `discovery_report_path`

---

## 常用选项

```bash
# 给所有导入的命令加路径前缀
cts import mcp my-mcp \
  --server-config '{"type":"sse","url":"https://..."}' \
  --under api \
  --apply

# 只预览，不写配置
cts import mcp my-mcp \
  --server-config '{"type":"sse","url":"https://..."}' \
  --format json
```

---

## 排查建议

如果你看到 `tools_count: 0`，不要只盯着返回值本身，继续查：

```bash
cts manage source test my-mcp --discover --format json
cts manage source show my-mcp --format json
```

重点确认：

- discovery 是真的拿到了 0 个 tool
- 还是 bridge / node / mcp sdk 依赖缺失
- 还是 server 配置写进去了，但 discovery 没成功

---

## 下一步

当你已经能把 MCP tool 导进来，接下来通常会看两篇：

- [Mount 设计](../08-mounts/README.md)
- [执行方式](../09-execution/README.md)
