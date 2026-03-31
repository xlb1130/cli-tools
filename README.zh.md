# cts

[English](README.md)

`cts` 把不同来源的能力统一成稳定命令。

你可以把本地 CLI、Shell、HTTP API、OpenAPI、GraphQL、MCP Server 编译成一套一致的命令入口，再通过 CLI、invoke、HTTP、UI 暴露出来。

## 建议学习路径

如果你是第一次接触 `cts`，建议按这个顺序：

1. 先导入一个本地 shell 命令，立刻跑通
2. 再导入一个你自己的本地 CLI 命令
3. 再尝试 MCP / HTTP / OpenAPI / GraphQL 这类外部能力源
4. 最后再进入 mount 设计、执行方式、plugin、hook

对应文档入口：

- [使用指南总览](docs/usage/README.md)
- [5 分钟上手](docs/usage/01-quickstart/README.md)
- [本地 CLI](docs/usage/02-local-cli/README.md)
- [Shell 脚本](docs/usage/03-shell/README.md)
- [HTTP API](docs/usage/04-http/README.md)
- [OpenAPI](docs/usage/05-openapi/README.md)
- [GraphQL](docs/usage/06-graphql/README.md)
- [MCP Server](docs/usage/07-mcp/README.md)
- [Mount 设计](docs/usage/08-mounts/README.md)
- [执行方式](docs/usage/09-execution/README.md)
- [Plugin](docs/usage/10-plugins/README.md)
- [Hook](docs/usage/11-hooks/README.md)

## 安装

```bash
pip install cts
```

从 wheel 文件安装：

```bash
python3 -m pip install ./dist/cts-0.1.0-py3-none-any.whl
```

从源码安装：

```bash
git clone https://github.com/xlb1130/cli-tools.git
cd cli-tools
pip install -e .
```

## 第一步：先跑通一个本地 shell 命令

这是最快的起点，因为不依赖外部服务，也不需要你手写配置文件。

```bash
cts import shell hello --exec 'echo Hello cts!' --apply
cts hello
```

如果你想先理解动态命令长什么样，可以再看：

```bash
cts hello --help
cts manage explain hello
```

你会看到：

- source: `hello`
- operation: `run`
- mount: `hello`
- command path: `hello`

## 第二步：导入一个真实本地 CLI

最常见的入口是：

```bash
cts import cli <source-name> <command> [subcommand...] --apply
```

例如导入 `git status`：

```bash
cts import cli git-status git status --apply
cts git-status --help
cts git-status
```

如果你想一次导入整棵子命令树：

```bash
cts import cli git git --all --apply --under git
```

接下来建议看 [本地 CLI](docs/usage/02-local-cli/README.md)。

## 第三步：接入 MCP Server

最短路径是：

```bash
cts import mcp my-mcp \
  --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' \
  --apply
```

然后检查 discovery 结果：

```bash
cts manage source show my-mcp --format json
cts manage source test my-mcp --discover --format json
cts my-mcp --help
```

更完整的方式见 [MCP Server](docs/usage/07-mcp/README.md)。

## 启动 Web UI

启动内置的 Web 界面来与你的 CTS 实例交互：

```bash
cts manage ui
```

这会启动 HTTP API 并同时提供前端 UI。默认运行在 `http://127.0.0.1:8787`。

其他选项：

```bash
# 自动打开浏览器
cts manage ui --open

# 使用自定义主机/端口
cts manage ui --host 0.0.0.0 --port 9000

# 使用自定义 UI 目录
cts manage ui --ui-dir /path/to/ui/dist
```

如果找不到 UI 资源，需要先构建：

```bash
cd frontend/app
npm install
npm run build
```

如果需要更多控制，也可以直接使用 HTTP server 命令：

```bash
# 只启动 HTTP API
cts manage serve http

# 启动 HTTP API 和 UI
cts manage serve http --ui

# 启动 HTTP API 和 UI 并自动打开浏览器
cts manage serve http --ui --open
```

## 核心模型

```text
source -> operation -> mount -> surface
```

- `source`：能力来源
- `operation`：来源中的一个具体操作
- `mount`：给 operation 绑定稳定 id 和命令路径
- `surface`：把 mount 暴露到不同入口

## 常用命令

```bash
# 查看 source 详情
cts manage source show <source> --format json

# 测试并发现操作
cts manage source test <source> --discover --format json

# 列出所有 mount
cts manage mount list --format json

# 删除 source
cts manage source remove <source_name> --force --format json

# 调用 mount
cts manage invoke <mount-id> --input-json '{"key":"value"}' --format json

# 解释 mount
cts manage explain <mount-id> --input-json '{"key":"value"}'
```

## 开发

```bash
git clone https://github.com/xlb1130/cli-tools.git
cd cli-tools
python3 -m pip install -e ".[dev]"
```

日常开发时，推荐先直接跑源码版本：

```bash
# 直接运行本地源码
PYTHONPATH=src python3 -m cts.main --help

# 用本地源码跑一次 shell 快速上手
PYTHONPATH=src python3 -m cts.main import shell hello --exec 'echo Hello cts!' --apply
PYTHONPATH=src python3 -m cts.main hello
```

常用验证命令：

```bash
# 编译并检查配置/运行时
PYTHONPATH=src python3 -m cts.main config lint --compile --format json

# 运行测试
python3 -m pytest

# 只跑一个测试文件
python3 -m pytest tests/test_cli_management.py -q
```

前端开发：

```bash
cd frontend/app
npm install
npm run build
```

如果你希望终端里的 `cts` 命令立刻使用本地修改后的代码，再执行：

```bash
python3 -m pip install -e .
```

这一点很重要，尤其是在你新增 CLI 命令时，例如 `cts import shell`，否则终端里可能仍然跑的是旧安装版本。

## 延伸阅读

- [使用指南总览](docs/usage/README.md)
- [架构设计](docs/00-rfc-master-architecture.md)
- [安装与使用说明](docs/15-install-and-usage.md)

## License

[MIT](LICENSE)
