# 运行时、执行流与安全

## 1. 运行时职责

运行时负责把用户输入的 `cts` 命令变成一次稳定、可审计、可治理的能力调用。

它不关心底层具体是 MCP、HTTP 还是 CLI，只关心：

- 解析到哪个 mount
- 这个 mount 对应哪个 operation
- 参数是否合法
- 是否符合策略
- 交给哪个 provider 执行
- 结果如何呈现

## 2. 执行总流程

建议完整流程如下：

1. 解析 CLI 输入
2. 加载配置层
3. 合并 profile 与覆盖项
4. 解析为稳定 mount id 或命令路径
5. 加载 operation descriptor
6. 将 CLI 参数转换为 operation args
7. 生成 explain/plan 或直接执行
8. 执行策略检查
9. 调用 provider invoke
10. 统一处理输出、错误与审计
11. 根据输出格式渲染结果

整个流程建议生成统一 `run_id`，并在日志、错误、前端历史和审计记录中复用。

## 2.1 日志事件生命周期

建议至少记录这些阶段事件：

- `config_load_start` / `config_load_success` / `config_load_failed`
- `profile_resolved`
- `registry_built`
- `discovery_sync_start` / `discovery_sync_complete`
- `schema_import_start` / `schema_import_complete`
- `help_compile_start` / `help_compile_complete`
- `invoke_start` / `invoke_complete` / `invoke_failed`
- `policy_blocked`
- `surface_request_start` / `surface_request_complete`

这样无论是 CLI、前端页面还是 `cts serve mcp/http/jsonrpc`，都能把完整链路串起来。

## 2.2 Hook 生命周期

除了日志事件，运行时还应暴露正式的 hook 生命周期。

建议第一批事件：

- `discovery.before`
- `discovery.after`
- `discovery.error`
- `help.before`
- `help.after`
- `explain.before`
- `explain.after`
- `explain.error`
- `invoke.before`
- `invoke.after`
- `invoke.error`
- `surface.http.request.before`
- `surface.http.request.after`
- `surface.http.request.error`

推荐规则：

- `before` hook 可做有限输入规范化
- `after` hook 可做有限结果增强
- `error` hook 主要做分类、留痕、告警和恢复辅助
- hook 默认不改变主执行流的成功/失败语义，除非显式 `fail_mode=raise`

## 3. 动态命令树生成

由于命令不是预先写死，CLI 层需要在启动时构建命令树。

推荐流程：

1. 读取所有 mount
2. 解析每个 mount 的 `command.path` 或 `under + path_template`
3. 构建一棵 token tree
4. 在叶子节点挂 operation resolver
5. 生成帮助文本和补全候选

建议使用 Python `Click` 做命令树框架，因为：

- 动态子命令注册更自然
- 自定义参数解析更灵活
- 比只追求类型提示的框架更适合运行时生成命令

但要注意：

- 动态命令树只是人类 UX
- 稳定机器入口必须独立存在，不能依赖路径 token

## 3.1 动态 `--help` 生成

所有动态挂载命令都必须支持 `--help`。

推荐帮助生成流程：

1. 根据命令路径解析到 mount
2. 加载 mount 配置中的 help 覆盖
3. 加载 operation descriptor
4. 从 provider 获取 `HelpDescriptor`
5. 合并参数 schema、风险、surface、机器入口信息
6. 渲染为统一 help 输出

也建议支持：

```bash
cts invoke <mount-id> --help
```

这样同一条能力既有人类路径帮助，也有稳定机器入口帮助。

## 3.2 Help 输出建议结构

建议动态 `--help` 至少包含：

- 命令摘要
- 详细描述
- Usage
- 参数列表
- 默认值与必填信息
- 风险等级
- provider/source 来源
- `mount.id`
- `stable_name`
- 可见 surfaces
- 人类路径示例
- `cts invoke` 示例

### 3.2.1 帮助内容的动态来源

帮助内容应按以下来源合成：

- mount help 覆盖
- operation schema 描述
- provider 原生文档
- 运行时生成的上下文信息

同一个命令挂到不同 provider 时，`--help` 应自然不同。

例如：

- MCP tool 帮助里展示 tool 描述和 server 名
- OpenAPI 帮助里展示 method/path 和参数说明
- CLI 帮助里展示底层可执行文件、输出模式和 manifest 描述
- plugin hook 还可以在统一帮助编译完成后追加团队注释、治理提示或风险说明

## 3.3 稳定机器调用入口

建议把下面两条命令视为架构一等公民，而不是兜底命令：

```bash
cts invoke <mount-id> --input-json '{...}' --output json
cts explain <mount-id> --input-json '{...}'
```

原因：

- `mount.id` 可长期稳定
- AI 不需要解析帮助文本
- 自动化系统不受动态路径变更影响
- 更适合做 HTTP/MCP 北向桥接

