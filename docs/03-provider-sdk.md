# Provider SDK 与接入协议

## 1. 目标

Provider 层决定了 `cts` 能否长期扩展。设计不当，后面每接一种新协议都要改核心；设计得当，核心只需要理解统一 operation，不需要理解具体协议细节。

## 2. 统一抽象

所有 Provider 都应实现统一的能力模型。

### 2.1 Provider 元信息

```python
class ProviderMetadata(BaseModel):
    name: str
    provider_type: str
    version: str | None = None
    api_version: str | None = None
    min_cts_version: str | None = None
    supports_discovery: bool = True
    supports_streaming: bool = False
    supports_healthcheck: bool = True
    supports_profiles: bool = True
```

### 2.2 Operation 描述

```python
class OperationDescriptor(BaseModel):
    id: str
    source: str
    provider_type: str
    title: str
    stable_name: str | None = None
    description: str | None = None
    kind: Literal["action", "query", "stream", "job"]
    tags: list[str] = []
    group: str | None = None
    risk: Literal["read", "write", "destructive", "privileged"] = "read"
    input_schema: dict = {}
    output_schema: dict | None = None
    examples: list[dict] = []
    supported_surfaces: list[str] = ["cli", "invoke"]
    transport_hints: dict = {}
```

### 2.2.1 Capability Card

为了让 AI 和自动化系统直接消费，建议在 operation descriptor 之外再生成一个 northbound capability card。

```python
class CapabilityCard(BaseModel):
    mount_id: str
    stable_name: str
    command_path: list[str]
    summary: str
    risk: str
    input_schema: dict
    output_schema: dict | None = None
    examples: list[dict] = []
    requires_confirmation: bool = False
    supports_dry_run: bool = True
    supported_surfaces: list[str] = ["cli", "invoke"]
```

### 2.2.2 Help Descriptor

为了支持动态挂载命令的 `--help`，建议引入统一帮助模型，而不是由每个 provider 直接输出最终文本。

```python
class HelpDescriptor(BaseModel):
    summary: str | None = None
    description: str | None = None
    arguments: list[dict] = []
    examples: list[str] = []
    notes: list[str] = []
    source_origin: str | None = None
```

### 2.2.3 Schema Provenance

不同 provider 获取参数格式的方式不同，建议保留 schema 来源和可信度。

```python
class SchemaProvenance(BaseModel):
    strategy: Literal["authoritative", "declared", "probed", "inferred", "manual"]
    origin: str | None = None
    confidence: float = 1.0
```

### 2.3 调用请求

```python
class InvokeRequest(BaseModel):
    source: str
    operation_id: str
    args: dict
    profile: str | None = None
    cwd: str | None = None
    env: dict[str, str] = {}
    stream: bool = False
    timeout_seconds: int | None = None
    dry_run: bool = False
```

### 2.4 调用结果

```python
class InvokeResult(BaseModel):
    ok: bool
    status_code: int | None = None
    data: Any = None
    text: str | None = None
    stderr: str | None = None
    metadata: dict = {}
```

### 2.5 执行计划

AI 友好架构建议支持 explain/dry-run，因此运行时和 provider 最好都能返回执行计划。

```python
class ExecutionPlan(BaseModel):
    source: str
    operation_id: str
    provider_type: str
    normalized_args: dict
    risk: str
    requires_confirmation: bool = False
    rendered_request: dict | None = None
```

## 3. Provider 接口

建议 Python 核心里定义：

```python
class Provider(Protocol):
    def discover(self, source_config, context) -> list[OperationDescriptor]:
        ...

    def get_operation(self, source_config, operation_id, context) -> OperationDescriptor:
        ...

    def get_schema(self, source_config, operation_id, context) -> tuple[dict, SchemaProvenance] | None:
        ...

    def get_help(self, source_config, operation_id, context) -> HelpDescriptor | None:
        ...

    def refresh_auth(self, source_config, context) -> dict | None:
        ...

    def plan(self, source_config, request: InvokeRequest, context) -> ExecutionPlan:
        ...

    def invoke(self, source_config, request: InvokeRequest, context) -> InvokeResult:
        ...

    def healthcheck(self, source_config, context) -> dict:
        ...
```

可选增强：

- `complete()` 提供 shell completion
- `auth_bootstrap()` 帮助登录
- `refresh_auth()` 处理 token / session 刷新
- `stream_invoke()` 处理流式输出
- `list_surfaces()` 声明适合暴露到哪些 northbound surface
- `get_schema()` 返回 schema 与 provenance
- `get_help()` 返回 provider 级帮助片段

## 4. 内置 Provider 清单

建议第一阶段内置以下 Provider。

