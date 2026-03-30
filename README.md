# cts

[中文](#中文) | [English](#english)

## 中文

`cts` 是一个可配置的能力中转系统，用来把 API、MCP Server、CLI 工具和本地脚本统一编译成稳定的命令入口。

它提供一致的建模、挂载和暴露方式，让来自不同后端的能力可以通过统一的 CLI、HTTP API 和本地 Web UI 来使用。

### 为什么是 cts

很多团队的能力都分散在不同地方：

- 内部 HTTP API
- OpenAPI 和 GraphQL 服务
- MCP Server
- 既有 CLI 工具
- Shell 脚本和本地自动化

`cts` 的目标是把这些能力拉到同一个契约驱动的层里，让它们可以被统一发现、挂载、调用、生成文档和治理。

核心模型：

```text
source -> operation -> mount -> surface
```

- `source`：能力来源
- `operation`：来源中的具体操作
- `mount`：为操作绑定稳定 ID 和命令路径
- `surface`：对外暴露方式，例如 CLI、HTTP、UI

### 当前已经具备的能力

这个仓库已经不是纯设计稿，而是一个可运行的 Python MVP，当前包括：

- 单文件和拆分式配置编译
- 基于挂载结果动态生成 CLI 命令
- 基于 `mount.id` 的稳定调用入口
- `cli`、`shell`、`http`、`openapi`、`graphql`、`mcp` provider
- discovery、schema 缓存、sync、drift 检查和 reconcile 基础能力
- auth 与 secret 管理能力
- plugin 与 hook 扩展点
- 本地 HTTP API 和打包好的前端 UI

### 快速开始

#### 从源码安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

验证安装：

```bash
cts --help
cts --version
```

#### 运行示例

先检查并编译示例配置：

```bash
cts --config examples/demo/cts.yaml config lint --compile --format json
```

查看动态生成的命令：

```bash
cts --config examples/demo/cts.yaml demo echo --help
```

通过挂载命令路径调用：

```bash
cts --config examples/demo/cts.yaml demo echo --text hello --upper --output json
```

通过稳定 mount ID 调用：

```bash
cts --config examples/demo/cts.yaml invoke demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

### 最快上手

这一部分目标只有一个：先跑通一次，不需要你先手写配置文件。

`cts` 在不传 `--config` 时，会默认使用用户目录下的 `~/.cts/config.yaml`。如果这个文件还不存在，像 `import cli`、`source add`、`mount add` 这样的命令会自动创建它。

#### 1. 用一步导入接入一个本地 CLI

如果你已经有一个本地 CLI，最短路径不再是先写 `source` 再写 `mount`，而是直接导入：

```bash
cts import cli demo_cli python3 ./demo_cli.py greet \
  --from help \
  --apply
```

这一步默认会完成三件事：

- 把一个现成 CLI operation 导入到 `source.operations`
- 自动生成一个 mount
- 默认给出可用的命令路径和稳定 mount ID

如果你想先看预览，不真正改配置，可以先去掉 `--apply`：

```bash
cts import cli demo_cli python3 ./demo_cli.py greet \
  --from help \
  --format json
```

如果你更喜欢交互式方式，也可以：

```bash
cts import wizard
```

#### 2. 立即执行它

通过命令路径执行：

```bash
cts demo echo --text hello --upper --output json
```

通过稳定 mount ID 执行：

```bash
cts invoke demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

如果你想先只看执行计划：

```bash
cts explain demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

#### 3. 看看当前已经挂了什么

```bash
cts source list
cts mount list
cts inspect mount demo-echo --format json
```

### 进阶用法

跑通之后，再看下面这些更适合真实项目的方式。

#### 1. 手写配置文件挂载命令

最常见的进阶方式，是把 source 和 mount 明确写进 YAML。

示例配置：

```yaml
version: 1

sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
      manifest: ./echo-manifest.yaml

mounts:
  - id: demo-echo
    source: demo_cli
    operation: echo_json
    command:
      path: [demo, echo]
```

对应的 manifest 例子：

```yaml
version: 1
operations:
  - id: echo_json
    title: Echo JSON
    input_schema:
      type: object
      required: [text]
      properties:
        text:
          type: string
        upper:
          type: boolean
          default: false
    argv_template:
      - python3
      - -c
      - |
        import json, sys
        text = sys.argv[1]
        upper = sys.argv[2].lower() == "true"
        if upper:
            text = text.upper()
        print(json.dumps({"text": text, "upper": upper}))
      - "{text}"
      - "{upper}"
    output:
      mode: json
```

这套完整可运行示例就在：

- [examples/demo/cts.yaml](examples/demo/cts.yaml)
- [examples/demo/echo-manifest.yaml](examples/demo/echo-manifest.yaml)

#### 2. manifest 不是唯一方式

对 `cli` source 来说，`manifest` 不是唯一选择。你也可以把 operation 直接写在 `source.operations` 里。

但需要注意：

- `mount` 只是负责“挂载”
- 真正可执行的 operation 信息，还是必须提前定义好
- 对 `cli` source，当前最稳妥的方式仍然是 `manifest-first`

#### 3. 怎么接一个 MCP

如果你有一个 MCP server，可以把它作为 `mcp` source 接进来，然后批量导入它发现到的 tools。

示例：

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

mounts:
  - id: my-mcp
    source: my_mcp
    select:
      include: ["*"]
    command:
      under: [my]
```

先验证 discovery：

```bash
cts --config cts.yaml source test my_mcp --discover --format json
```

再批量导入 mounts：

```bash
cts --config cts.yaml mount import my_mcp --under my
```

导入完成后，就可以执行类似：

```bash
cts --config cts.yaml my <tool-name> ...
```

### 常用命令

```bash
cts --config cts.yaml config build --format yaml
cts --config cts.yaml config lint --compile --format json
cts --config cts.yaml source list
cts --config cts.yaml mount list
cts --config cts.yaml inspect mount demo-echo --format json
cts --config cts.yaml explain demo-echo --input-json '{"text":"hello"}' --format json
cts --config cts.yaml serve http
cts --config cts.yaml ui --open
```

当前主要命令组包括：

- `config`
- `source`
- `mount`
- `invoke`
- `explain`
- `inspect`
- `catalog`
- `sync`
- `reconcile`
- `auth`
- `secret`
- `serve`
- `ui`
- `workflow`
- `docs`

### UI

`cts` 自带一个前端控制台，用来查看 sources、mounts、catalog、runs、drift、extensions 和 auth 相关状态。

只启动 HTTP API：

```bash
cts --config examples/demo/cts.yaml serve http
```

同时启动 HTTP API 和内置 UI：

```bash
cts --config examples/demo/cts.yaml serve http --ui --open
```

前端开发说明见 [frontend/README.md](frontend/README.md)。

### 示例文件

- Demo 配置：[examples/demo/cts.yaml](examples/demo/cts.yaml)
- Demo manifest：[examples/demo/echo-manifest.yaml](examples/demo/echo-manifest.yaml)
- Split config 示例：[examples/split-demo/cts.yaml](examples/split-demo/cts.yaml)
- MCP 示例：[examples/mcp/bing-cts.yaml](examples/mcp/bing-cts.yaml)

### 项目结构

```text
src/cts/          Python 包
tests/            测试
examples/         可运行示例配置
docs/             架构与设计文档
frontend/         前端控制台与前端文档
```

### 文档

更完整的项目文档都在 [`docs/`](docs/) 下，建议阅读顺序：

1. [Usage 实战文档](docs/usage/README.md)
2. [安装与使用指南](docs/15-install-and-usage.md)
3. [RFC 总纲：主架构](docs/00-rfc-master-architecture.md)
4. [平台总览](docs/01-platform-overview.md)
5. [配置模型](docs/02-config-model.md)
6. [Provider SDK](docs/03-provider-sdk.md)
7. [运行时设计](docs/04-runtime-execution.md)
8. [AI 友好架构](docs/06-ai-friendly-architecture.md)
9. [当前状态与路线图](docs/14-status-and-roadmap.md)

补充文档：

- [Schema 漂移与对账](docs/13-schema-drift-and-reconciliation.md)
- [可靠性与限流](docs/12-reliability-and-rate-limits.md)
- [认证生命周期](docs/11-auth-lifecycle.md)
- [前端 README](frontend/README.md)

### 开发

运行测试：

```bash
pytest
```

运行单个测试文件：

```bash
pytest tests/test_demo_cli.py
```

构建前端：

```bash
cd frontend/app
npm install
npm run build
```

### 状态

当前版本：`0.1.0`

项目目前处于活跃的 MVP 阶段。整体架构、CLI 和 UI 都已经可运行，代码仓库里也有测试和打包产物，但更完整的产品化能力还在持续演进中。

### License

[MIT](LICENSE)

## English

`cts` is a configurable capability transit system for turning APIs, MCP servers, CLI tools, and local scripts into one stable command surface.

It gives you a unified way to model, mount, and expose capabilities from different backends through a consistent CLI, HTTP API, and local web UI.

### Why cts

Modern teams often have useful capabilities scattered across:

- internal HTTP APIs
- OpenAPI and GraphQL services
- MCP servers
- existing CLI tools
- shell scripts and local automation

`cts` brings those capabilities into one contract-driven layer so they can be discovered, mounted, invoked, documented, and governed in a consistent way.

Core model:

```text
source -> operation -> mount -> surface
```

- `source`: where a capability comes from
- `operation`: one callable action in that source
- `mount`: a stable ID and command path for the operation
- `surface`: how it is exposed, such as CLI, HTTP, or UI

### What It Can Do Today

The current repository already includes a working Python MVP with:

- config compilation with single-file and split-file configs
- dynamic CLI command generation from mounted operations
- stable invocation by `mount.id`
- providers for `cli`, `shell`, `http`, `openapi`, `graphql`, and `mcp`
- discovery, schema caching, sync, drift inspection, and reconciliation foundations
- auth and secret management primitives
- plugin and hook extension points
- a local HTTP API and bundled frontend UI

### Quick Start

#### Install From Source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

Verify the CLI:

```bash
cts --help
cts --version
```

#### Try The Demo

Lint and compile the example config:

```bash
cts --config examples/demo/cts.yaml config lint --compile --format json
```

See the generated command:

```bash
cts --config examples/demo/cts.yaml demo echo --help
```

Invoke it through the mounted command path:

```bash
cts --config examples/demo/cts.yaml demo echo --text hello --upper --output json
```

Invoke the same operation through its stable mount ID:

```bash
cts --config examples/demo/cts.yaml invoke demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

### Fastest Start

This section has one goal: get something running first, without asking you to hand-write a config file.

If you do not pass `--config`, `cts` uses the default config location at `~/.cts/config.yaml`. If that file does not exist yet, commands like `import cli`, `source add`, and `mount add` will create it for you.

#### 1. Import a local CLI in one step

If you already have a CLI, the shortest path is now the unified import command:

```bash
cts import cli demo_cli python3 ./demo_cli.py greet \
  --from help \
  --apply
```

This single command will:

- import one CLI operation into `source.operations`
- create a mount automatically
- generate a usable command path and stable mount id

If you want a preview first, omit `--apply`:

```bash
cts import cli demo_cli python3 ./demo_cli.py greet \
  --from help \
  --format json
```

You can also use the interactive wizard:

```bash
cts import wizard
```

#### 2. Run it immediately

Run by command path:

```bash
cts demo echo --text hello --upper --output json
```

Run by stable mount ID:

```bash
cts invoke demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

Preview the execution plan:

```bash
cts explain demo-echo \
  --input-json '{"text":"hello","upper":true}' \
  --format json
```

#### 3. Inspect what is mounted

```bash
cts source list
cts mount list
cts inspect mount demo-echo --format json
```

### Advanced Usage

Once you have something working, these are the more realistic project workflows.

#### 1. Mount commands through YAML config

The most common advanced pattern is to declare sources and mounts explicitly in YAML.

Example config:

```yaml
version: 1

sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
      manifest: ./echo-manifest.yaml

mounts:
  - id: demo-echo
    source: demo_cli
    operation: echo_json
    command:
      path: [demo, echo]
```

Example manifest:

```yaml
version: 1
operations:
  - id: echo_json
    title: Echo JSON
    input_schema:
      type: object
      required: [text]
      properties:
        text:
          type: string
        upper:
          type: boolean
          default: false
    argv_template:
      - python3
      - -c
      - |
        import json, sys
        text = sys.argv[1]
        upper = sys.argv[2].lower() == "true"
        if upper:
            text = text.upper()
        print(json.dumps({"text": text, "upper": upper}))
      - "{text}"
      - "{upper}"
    output:
      mode: json
```

The full runnable example is in:

- [examples/demo/cts.yaml](examples/demo/cts.yaml)
- [examples/demo/echo-manifest.yaml](examples/demo/echo-manifest.yaml)

#### 2. A manifest is not the only option

For `cli` sources, a manifest is not the only way to define operations. You can also declare operations directly in `source.operations`.

Still, keep this in mind:

- a `mount` only attaches an operation to the command tree
- the executable operation definition still needs to exist somewhere
- for `cli` sources, `manifest-first` is currently the most stable approach

#### 3. Add an MCP server

If you already have an MCP server, you can add it as an `mcp` source and batch-import discovered tools.

Example:

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

mounts:
  - id: my-mcp
    source: my_mcp
    select:
      include: ["*"]
    command:
      under: [my]
```

Validate discovery:

```bash
cts --config cts.yaml source test my_mcp --discover --format json
```

Batch import mounts:

```bash
cts --config cts.yaml mount import my_mcp --under my
```

Then run tools like:

```bash
cts --config cts.yaml my <tool-name> ...
```

### Common Commands

```bash
cts --config cts.yaml config build --format yaml
cts --config cts.yaml config lint --compile --format json
cts --config cts.yaml source list
cts --config cts.yaml mount list
cts --config cts.yaml inspect mount demo-echo --format json
cts --config cts.yaml explain demo-echo --input-json '{"text":"hello"}' --format json
cts --config cts.yaml serve http
cts --config cts.yaml ui --open
```

Top-level command groups currently include:

- `config`
- `source`
- `mount`
- `invoke`
- `explain`
- `inspect`
- `catalog`
- `sync`
- `reconcile`
- `auth`
- `secret`
- `serve`
- `ui`
- `workflow`
- `docs`

### UI

`cts` also ships with a bundled frontend console for inspecting sources, mounts, catalog data, runs, drift, extensions, and auth-related state.

Run the HTTP API only:

```bash
cts --config examples/demo/cts.yaml serve http
```

Run the HTTP API with the bundled UI:

```bash
cts --config examples/demo/cts.yaml serve http --ui --open
```

For frontend development, see [frontend/README.md](frontend/README.md).

### Example Files

- Demo config: [examples/demo/cts.yaml](examples/demo/cts.yaml)
- Demo manifest: [examples/demo/echo-manifest.yaml](examples/demo/echo-manifest.yaml)
- Split config example: [examples/split-demo/cts.yaml](examples/split-demo/cts.yaml)
- MCP example: [examples/mcp/bing-cts.yaml](examples/mcp/bing-cts.yaml)

### Project Structure

```text
src/cts/          Python package
tests/            Test suite
examples/         Runnable sample configurations
docs/             Architecture and design documents
frontend/         Frontend console and UI docs
```

### Documentation

Most in-depth project documents are currently written in Chinese and live under [`docs/`](docs/). A good reading order is:

1. [Practical usage docs](docs/usage/README.md)
2. [Install and usage guide](docs/15-install-and-usage.md)
3. [Master architecture RFC](docs/00-rfc-master-architecture.md)
4. [Platform overview](docs/01-platform-overview.md)
5. [Config model](docs/02-config-model.md)
6. [Provider SDK](docs/03-provider-sdk.md)
7. [Runtime execution](docs/04-runtime-execution.md)
8. [AI-friendly architecture](docs/06-ai-friendly-architecture.md)
9. [Install, current status, and roadmap](docs/14-status-and-roadmap.md)

Additional references:

- [Schema drift and reconciliation](docs/13-schema-drift-and-reconciliation.md)
- [Reliability and rate limits](docs/12-reliability-and-rate-limits.md)
- [Auth lifecycle](docs/11-auth-lifecycle.md)
- [Frontend README](frontend/README.md)

### Development

Run tests:

```bash
pytest
```

Run a focused test file:

```bash
pytest tests/test_demo_cli.py
```

Build the frontend bundle:

```bash
cd frontend/app
npm install
npm run build
```

### Status

Current version: `0.1.0`

The project is in an active MVP stage: the architecture is already substantial, the CLI and UI are runnable, and the codebase includes tests and package artifacts, but the broader product surface is still evolving.

### License

[MIT](LICENSE)