## 4. 参数解析策略

统一 operation schema 后，运行时需要把 schema 映射为用户可输入的参数。

推荐规则：

### 4.1 required 字段 -> 必填 flags 或 positionals

如果 mount 明确指定路径语义，可以把少量核心字段做 positional，其余仍用 flags。

### 4.2 简单标量 -> flags

例如：

```bash
cts ops jira issue get --key ABC-123
```

### 4.3 复杂对象 -> 三种入口

- `--input-json`
- `--input-file`
- mount 级别扁平映射

### 4.4 原始透传

对某些 CLI/source，要支持：

```bash
cts invoke <mount-id> --raw-args '...'
```

但不建议作为主路径，只用于兜底。

## 4.5 Non-interactive / AI 模式

建议所有执行命令都支持：

- `--non-interactive`
- `--output json`
- `--no-color`
- 结构化错误输出

在 AI/自动化模式下：

- 不应弹交互式问题
- 需要确认时应返回明确的 policy error
- 帮助文本不应混入标准输出

注意：

- `--help` 是人类入口的重要能力
- AI/自动化系统不应依赖帮助文本解析，而应优先使用 schema、catalog 和 `invoke`

## 4.6 Hook 的变更边界

为了避免 hook 变成“任意篡改运行时”的逃生门，建议尽早约束：

- hook 可以改 `args`、`runtime`、`help payload`、`result payload`
- hook 不应改 `mount.id`、`stable_name`、`source name`
- hook 不应直接写日志文件，而应复用统一 logging API
- hook 不应绕过统一错误归一化
- 涉及写操作的 hook 后续应接入 policy / audit 治理

## 5. 输出处理

输出必须统一，不然平台层体验会很碎。

建议输出层至少支持：

- `table`
- `json`
- `yaml`
- `raw`
- `lines`

### 5.1 统一结果对象

Provider 只返回统一 `InvokeResult`，显示层再决定：

- 是否渲染表格
- 是否显示 stderr
- 是否截断大对象
- 是否显示 metadata

### 5.2 CLI 输出解析

CLI Provider 需要支持：

- 原样输出
- JSON 解析
- 正则提取
- 自定义 parser

如果某 CLI 支持 `--json`，应优先走结构化输出。

## 5.3 机器错误输出

机器模式建议统一输出：

```json
{
  "ok": false,
  "error": {
    "type": "ValidationError",
    "code": "missing_required_field",
    "message": "Field repo is required"
  }
}
```

## 6. Discovery 与缓存

为了避免每次启动都访问远端系统，建议引入 discovery cache。

### 6.1 缓存内容

- source 元信息
- operation descriptor
- schema hash
- 上次同步时间
- provider 版本

### 6.2 缓存位置

建议：

- `~/.cache/cts/discovery.db`
- 或 `~/.cache/cts/discovery/<source>.json`

### 6.3 同步命令

```bash
cts sync
cts sync github_mcp
cts inspect source github_mcp --refresh
```

### 6.4 缓存策略

建议每个 source 配置：

- `cache_ttl`
- `refresh_on_start`
- `manual_only`

## 6.5 Catalog 导出

运行时应支持导出完整能力目录，供 AI、IDE、自动化系统消费：

```bash
cts catalog export --format json
```

Catalog 至少应包含：

- mount 基本信息
- 稳定 id 与 stable name
- input/output schema
- 风险等级
- 可见 surface

Catalog 还建议包含一份结构化 help 摘要，供前端或文档生成器使用。

## 6.6 配置与导入日志

除了运行日志，还建议单独记录配置和导入阶段：

- 加载了哪些配置文件
- 哪些配置文件被覆盖
- 哪个 profile 生效
- 哪个 source 执行了 discover
- schema 是从 authoritative/probe/manual 哪种策略得到
- cache hit / miss
- 是否命中了人工覆盖

## 7. 策略与安全

安全模型建议尽早纳入设计，否则后面会很难补。

### 7.1 风险等级

所有 operation 都建议标记：

- `read`
- `write`
- `destructive`
- `privileged`

### 7.2 确认机制

对 `write`、`destructive`、`privileged` 建议支持：

- 交互确认
- `--yes` 跳过确认
- profile 级禁止执行

### 7.3 CLI allowlist

`cli` 和 `shell` provider 默认风险最高。

建议：

- 默认不允许任意二进制
- 只允许 allowlist 可执行文件
- 可按 profile 限制
- 可记录完整 argv 审计日志

### 7.4 路径限制

对 shell 和脚本 source，建议限制：

- 可执行根目录
- 工作目录
- 文件访问白名单

### 7.5 Secret 管理

不要把 token 写进 mount。

建议优先级：

1. 环境变量
2. 操作系统 keyring
3. 外部 secret manager
4. 配置文件中的引用键

