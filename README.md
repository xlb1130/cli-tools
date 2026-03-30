# cts

[中文](#中文) | [English](#english)

## 中文

**一句话介绍**：`cts` 让你用一条命令把本地 CLI、API、脚本变成可执行的命令，无需先写配置。

### 30 秒上手

```bash
# 安装
pip install cts

# 导入一个本地命令（无需配置文件）
cts import cli mycmd --exec "echo hello" --apply

# 执行
cts mycmd
# 输出: hello
```

就这样。不需要配置文件，不需要 manifest，先跑通再说。

---

### 还能做什么

```bash
# 导入一个已有 CLI 的某个命令
cts import cli greet --exec "echo Hello, \$1!" --apply
cts greet World
# 输出: Hello, World!

# 快捷导入 MCP Server（无需配置文件）
cts import mcp 12306 --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' --apply
# 可以看到已经挂载成功
cts 12306 --help 

# 看看当前挂载了什么
cts manage mount list

# 用稳定 ID 调用
cts manage invoke greet --input-json '{"args":["World"]}'

# 预览执行计划
cts manage explain greet
```

---

### 进阶：使用配置文件

当你需要管理多个命令、团队共享配置时，可以用 YAML 配置文件。

最小示例：

```yaml
# cts.yaml
version: 1
sources:
  demo:
    type: cli
    executable: python3
    operations:
      echo:
        input_schema:
          type: object
          properties:
            text: { type: string }
        provider_config:
          argv_template: ["python3", "-c", "print('{text}')"]

mounts:
  - id: demo-echo
    source: demo
    operation: echo
    command: { path: [demo, echo] }
```

```bash
cts --config cts.yaml demo echo --text hello
```

MCP Server 示例：

```yaml
# cts.yaml
version: 1
sources:
  12306_mcp:
    type: mcp
    adapter: mcp-cli
    config_file: ./servers.json
    server: 12306-mcp
    discovery:
      mode: live

# servers.json
{
  "mcpServers": {
    "12306-mcp": {
      "type": "sse",
      "url": "https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"
    }
  }
}
```

```bash
# 批量导入 MCP tools
cts --config cts.yaml manage mount import 12306_mcp --under 12306

# 执行导入的工具
cts --config cts.yaml 12306 <tool-name> --param value
```

完整示例见 [examples/](examples/)。

---

### 架构概念（了解即可）

`cts` 的核心模型：

```
source -> operation -> mount -> surface
```

- `source`：能力来源（CLI、HTTP API、MCP Server 等）
- `operation`：来源中的具体操作
- `mount`：绑定稳定命令路径和 ID
- `surface`：暴露方式（CLI、HTTP、UI）

这些概念在你需要复杂配置时才有意义，简单场景无需关心。

---

### 支持的能力来源

| 类型 | 说明 |
|------|------|
| `cli` | 本地命令行工具 |
| `shell` | Shell 脚本 |
| `http` | HTTP API |
| `openapi` | OpenAPI 规范 |
| `graphql` | GraphQL 服务 |
| `mcp` | MCP Server |

---

### UI 控制台

```bash
# 启动 Web UI
cts manage serve http --ui --open
```

访问 `http://localhost:8000` 查看 sources、mounts、执行历史等。

---

### 文档

- [使用指南](docs/usage/README.md) - 从简单到进阶的完整教程
- [架构设计](docs/00-rfc-master-architecture.md) - 深入理解内部设计

---

### 安装

```bash
# 从 PyPI（发布后）
pip install cts

# 从源码
git clone https://github.com/xlb1130/cli-tools.git
cd cli-tools
pip install -e ".[dev]"
```

---

### 开发

```bash
pytest                    # 运行测试
cd frontend/app && npm run build  # 构建前端
```

---

### 状态

当前版本：`0.1.0`（MVP 阶段）

核心功能已可用，更多能力持续演进中。

### License

[MIT](LICENSE)

---

## English

**One-liner**: `cts` turns local CLIs, APIs, and scripts into executable commands with a single command—no config required.

### 30-Second Start

```bash
# Install
pip install cts

# Import a local command (no config file needed)
cts import cli mycmd --exec "echo hello" --apply

# Run it
cts mycmd
# Output: hello
```

That's it. No config files, no manifests—just run it first.

---

### What Else Can It Do

```bash
# Import an existing CLI command
cts import cli greet --exec "echo Hello, \$1!" --apply
cts greet World
# Output: Hello, World!

# See what's mounted
cts manage mount list

# Invoke by stable ID
cts manage invoke greet --input-json '{"args":["World"]}'

# Preview execution plan
cts manage explain greet
```

---

### Advanced: Config Files

When you need to manage multiple commands or share config across a team.

Minimal example:

```yaml
# cts.yaml
version: 1
sources:
  demo:
    type: cli
    executable: python3
    operations:
      echo:
        input_schema:
          type: object
          properties:
            text: { type: string }
        provider_config:
          argv_template: ["python3", "-c", "print('{text}')"]

mounts:
  - id: demo-echo
    source: demo
    operation: echo
    command: { path: [demo, echo] }
```

```bash
cts --config cts.yaml demo echo --text hello
```

See [examples/](examples/) for more.

---

### Architecture Concepts (Optional)

Core model:

```
source -> operation -> mount -> surface
```

- `source`: where capabilities come from (CLI, HTTP API, MCP, etc.)
- `operation`: a specific action in that source
- `mount`: binds a stable command path and ID
- `surface`: how it's exposed (CLI, HTTP, UI)

These only matter for complex scenarios—simple cases don't need them.

---

### Supported Sources

| Type | Description |
|------|-------------|
| `cli` | Local CLI tools |
| `shell` | Shell scripts |
| `http` | HTTP APIs |
| `openapi` | OpenAPI specs |
| `graphql` | GraphQL services |
| `mcp` | MCP Servers |

---

### UI Console

```bash
# Start Web UI
cts manage serve http --ui --open
```

Visit `http://localhost:8000` to inspect sources, mounts, run history, etc.

---

### Documentation

- [Usage Guide](docs/usage/README.md) - From simple to advanced
- [Architecture](docs/00-rfc-master-architecture.md) - Deep dive into design

---

### Install

```bash
# From PyPI (after release)
pip install cts

# From source
git clone https://github.com/xlb1130/cli-tools.git
cd cli-tools
pip install -e ".[dev]"
```

---

### Development

```bash
pytest                    # Run tests
cd frontend/app && npm run build  # Build frontend
```

---

### Status

Current version: `0.1.0` (MVP)

Core features work; more capabilities evolving.

### License

[MIT](LICENSE)