# cts

[English](README.md)

`cts` 把不同来源的能力统一成稳定命令。

你可以把本地 CLI、Shell、HTTP API、OpenAPI、GraphQL、MCP Server 编译成一套一致的命令入口，再通过 CLI、invoke、HTTP、UI 暴露出来。

## 能解决什么问题？

很多团队手里已经有一堆可用能力，但它们往往分散在不同形态里：

- 有些是本地 CLI
- 有些是 Shell 脚本
- 有些是 HTTP / OpenAPI / GraphQL 接口
- 有些是 MCP Server

问题通常不是“能力不够”，而是：

- 入口太散，不好记，也不好教给别人用
- 自动化脚本越写越多，参数和调用方式越来越不统一
- AI 能调工具，但很难稳定地调对
- 同一套能力很难同时给 CLI、HTTP、UI、MCP 复用

`cts` 解决的是“把这些零散能力编译成一套稳定命令系统”。

你可以用它来做这些事：

- 把一个本地命令快速包成稳定 CLI
- 把一组 HTTP / OpenAPI / GraphQL 接口统一成可调用命令
- 把 MCP tools 编译成清晰的命令树
- 给 AI 提供更稳定、更可治理的工具入口
- 把同一套能力同时暴露给人、脚本、服务和 AI

典型场景包括：

- 研发工具统一入口
- 运维排障与发布自动化
- 行程规划、搜索编排这类多工具协作场景
- 公司内部平台能力的标准化封装

### 高阶场景

**统一 CLI 的核心价值：**

- **稳定接口**：Mount 绑定创建可预测的命令路径——AI 和脚本无需猜测工具名称或参数
- **多入口访问**：一次导入，同时通过 CLI、HTTP、UI、MCP 暴露
- **跨来源一致性**：MCP 工具、OpenAPI 接口、本地 CLI、Shell 脚本都变成一等公民命令
- **内置治理**：钩子支持日志、鉴权、限流、审批流程——对所有来源统一生效

**CTS vs 传统多 MCP 配置：**

| 维度 | 传统多 MCP 配置 | CTS |
|------|----------------|-----|
| 配置方式 | 每个客户端单独配置 | 集中导入和 mount 管理 |
| 访问通道 | 仅 MCP | CLI、HTTP、UI、MCP 并行 |
| 脚本集成 | 不支持 | `cts invoke` 或 HTTP API |
| 治理能力 | 各客户端自行处理 | 钩子、插件、执行历史 |
| 复用性 | 每个客户端重复配置 | 导入一次，处处可用 |

**高阶场景示例：**

- [行程规划](docs/usage/12-travel-planning/README.md)：高德、12306、必应 MCP 统一命令入口
- [自动问题分析与部署](docs/usage/13-advanced-automation/README.md)：日志、数据库、部署、通知工具链，带治理钩子

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
- [高阶实战：行程规划](docs/usage/12-travel-planning/README.md)
- [高阶实战：自动问题分析、自动需求开发与自动部署](docs/usage/13-advanced-automation/README.md)
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

## Provider 驱动的导入入口

现在的 `cts import` 已经统一为 provider 驱动模型：

```bash
cts import <provider-type> ...
cts import wizard
cts import wizard <provider-type>
```

当前内置 provider 类型包括：

- `shell`
- `cli`
- `http`
- `openapi`
- `graphql`
- `mcp`

如果是 plugin 注册出来的 provider，只要它实现了 import 能力，也会自动出现在 `cts import` 和 `cts import wizard` 里。

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

如果你只想在导入时挂载部分 operation / tool，可以直接加筛选条件：

```bash
cts import mcp my-mcp \
  --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' \
  --include 'search_*' \
  --exclude 'delete_*' \
  --apply
```

同样的 `--include` / `--exclude` 也适用于 `cli --all`、`openapi`、`graphql` 这类批量导入 provider。

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
