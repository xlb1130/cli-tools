# cts 平台总览

本文是面向快速理解的概览文档。涉及主架构、稳定合同和关键决定时，以 [RFC-0001: cts 统一能力平面主架构](00-rfc-master-architecture.md) 为准。

## 1. 背景与目标

`cts` 是一个统一命令编排平台，不把自己限定为某一种协议的客户端。它的核心职责是：

- 把任意能力源接入为统一的 `source`
- 把能力源暴露的动作抽象为统一的 `operation`
- 把 operation 映射为本地 `cts` 层级命令
- 负责参数验证、路由执行、结果格式化、安全控制与缓存

目标不是只做一个 MCP wrapper，而是做一个可以长期生长的命令平面。

一个成熟的 `cts` 应该同时支持：

- MCP 服务，通过 `mcp-cli` 或未来的原生 SDK 接入
- HTTP API，通过手工配置或 OpenAPI 导入
- GraphQL API，通过 schema 或静态描述导入
- gRPC、WebSocket、SSE、SQL、内部 RPC 等协议，通过 plugin 或专用 provider 接入
- 任意本地 CLI，例如 `gh`、`kubectl`、`terraform`、`docker`
- Shell 脚本、Python 脚本、Node 脚本
- 未来的数据库、消息队列、内部服务网关、RPC 网关

## 2. 设计原则

### 2.1 协议无关

核心层不能绑定在 MCP、HTTP 或 CLI 任何一种协议上。上层统一面对的只能是 capability 和 operation。

### 2.2 Provider 一等公民

任何接入方式都必须通过统一 Provider 抽象进入系统。MCP 只是一个内置 Provider，不是系统中心。

### 2.3 配置驱动，但允许代码扩展

大多数集成应该能通过 YAML 配置完成。复杂场景允许用 Python 插件或外部 adapter 扩展。

### 2.4 动态命令树

`cts` 不应要求所有命令在发布时写死。命令树应按配置和缓存动态生成。

动态命令不只是“能执行”，还必须完整支持 `--help`、补全和示例输出。

### 2.5 兼顾可发现性与可治理性

动态不代表混乱。必须提供 inspect、sync、doctor、policy、audit 等治理能力。

同时必须提供贯穿配置加载、导入、schema 获取、命令执行和 northbound surface 的结构化日志。

### 2.6 CLI 也是一等输入源

很多真实世界能力根本不是 API，而是成熟 CLI。`cts` 必须把 CLI 接入放在架构中心考虑，而不是边缘补丁。

### 2.7 AI 与自动化优先

`cts` 不仅要对人类友好，也必须对 AI/Agent/自动化友好。每个 mount 都应具备稳定 id、机器可读 schema、结构化输出、可解释执行计划和稳定错误模型。

### 2.8 南向接入与北向暴露分离

南向负责接外部系统，北向负责把统一后的能力再次暴露给人类和机器。`cts` 既要能“接很多系统”，也要能“以统一方式被别的系统使用”。

## 3. 非目标

`cts` 第一阶段不追求：

- 自己实现每一种协议的全部高级特性
- 替代已有专用工具的全部交互式体验
- 自动把任意未知 CLI 完美反射成命令树
- 代替配置管理系统、密钥管理系统或 CI 系统

## 4. 核心概念

### 4.1 Source

`source` 表示能力来源，是系统内最重要的注册对象之一。

示例：

- 一个 MCP server
- 一个 REST API 服务
- 一个 OpenAPI 文档
- 一个 GraphQL endpoint
- 一个本地 CLI 程序
- 一个 shell 脚本目录

Source 关注“从哪里来”。

### 4.2 Operation

`operation` 是 `cts` 统一抽象后的可执行能力单位。

一个 operation 通常包括：

- 唯一 id
- 类型，例如 `action`、`query`、`stream`
- 输入 schema
- 输出 schema 或输出提示
- 描述、标签、分组、风险等级
- 执行元信息，例如超时、幂等性、是否支持流式输出

Operation 关注“能做什么”。

### 4.3 Mount

`mount` 把一个 operation 挂载到 `cts` 命令树中的某个路径。

例如：

- `github:list_issues` -> `cts dev github issues list`
- `jira:get_issue` -> `cts ops jira issue get`
- `gh repo list` -> `cts dev gh repo list`

Mount 关注“用户如何调用”。

### 4.4 Provider

`provider` 是一种接入器，负责从某类 source 中发现 operation、执行 operation、返回统一结果。

示例：

- `mcp_cli` provider
- `http` provider
- `openapi` provider
- `graphql` provider
- `cli` provider
- `shell` provider

Provider 关注“怎么接入和执行”。

### 4.5 Profile

`profile` 是运行上下文，用来切换环境、凭证、默认参数、输出偏好。

例如：

- `dev`
- `staging`
- `prod`
- `personal`

### 4.6 Policy

`policy` 控制风险，例如：

- 某些命令只能在特定 profile 可见
- 某些操作需要确认
- 某些 CLI 只能在 allowlist 中执行
- 某些 source 不允许 `--all` 自动挂载

### 4.7 Surface

`surface` 表示 `cts` 对外暴露能力的北向接口。

典型 surface：

- 交互式 CLI 路径，例如 `cts dev github issues list`
- 稳定机器入口，例如 `cts invoke github-list-issues`
- 本地 HTTP/JSON-RPC 服务
- 本地 MCP bridge
- 本地 Web 控制台

Surface 关注“统一能力如何再次被消费”。

### 4.8 Workflow / Composite Operation

单个 operation 只代表一个能力调用，但真实业务往往需要把多个系统串起来。因此长期建议支持 workflow/composite operation，把多个 source 的 operation 组合成一个高层能力。

