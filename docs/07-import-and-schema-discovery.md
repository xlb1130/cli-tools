# 导入与参数 Schema 发现

## 1. 为什么这层必须单独设计

`cts` 的动态命令树、参数校验、`--help`、前端控制台、AI capability card，最终都依赖同一个核心前提：

- 系统必须知道每个 operation 需要什么参数
- 参数类型、必填、默认值、枚举、描述、示例尽量可得
- 这些信息来自不同协议时，格式和可靠性并不一样

所以“导入”不能只停留在“把操作名导进来”，还必须包含：

- operation 发现
- 参数 schema 获取
- schema 归一化
- schema 可信度标记
- 缓存与人工覆盖

## 2. 统一目标

无论底层是 MCP、OpenAPI、GraphQL、HTTP、CLI 还是 plugin，`cts` 都应尝试产出统一的输入模型：

- `input_schema`
- `required`
- `default`
- `enum`
- `description`
- `examples`
- `schema_source`
- `schema_confidence`

如果拿不到完整 schema，也要明确“拿到了多少”。

## 3. Schema 来源分级

建议把参数格式来源分成五级。

### 3.1 Authoritative

最可靠，直接来自系统的权威定义。

示例：

- OpenAPI spec
- GraphQL introspection
- MCP tool input schema
- CLI 官方 manifest / machine-readable schema

### 3.2 Provider Declared

由 provider/plugin 主动声明。

示例：

- 外部 plugin 返回自己的 operation schema
- 内部 RPC adapter 提供参数定义

### 3.3 Probed

通过一次探测调用、预检请求或只读命令得到更具体的参数格式。

示例：

- MCP 通过 `mcp-cli` 的 discovery / probe 流程获取更具体的 tool 参数格式
- CLI 通过 `--help`、`completion`、schema 子命令获取 option 说明
- 某些 API 提供 describe/metadata endpoint

### 3.4 Inferred

通过样例请求、样例返回、命名规则或弱解析推断。

这层可信度低，必须标记。

### 3.5 Manual Override

人工在配置里覆盖。

这层很重要，因为现实世界里永远有拿不到足够 schema 的系统。

## 4. 统一数据模型建议

建议增加 schema provenance 模型。

```python
class SchemaProvenance(BaseModel):
    source_type: str
    strategy: Literal["authoritative", "declared", "probed", "inferred", "manual"]
    origin: str | None = None
    confidence: float = 1.0
    fetched_at: datetime | None = None
```

并建议为参数保留统一描述：

```python
class ParameterDescriptor(BaseModel):
    name: str
    type: str
    required: bool = False
    default: Any = None
    enum: list[Any] = []
    description: str | None = None
    examples: list[Any] = []
```

最终绑定到：

```python
class NormalizedSchema(BaseModel):
    input_schema: dict
    parameters: list[ParameterDescriptor]
    provenance: SchemaProvenance
```

## 5. 导入总流程

建议把导入拆成 6 个阶段。

### 5.1 发现 operation

先知道有哪些操作。

### 5.2 获取参数格式

对每个 operation 获取 schema 或等价信息。

### 5.3 归一化

把来源不同的描述统一成 `input_schema + ParameterDescriptor`。

### 5.4 补充帮助信息

把参数说明、默认值、示例带到 help/capability card。

### 5.5 缓存

把 schema、来源、置信度、抓取时间写入 discovery cache。

### 5.6 人工覆盖

允许 mount 或 source 级配置覆盖错误或缺失的参数定义。

## 6. 各类 Provider 的参数获取策略

## 6.1 MCP

对于 MCP，建议分两层：

### 第一层：标准 discovery

优先使用 MCP tool 自带的 input schema 和描述。

### 第二层：可选 probe

按你的设想，允许通过 `mcp-cli` 做一次 discovery/probe 流程，补拿更具体的参数格式、示例或 tool 元信息。

适合场景：

- 工具本身声明比较粗糙
- 需要更详细的字段描述
- 需要在导入时生成更好的 `--help`

注意：

- probe 默认应限制为只读或安全模式
- 不应对 write/destructive tool 盲目探测

## 6.2 OpenAPI

OpenAPI 是最标准的一类。

参数来源：

- path params
- query params
- headers
- cookies
- request body schema
- operation summary/description

这类通常属于 `authoritative`。

## 6.3 GraphQL

来源：

- introspection
- variable definitions
- input object types
- field descriptions