### 4.1 MCP Provider

职责：

- 使用 `mcp-cli` 连接 MCP server
- 发现 tools、prompts、resources
- 把 tool 映射成 operation
- 执行时调用 `mcp-cli call-tool`

为什么用 adapter 而不是内嵌耦合：

- 当前已有成熟 `mcp-cli`
- 以后可切换原生 MCP SDK
- 核心层不需要理解 MCP transport

建议细分：

- `mcp_tool` 映射为 action/query
- `mcp_prompt` 映射为 prompt-like operation
- `mcp_resource` 映射为 read-only operation

帮助信息来源建议：

- tool description
- input schema property descriptions
- prompt/resource 描述
- MCP server 名称与目标类型

### 4.2 HTTP Provider

职责：

- 根据配置描述执行 HTTP 请求
- 做认证、路径参数替换、query/body 组装
- 支持 JSON、form、multipart、raw body

它适合：

- 手工接入少量 API
- 内部系统无 OpenAPI 文档
- 快速验证集成

帮助信息来源建议：

- mount help 配置
- path/method
- 参数映射描述
- auth/risk 提示

### 4.3 OpenAPI Provider

职责：

- 读取 OpenAPI 文档
- 把 path + method 归一化为 operation
- 根据 schema 自动生成参数

它适合：

- 文档完备的 REST API
- 希望批量导入大量接口

帮助信息来源建议：

- operation summary
- operation description
- parameter descriptions
- request body schema descriptions
- response summary

### 4.4 GraphQL Provider

职责：

- 从 introspection 或静态 schema 发现 query/mutation
- 将 operation name 归一化
- 支持 fragments、variables、preset query 模板

帮助信息来源建议：

- field description
- variable descriptions
- operation text 或模板说明

### 4.5 CLI Provider

CLI Provider 是长期第二核心，仅次于 HTTP/OpenAPI。

职责：

- 对任意 CLI 进行封装
- 根据 manifest 或 adapter 暴露命令
- 管理参数、环境变量、工作目录、超时和输出解析

必须支持两种模式：

#### 模式 A：Manifest 驱动

由用户或工具提供一个 YAML/JSON manifest，显式定义命令能力。

优点：

- 可控
- 易审计
- 对复杂 CLI 兼容性最好

帮助信息来源建议：

- manifest summary / description
- option help
- output mode
- 底层命令示例

#### 模式 B：Adapter 驱动

给某个 CLI 写专用 provider 或 plugin，用更丰富的逻辑做 discovery 和 invoke。

适合：

- `kubectl`
- `gh`
- `terraform`
- 自家内部 CLI

### 4.6 Shell Provider

适合：

- 接管现有脚本目录
- 让 shell 脚本也能纳入统一命令树

它应该比 CLI Provider 更严格，因为 shell 风险更高。

### 4.7 Workflow / Composite Provider

这个 provider 不直接对接外部协议，而是对接 `cts` 自己已经接入的 operation。

职责：

- 组合多个 operation
- 处理步骤输入输出映射
- 处理中止、重试、补偿和结果聚合

它的意义在于让“跨多个 API/CLI 的组合能力”也能成为一等 operation。

## 5. CLI 接入的三层模型

因为“任意 CLI”无法可靠自动 introspect，推荐明确区分三层接入方式。

### 5.1 轻量包装

适合简单命令。

```yaml
sources:
  jq_cli:
    type: cli
    executable: jq

mounts:
  - id: jq-format
    source: jq_cli
    operation: format
    provider_config:
      argv: ["jq", "."]
```

### 5.2 Manifest 包装

适合成熟 CLI，能够长期维护。

```yaml
operations:
  - id: repo_list
    argv_template: ["gh", "repo", "list", "{owner}", "--limit", "{limit}"]
    input_schema:
      type: object
      properties:
        owner:
          type: string
        limit:
          type: integer
```

### 5.3 专用 Adapter

适合需要复杂逻辑、自动 discovery、上下文联动的 CLI。

例如：

- 从 `gh api` 获取 schema
- 从 `kubectl api-resources` 构建 operation
- 从 `terraform providers schema -json` 构建映射

## 6. Manifest 设计建议

CLI manifest 应至少包含：

```yaml
version: 1
executable: gh
operations:
  - id: repo_list
    title: List repositories
    risk: read
    argv_template: ["gh", "repo", "list", "{owner}", "--limit", "{limit}"]
    input_schema:
      type: object
      required: [owner]
      properties:
        owner:
          type: string
        limit:
          type: integer
          default: 30
    output:
      mode: json
```

输出模式建议支持：

- `json`
- `text`
- `lines`
- `table`
- `regex`
- `custom_parser`