## 5. 系统分层

推荐把 `cts` 分成六层。

### 5.1 Northbound Surface 层

负责所有用户可见命令：

- 稳定机器调用入口
- 内置管理命令
- 动态业务命令
- 本地 MCP bridge
- 本地 HTTP/JSON-RPC gateway
- 本地 Web 控制台
- 帮助信息
- 自动补全
- 表格、JSON、流式输出

### 5.2 Registry 与配置层

负责：

- 加载全局配置、项目配置、profile 覆盖
- 管理 source、mount、alias、policy、surface
- 解析命令路径与 operation 的映射关系

### 5.3 Discovery 与 Schema 归一化层

负责：

- 从 Provider 发现 capability
- 把 Provider 原生描述转成统一 operation 模型
- 生成可供 AI/自动化消费的 capability catalog
- 缓存发现结果
- 做冲突检测和命名策略

### 5.4 Composition 层

负责：

- 把多个 operation 组合成 workflow
- 管理步骤依赖、变量传递与错误中止策略
- 产出高层复合能力

### 5.5 Execution 层

负责：

- 参数解析与验证
- 调用具体 Provider
- 超时、重试、并发、流式处理
- 审计日志与错误归一化
- 结构化运行日志与 trace id
- dry-run / explain / render-request

### 5.6 Provider 层

负责对接真实世界的能力源：

- `mcp-cli`
- HTTP
- OpenAPI
- GraphQL
- CLI
- Shell
- 外部插件协议

## 6. 命令模型

`cts` 命令应分成两类：

- 平台内置命令
- 动态挂载命令

### 6.1 平台内置命令

建议至少包含：

- `cts source add|list|show|test|remove`
- `cts mount add|import|list|show|remove|sync`
- `cts inspect source|operation|mount|schema`
- `cts invoke <mount-id>`
- `cts explain <mount-id>`
- `cts catalog export`
- `cts serve mcp|http|jsonrpc`
- `cts ui`
- `cts auth login|logout|status`
- `cts cache list|clear`
- `cts doctor`
- `cts sync`

### 6.2 动态挂载命令

这是用户日常真正执行的命令，例如：

```bash
cts dev github issues list --repo owner/repo
cts ops jira issue get --key ABC-123
cts gh repo list --owner my-org
cts cloud kubernetes pods list --namespace prod
```

这些动态挂载命令都必须支持：

- `--help`
- 参数级帮助
- 示例
- 风险提示
- 机器入口提示

而且帮助内容必须根据挂载到的 operation/tool/provider 动态生成，而不是写死一套模板。

### 6.3 稳定机器调用命令

动态命令路径适合人类记忆和团队约定，但机器调用不应依赖可变路径。推荐把 `mount.id` 作为稳定合同，对 AI 和自动化系统暴露：

```bash
cts invoke github-list-issues --input-json '{"repo":"owner/repo"}' --output json
cts explain github-list-issues --input-json '{"repo":"owner/repo"}'
```

## 7. 为什么必须把 CLI 纳入统一模型

很多组织的关键能力不是通过 HTTP 暴露，而是通过 CLI 暴露。典型场景：

- `kubectl`
- `gh`
- `terraform`
- `docker`
- `az`
- `gcloud`
- `aws`
- 各类公司内部命令

如果 `cts` 对 CLI 的支持只是“顺手 exec 一下”，长期会遇到问题：

- 无法发现能力
- 无法做统一参数验证
- 无法做命令树映射
- 无法治理风险
- 无法审计和缓存

因此 CLI 必须有自己的 Provider 与 manifest 机制。

## 8. 典型使用方式

### 8.1 把 MCP 工具挂到 cts 命令树

```bash
cts source add mcp github --config ~/.config/claude_desktop_config.json --server github
cts mount add github list_issues --path "dev github issues list"
cts dev github issues list --repo owner/repo
```

### 8.2 把一个 REST API 挂到 cts

```bash
cts source add http jira --base-url https://jira.example.com/rest/api/3
cts mount add jira get_issue --path "ops jira issue get"
cts ops jira issue get --key ABC-123
```

### 8.3 把成熟 CLI 包成统一命令

```bash
cts source add cli gh --bin gh
cts mount import gh --manifest ./gh-commands.yaml --under dev gh
cts dev gh repo list --owner my-org
```

### 8.4 把脚本目录接进来

```bash
cts source add shell scripts --root ./scripts
cts mount add scripts backup_db --path "ops db backup"
cts ops db backup --target prod
```

### 8.5 用 plugin 扩展新的 provider 和 hook

```yaml
plugins:
  internal_api_ext:
    module: company_cts_plugins.internal_api

hooks:
  - event: invoke.after
    plugin: internal_api_ext
    handler: redact_result

sources:
  internal_mesh:
    type: internal_mesh_api
```

这类 plugin 不只是“接一个 source”，而是给 `cts` 核心注册新的 provider type 和生命周期 hook。

## 9. 长期能力边界

`cts` 长期可以演进为：

- 统一命令入口
- 统一能力目录
- 统一执行与审计平面
- 统一集成适配框架
- 统一 northbound capability gateway
- 统一 workflow 组合层

但它不应该演进为：

- 超大而全的 API 管理平台
- 替代原生客户端的完整 IDE
- 强制所有系统都迁移到同一种协议

## 10. 一句话架构结论

最稳的方向是：

`Python core + Provider/Adapter architecture + Dynamic mount system + Stable machine contract + CLI as first-class source`

MCP 通过 `mcp-cli` 接入只是其中一个 provider，不应主导整个系统设计。