### 7.6 北向暴露最小权限

当 `cts` 通过 MCP、HTTP、JSON-RPC 等方式对外暴露能力时，建议默认：

- 只暴露显式 allow 的 mount
- 默认不暴露 destructive / privileged 操作
- 默认不暴露 shell source
- 允许按 surface 做可见性控制

## 8. 审计与可观测性

长期要把 `cts` 当作执行平面，因此建议保留审计能力。

建议明确区分三类记录：

- `app log`
  研发调试和运行诊断
- `audit log`
  高价值执行留痕，偏安全/合规
- `run history`
  给前端和用户查看的近期执行历史

### 8.1 审计日志字段

- 时间
- run_id
- trace_id
- profile
- source
- mount id
- operation id
- argv 或 request 摘要
- 执行结果
- 耗时
- 调用人

### 8.1.1 配置与导入日志字段

建议额外记录：

- config file path
- config hash
- source version
- schema provenance
- cache status
- surface

### 8.2 调试模式

建议提供：

```bash
cts ... --debug
cts ... --trace
cts inspect mount <id> --render-request
```

这样在接 HTTP、CLI、MCP 时都能快速定位问题。

也建议支持：

```bash
cts logs tail
cts logs show --run-id <id>
cts logs config
```

对 AI/自动化系统还建议提供：

```bash
cts explain <mount-id> --input-json '{...}' --format json
```

## 9. 错误模型

不同 provider 的错误差异很大，运行时必须归一化。

建议分类：

- `ConfigError`
- `ResolutionError`
- `ValidationError`
- `PolicyError`
- `AuthError`
- `ProviderError`
- `ExecutionError`
- `TimeoutError`

CLI 层要把这些错误转换成稳定的用户输出和退出码。

推荐额外区分：

- `SurfaceError`
- `CatalogError`

## 9.1 日志脱敏

日志里必须默认脱敏：

- Authorization header
- token/api_key/password/secret
- provider 返回的敏感字段

并且：

- `app log` 允许记录更多调试信息，但仍要脱敏
- `audit log` 应尽量保留关键信息和摘要，不保留完整敏感 payload

## 10. 流式执行

MCP、GraphQL subscription、部分 CLI、长任务日志都可能需要流式输出。

建议运行时从第一天保留流式通道设计：

- `stream=True`
- provider 可逐块输出
- formatter 可逐块渲染

即使 MVP 暂时不完全实现，也要在接口上预留。

## 10.1 长任务与作业句柄

多种 API 尤其是云平台和内部运维系统常有异步任务。运行时建议为 `job` 类型 operation 预留统一句柄：

- `job_id`
- `status`
- `poll_url` 或 provider-specific handle
- `resume_token`

## 11. 并发与批处理

第二阶段可以考虑：

- `cts batch run`
- `cts parallel`
- 一次执行多个 mount

但第一阶段不必做得太重。只要数据模型允许将来加并发，就够了。

## 11.1 组合能力执行

当引入 workflow/composite operation 后，运行时还需要：

- 步骤级上下文
- 变量注入
- 中间结果选择
- 步骤失败策略

这层应该放在 execution 之上、provider 之下，避免把组合逻辑散落在各 provider 中。

## 12. 典型执行例子

### 12.1 MCP 调用

```bash
cts dev github issues list --repo owner/repo
```

运行时执行：

1. 命中 mount `github-list-issues`
2. 得到 source `github_mcp`
3. 读取 operation `list_issues`
4. 组装 `args = {"repo": "owner/repo"}`
5. 调用 `mcp-cli call-tool github:list_issues --args ...`
6. 返回统一结果并渲染

### 12.2 HTTP 调用

```bash
cts ops jira issue get --key ABC-123
```

运行时执行：

1. 命中 mount `jira-get-issue`
2. 把 `key` 填入 path 模板
3. 注入 auth header
4. 发起 GET 请求
5. 渲染 JSON 或 table

### 12.3 CLI 调用

```bash
cts dev gh repo list --owner my-org --limit 50
```

运行时执行：

1. 命中 mount `gh-repo-list`
2. 使用 manifest 生成 argv
3. 执行本地 `gh`
4. 如果支持 JSON，则解析后格式化

### 12.4 稳定机器调用

```bash
cts invoke github-list-issues --input-json '{"repo":"owner/repo"}' --output json
```

运行时执行：

1. 根据 `mount.id` 直接命中 mount
2. 生成统一 execution plan
3. 做策略检查
4. 调用 provider
5. 返回稳定 JSON 结果

## 13. 结论

运行时真正要保障的是：

- 命令解析稳定
- 参数校验统一
- 输出体验一致
- 风险可治理
- 问题可定位
- 配置、导入、执行全过程可追踪

只要这层稳定，后面加新 provider 的成本才会越来越低。