GraphQL 难点在于：

- 有时需要预定义 operation 模板
- 不是所有 query/mutation 都适合直接暴露成 CLI

## 6.4 手工 HTTP

手工 HTTP source 常常没有权威 schema。

建议来源优先级：

1. mount 显式配置参数
2. provider declared schema
3. 样例请求模板
4. metadata endpoint probe
5. inferred

## 6.5 CLI

CLI 是最复杂的一类。

建议支持四种来源：

### A. 官方/人工 manifest

最推荐。

### B. `--help`

从 option 列表、说明、默认值中提取。

### C. completion / man page / schema 子命令

比纯 `--help` 更结构化时，优先使用。

当前 MVP 已有：

- `cts source import-help`
- `cts source import-completion`
- `cts source import-manpage`
- `cts source import-schema`

其中 `import-manpage` 当前先支持 plain-text man page 输入，例如：

- `man foo | col -b`
- 已经导出的 `.txt` / `.man.txt`

它适合作为 `--help` 信息不足、但还拿不到 machine-readable schema 时的中间层。

`import-schema` 则适合 CLI 已经暴露 machine-readable 描述的场景，例如：

- `schema --json`
- `describe --format json`
- `options --json`

当前实现支持三类 JSON 载荷自动识别：

- 完整 `operation` 对象
- `input_schema + option_bindings`
- `options[]` 轻量结构

### D. probe 子命令

例如某些 CLI 提供：

- `schema -json`
- `describe`
- `options --json`

如果 CLI 支持 machine-readable schema，应优先走这个分支。

## 6.6 Plugin / 内部协议

要求 plugin/provider 直接返回：

- operation
- schema
- provenance

这是最干净的长期扩展方式。

## 7. 导入策略配置建议

建议在 source 的 `discovery` 下增加 schema 获取策略：

```yaml
sources:
  github_mcp:
    type: mcp
    discovery:
      mode: live
      schema_strategy: hybrid
      probe:
        enabled: true
        policy: safe_only
        timeout_seconds: 5
```

推荐字段：

- `schema_strategy`
  - `authoritative`
  - `probe`
  - `infer`
  - `manual`
  - `hybrid`
- `probe.enabled`
- `probe.policy`
  - `disabled`
  - `safe_only`
  - `readonly_only`
  - `all`
- `probe.timeout_seconds`
- `cache_ttl`

## 8. Mount 级人工覆盖

即使 source 能自动导入 schema，mount 级仍要允许覆盖。

```yaml
mounts:
  - id: jira-get-issue
    source: jira_http
    operation: get_issue
    params:
      key:
        flag: --key
        required: true
        type: string
        help: 工单 key，例如 ABC-123
```

适合：

- 自动导入不够友好
- 想把对象参数扁平化
- 想修正 provider 不准确的字段说明

## 9. 缓存与置信度

建议 discovery cache 对 schema 记录：

- schema hash
- provenance strategy
- confidence
- fetched_at
- source version

这样前端和 CLI 都可以显示：

- 这是来自 OpenAPI 的权威 schema
- 这是来自 CLI `--help` 的弱结构化 schema
- 这是人工覆盖后的 schema

## 10. 对 `--help` 和前端的影响

动态 `--help` 不应该只显示“有这个参数”，还应能显示“这个参数信息来自哪里”。

前端详情页建议展示：

- 参数来源
- schema 置信度
- 是否人工覆盖
- 最近抓取时间

这样在弱 schema 场景下，用户能理解为什么某些帮助信息不完整。

## 11. 对 AI 的影响

AI 使用 `cts` 时也需要知道 schema 是否可靠。

建议 capability card 或 catalog 附带：

- `schema_source`
- `schema_confidence`
- `schema_strategy`

这能帮助 agent 判断：

- 是否可以直接调用
- 是否应该先走 explain
- 是否需要人工确认

## 12. Phase 1 建议

第一版建议只做三类强路径：

- OpenAPI：直接吃 spec
- MCP：先吃 tool schema，再按需 probe
- CLI：manifest-first，`--help` 只做辅助

这样能控制复杂度，同时把架构留足。

## 13. 最终结论

`cts` 的导入层应被理解为：

- 不是简单“导入命令名”
- 而是“导入 operation + 参数 schema + 帮助元数据 + provenance”

只有这样，后面的：

- 动态命令执行
- 动态 `--help`
- 前端展示
- AI 调用

才会真正稳定。