## 7. 外部 Provider 插件协议

为了不把所有 Provider 都写死在 Python 进程里，建议支持外部插件。

在真正进入外部协议之前，核心 SHOULD 先支持一层更轻量的 in-process plugin extension：

- plugin 注册新的 provider type
- source 直接使用 plugin 注册出来的 type
- plugin provider 与内置 provider 共享同一 Provider 接口
- plugin 可以再额外注册 hook handler

也就是说，Provider SDK 的扩展顺序建议是：

1. 内置 provider
2. Python in-process plugin provider
3. 外部 plugin protocol

### 7.1 推荐协议

建议使用 `JSON-RPC over stdio` 或 `NDJSON over stdio`。

优势：

- 多语言可实现
- 易调试
- 生命周期清晰
- 与 CLI 工具生态兼容

### 7.2 最小插件接口

建议支持这些方法：

- `handshake`
- `discover`
- `get_operation`
- `plan`
- `invoke`
- `healthcheck`

### 7.3 示例消息

```json
{"id":"1","method":"discover","params":{"source":"internal_mesh"}}
{"id":"1","result":{"operations":[{"id":"deploy_service","kind":"action"}]}}
```

### 7.4 适用场景

- 某种协议只有 JS SDK，Python 不方便
- 团队想用 Go 写高性能 adapter
- 某个 CLI 的专用逻辑太复杂，不想进核心仓库
- 需要对接 gRPC、WebSocket、SQL、消息队列或内部 RPC

## 7.5 Hook SDK

plugin 除了注册 provider，还应能注册 hook handler。

推荐最小模型：

```python
class HookContext(BaseModel):
    event: str
    plugin_name: str
    payload: dict
    app: Any | None = None
    hook_config: dict = {}
```

推荐 handler 约定：

```python
def normalize_args(ctx: HookContext) -> dict | None:
    payload = dict(ctx.payload)
    ...
    return payload
```

建议支持三类 hook：

- `before`
  - 可以改写有限输入，如 args、runtime、help payload
- `after`
  - 可以增强结果，如 metadata、description、result summary
- `error`
  - 可以做留痕、分类增强、告警派发，但不应默认吞掉主错误

Hook SDK 必须遵守：

- handler 输入输出稳定
- fail mode 明确
- 不绕过统一日志、错误和 run_id 链路
- 不直接破坏 mount/source/provider 的稳定合同

## 8. 南向 Provider 与北向 Surface 的职责边界

为了避免架构混乱，建议明确区分：

- Provider 负责接入外部能力
- Surface 负责把统一能力暴露给外部消费者

例如：

- `mcp_cli` provider 是 southbound
- `cts serve mcp` 是 northbound
- `http` provider 是 southbound
- `cts serve http` 是 northbound

这能避免“既是接入协议，又是暴露协议”的概念混杂。

## 9. MCP Provider 详细建议

`mcp-cli` 目前可以承担执行器角色。

接入方式建议：

### 9.1 Discovery

优先级建议：

1. 通过 `mcp-cli` 的交互或脚本模式获取 tool/resource/prompt 列表
2. 归一化为 operation
3. 写入本地 discovery cache

### 9.2 Invoke

基于 operation 类型分流：

- tool -> `mcp-cli call-tool`
- resource -> `mcp-cli read-resource`
- prompt -> `mcp-cli get-prompt`

### 9.3 后续演进

未来可加一个 `mcp_native` provider，直接接 MCP SDK。对上层来说，两者共用同一 operation 模型。

## 10. HTTP 与 OpenAPI 的关系

建议不要把它们合并成一个 provider。

原因：

- HTTP provider 偏手工与灵活
- OpenAPI provider 偏自动导入
- 两者发现逻辑、缓存逻辑和 schema 来源不同

但它们可以共用底层：

- auth handler
- request builder
- response parser

## 11. Provider 的能力分级

为了治理复杂度，建议给 provider 定义成熟度级别：

- Level 1：仅 invoke，无 discovery
- Level 2：支持静态 discovery
- Level 3：支持 live discovery
- Level 4：支持 schema、completion、streaming

这很适合 CLI 集成，因为很多 CLI 最开始只能 Level 1 或 Level 2。

## 12. 关键结论

最重要的不是支持多少协议，而是：

- 所有协议都能归一成统一 operation
- 所有协议都能通过 provider 注册
- 所有 provider 都能被 mount 成同样的命令树
- 所有 mount 都能产出稳定的 capability card
- 所有动态挂载命令都能产出动态 `--help`
- 所有能力都能按需暴露到 northbound surface

只要这三点成立，后面加 CLI、加 RPC、加内部网关都不会推翻架构。
