# MCP Provider

导入和挂载 MCP Server 的 tools。

---

## 三种方式，从简单到复杂

### 方式 1：快捷导入（最简单）

适合：快速试一个 MCP Server，不想写配置文件。

```bash
# 一行命令导入
cts import mcp my-mcp --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' --apply

# 执行导入的工具
cts my-mcp <tool-name> --param value
```

---

### 方式 2：使用现有 servers.json

适合：已经有一个配置好的 servers.json 文件。

```bash
# 从 servers.json 导入
cts import mcp my-mcp --server-name my-server --config-file ./servers.json --apply
```

---

### 方式 3：配置文件（最灵活）

适合：管理多个 MCP Server，团队共享配置。

配置文件：

```yaml
# cts.yaml
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

servers.json：

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

```bash
# 批量导入 tools
cts --config cts.yaml manage mount import my_mcp --under my

# 执行
cts --config cts.yaml my <tool-name> --param value
```

---

## 常用选项

```bash
# 添加命令路径前缀
cts import mcp my-mcp --server-config '{"type":"sse","url":"https://..."}' --under api --apply

# 预览不应用
cts import mcp my-mcp --server-config '{"type":"sse","url":"https://..."}' --format json

# 验证 discovery
cts --config cts.yaml manage source test my_mcp --discover --format json
```

---

## 相关链接

- [完整示例](./examples/)
- [Mount 设计](../08-mounts/README.md)
- [执行方式](../09-execution/README.md)