# 配置模型与命令映射

## 1. 配置设计目标

配置层必须同时满足：

- 适合人手写
- 支持大规模 source 与 mount 管理
- 能表达多环境
- 能表达安全策略
- 能表达动态导入和命名规则
- 能覆盖 API、CLI、脚本和未来插件

推荐主配置格式为 YAML。

## 2. 配置文件层级

建议支持三层配置叠加：

### 2.1 全局配置

路径建议：

- `~/.config/cts/config.yaml`

适合存放：

- 通用 source
- 用户级 profile
- 全局认证与输出偏好

### 2.2 项目配置

路径建议：

- `<workspace>/.cts/config.yaml`

适合存放：

- 与仓库绑定的 source
- 项目命令挂载
- 团队共享 alias

### 2.3 临时覆盖

来源：

- 环境变量
- `--profile`
- `--set key=value`

### 2.4 分文件配置

单文件配置应继续支持，但长期推荐分文件。

推荐原则：

- 根配置文件负责版本、全局默认项和 `imports`
- source、mount、workflow、auth profile 拆到子文件
- 运行时仍然编译成一个统一配置模型

推荐目录：

```text
.cts/
  cts.yaml
  auth/
    github.yaml
    jira.yaml
  profiles/
    dev.yaml
    prod.yaml
  sources/
    mcp/
      bing.yaml
    http/
      jira.yaml
  mounts/
    bing.yaml
    jira.yaml
  workflows/
    triage.yaml
```

根文件示例：

```yaml
version: 1

imports:
  - ./auth/*.yaml
  - ./profiles/*.yaml
  - ./sources/**/*.yaml
  - ./mounts/**/*.yaml
  - ./workflows/**/*.yaml
```

建议合并语义：

- imported fragments 先加载
- 当前文件后覆盖
- `mounts`、`aliases` 追加合并
- 字典对象递归合并

建议约束：

- 一个 source 尽量放在一个文件里
- 一组强相关 mounts 放在一个文件里
- 不建议一开始就一个 mount 一个文件

## 3. 顶层模型

建议顶层结构如下：

```yaml
version: 1
app:
  name: cts
  default_profile: dev
  cache_dir: ~/.cache/cts
  state_dir: ~/.local/share/cts
  log_dir: ~/.local/state/cts/logs

imports: []
auth_profiles: {}
compatibility: {}
reliability: {}
drift: {}
profiles: {}
sources: {}
mounts: []
aliases: []
surfaces: {}
policies: {}
defaults: {}
```

新增的 `surfaces` 用来控制北向暴露，例如机器调用入口、MCP bridge、HTTP gateway。

同时建议把日志目录和日志策略当成一等配置，而不是硬编码。

## 3.1 Logging

建议顶层加入：

```yaml
logging:
  level: INFO
  format: jsonl
  sinks:
    app: ~/.local/state/cts/logs/app.jsonl
    audit: ~/.local/state/cts/logs/audit.jsonl
  redact:
    headers: [Authorization, X-API-Key]
    fields: [token, password, secret, api_key]
  retention:
    max_files: 10
    max_size_mb: 50
```

推荐字段：

- `level`
- `format`
- `sinks`
- `redact`
- `retention`
- `console`
- `trace_enabled`

## 3.2 Compatibility

建议显式治理配置、catalog、provider 与 northbound 合同的兼容边界：

```yaml
compatibility:
  min_cts_version: "0.1.0"
  catalog_version: 1
  error_contract_version: 1
  command_contract:
    mount_id_stable: true
    stable_name_stable: true
```

推荐字段：

- `imports`
- `min_cts_version`
- `catalog_version`
- `error_contract_version`
- `command_contract`
- `migrations`

## 3.3 Reliability

建议把超时、重试、限流、并发和幂等默认策略提升到顶层：

```yaml
reliability:
  defaults:
    timeout_seconds: 30
    retry:
      max_attempts: 2
      backoff: exponential
      base_delay_ms: 300
      jitter: full
    concurrency:
      max_inflight_per_source: 4
```

推荐字段：

- `defaults`
- `budgets`
- `retry_profiles`
- `timeout_profiles`
- `concurrency`

## 3.4 Drift

建议把 schema 漂移检测和对账策略也纳入顶层：

```yaml
drift:
  defaults:
    detect_on_sync: true
    classify_breaking_changes: true
    on_breaking_change: freeze_mount
    on_additive_change: auto_accept
```

推荐字段：

- `defaults`
- `fingerprints`
- `reconcile`
- `notifications`

## 3.5 Auth Profiles

建议把认证抽到单独顶层，而不是散落在每个 source 内。

```yaml
auth_profiles:
  jira-dev:
    type: bearer
    source: env
    token_env: JIRA_DEV_TOKEN

  github-oauth:
    type: oauth2
    grant_type: device_code
    session_store: keyring
```

推荐字段：

- `type`
- `source`
- `session_store`
- `refresh`
- `bootstrap`
- `scopes`
- `keyring_service`

## 4. Profiles

`profile` 用来表达环境和默认上下文。

```yaml
profiles:
  dev:
    env:
      region: ap-southeast-1
      team: core
    output:
      format: table
    auth_defaults:
      jira: jira-dev
      github: github-oauth

  prod:
    env:
      region: us-east-1
    output:
      format: json
    policy_overrides:
      require_confirm_for_write: true
```

建议 profile 支持：

- 默认环境变量
- 默认参数
- 默认认证引用
- 认证 profile 默认映射
- 输出格式
- 风险策略覆盖
- AI/机器模式默认输出
- 是否允许 northbound 暴露
- 日志级别覆盖
- profile 级脱敏策略覆盖

建议约束：

- profile 里尽量不要直接放 secret
- 共享项目配置里尽量只放 `auth_ref`，不放明文 token

## 4.1 Surfaces

`surface` 控制统一能力如何再次被暴露给人类或程序。

```yaml
surfaces:
  cli:
    enabled: true

  invoke:
    enabled: true
    default_output: json
    non_interactive_by_default: true

  mcp:
    enabled: false
    include_mounts: ["github-*", "jira-*"]

  http:
    enabled: false
    bind: 127.0.0.1:7788
```

推荐先内置：

- `cli`
- `invoke`
- `mcp`
- `http`
- `jsonrpc`

## 4.2 Plugins

`plugins` 用来扩展 `cts` 内核，而不是挂载业务能力本身。

第一阶段至少应支持两类扩展：

- 注册新的 provider type
- 注册可绑定到核心生命周期事件的 hook handler

```yaml
plugins:
  internal_api_ext:
    module: company_cts_plugins.internal_api
    config:
      endpoint: https://mesh.example.com

  local_demo_ext:
    path: ./plugins/local_demo.py
    factory: build_plugin
    config:
      suffix: "!"
```

建议字段：

- `enabled`
- `module`
- `path`
- `factory`
- `config`

当前实现补充：

- plugin 可以只提供 hook handler，也可以同时提供 provider
- 如果多个 plugin 注册同名 `provider_type`，当前实现会保留第一个成功注册者，后续重复注册会被跳过并进入治理视图
- 重复 provider 注册不会阻断 hook 多实例场景

说明：

- `module` 适合通过 Python package 分发的插件
- `path` 适合项目内局部插件或 PoC
- `factory` 用于指定插件构造入口
- plugin 注册出来的 provider type，可以直接被 `sources.*.type` 使用

## 4.3 Hooks

`hooks` 用来把 plugin 中声明的 handler 绑定到核心生命周期事件。

```yaml
hooks:
  - event: help.after
    plugin: local_demo_ext
    handler: append_help_note

  - event: explain.before
    plugin: local_demo_ext
    handler: normalize_args
    priority: 10
    when:
      mount_id: github.issue.list

  - event: invoke.after
    plugin: internal_api_ext
    handler: redact_result
    fail_mode: warn
```

建议字段：

- `event`
- `plugin`
- `handler`
- `enabled`
- `priority`
- `fail_mode`
- `when`
- `config`

建议 `fail_mode`：

- `warn`
- `raise`
- `ignore`

建议 `when`：

- 支持按 `mount_id`、`source`、`source_name`、`provider_type`、`operation_id`、`surface`、`mode` 等上下文字段过滤
- 支持标量相等、数组任一匹配、glob、以及 `exists/eq/glob/in/not` 这类操作符

当前实现补充：

- hook 按 `priority` 升序执行，相同优先级保持配置文件中的原始顺序
- `when.source` 与 `when.source_name` 在当前运行时里会做统一别名处理
- `fail_mode=raise` 会归一化成稳定的 `HookError`

## 5. Sources

## 5.1 Source 通用字段

每个 source 至少包含：

```yaml
sources:
  source_name:
    type: mcp | http | openapi | graphql | grpc | cli | shell | plugin
    enabled: true
    profile_scope: [dev, prod]
    description: ...
    tags: [team-a, internal]
    auth_ref: github-oauth
    auth_session: shared
    compatibility: {}
    reliability: {}
    drift_policy: {}
```

建议通用字段：

- `type`
- `enabled`
- `description`
- `tags`
- `owner`
- `profile_scope`
- `timeouts`
- `retry`
- `auth_ref`
- `auth_session`
- `discovery`
- `policy_ref`
- `compatibility`
- `reliability`
- `drift_policy`
- `expose_to_surfaces`

说明：

- `type` 是高层分类
- `plugin` 可以承载 WebSocket、SSE、SQL、消息总线、内部 RPC 等其他协议
- `type` 不只可以是内置枚举，也可以是 plugin 注册出来的自定义 provider type
- `auth_session` 用来声明这个 source 是否与其他 source 共享登录态或会话缓存
- `expose_to_surfaces` 控制该 source 下的能力默认能暴露到哪些北向接口

## 5.2 MCP Source

```yaml
sources:
  github_mcp:
    type: mcp
    adapter: mcp_cli
    config_file: ~/.config/claude_desktop_config.json
    server: github
    auth_ref: github-oauth
    pass_env: true
    discovery:
      mode: live
      cache_ttl: 3600
    drift_policy:
      on_breaking_change: require_manual_review
```

说明：

- `adapter` 指明通过 `mcp-cli` 接入
- `config_file` 与 `server` 用于定位具体 MCP server
- `discovery.mode` 可选 `live`、`cache_only`、`manual`

## 5.3 HTTP Source

```yaml
sources:
  jira_http:
    type: http
    base_url: https://jira.example.com/rest/api/3
    auth_ref: jira-dev
    headers:
      Accept: application/json
    reliability:
      timeout_seconds: 15
      retry:
        max_attempts: 2
      rate_limit:
        budget_key: jira-default
        requests_per_minute: 120
```

## 5.4 OpenAPI Source

```yaml
sources:
  stripe_api:
    type: openapi
    spec:
      url: https://api.stripe.com/openapi/spec3.json
      # 也可使用本地文件
      # path: ./specs/stripe-openapi.yaml
    auth_ref: stripe-prod
    discovery:
      mode: import
      cache_ttl: 86400
```

## 5.5 GraphQL Source

```yaml
sources:
  github_graphql:
    type: graphql
    endpoint: https://api.github.com/graphql
    schema:
      introspection: live
      # 也可使用静态 introspection JSON
      # path: ./schemas/github-introspection.json
    auth_ref: github-oauth
```

## 5.6 CLI Source

CLI source 是长期重点。

```yaml
sources:
  gh_cli:
    type: cli
    executable: gh
    working_dir: .
    discovery:
      mode: manifest
      manifest: ~/.config/cts/manifests/gh.yaml
    compatibility:
      min_binary_version: "2.45.0"
      break_on_major_upgrade: true
    env:
      GH_PAGER: cat
    output:
      preferred_format: json
```

CLI source 必须支持三种接入级别：

### A. 手工 manifest

最稳，推荐默认模式。由使用者显式描述 CLI 的命令、参数、输出。

### B. 半自动导入

通过 `--help`、`completion`、man page 或厂商 schema 半自动生成 manifest，再由人校正。

### C. 自定义 adapter

给某个复杂 CLI 写专用 provider 或 plugin，返回统一 operation 描述。

## 5.7 Shell Source

```yaml
sources:
  ops_scripts:
    type: shell
    root: ./scripts
    discovery:
      mode: manifest
      manifest: ./.cts/scripts.yaml
```

## 5.8 Plugin Source

```yaml
sources:
  internal_mesh:
    type: plugin
    plugin: cts-provider-internal-mesh
    config:
      endpoint: https://mesh.example.com
```

这里的 `type: plugin` 代表“通过通用 plugin bridge 接入一个能力源”。

如果是 plugin 给 `cts` 注册了一个新 provider type，则更推荐直接写成：

```yaml
plugins:
  internal_api_ext:
    module: company_cts_plugins.internal_api

sources:
  internal_mesh:
    type: internal_mesh_api
    endpoint: https://mesh.example.com
```

也就是说：

- `type: plugin` 是一种 southbound source 形态
- plugin 注册 provider type 是一种内核扩展机制

## 6. Mounts

Mount 是整个平台最关键的配置对象。

一个 mount 描述：

- 从哪个 source 来
- 对应哪个 operation
- 在命令树上挂到哪里
- 参数如何暴露
- 帮助信息如何生成
- 是否重命名
- 是否对不同 profile 有不同策略

### 6.1 单个 operation 挂载

```yaml
mounts:
  - id: github-list-issues
    source: github_mcp
    operation: list_issues
    command:
      path: [dev, github, issues, list]
      aliases:
        - [gh, issues, list]
    machine:
      stable_name: github.issue.list
      expose_via: [cli, invoke, mcp]
    help:
      summary: 列出仓库 issues
      description: 查询指定仓库的 issue 列表。
      examples:
        - "cts dev github issues list --repo owner/repo"
      param_overrides:
        repo:
          help: GitHub 仓库，格式 owner/repo
    exposure:
      help: 列出仓库 issues
      hidden: false
```

### 6.2 批量挂载全部 operation

```yaml
mounts:
  - id: github-all
    source: github_mcp
    select:
      include: ["*"]
      exclude: ["delete_*", "admin_*"]
    command:
      under: [mcp, github]
      naming:
        strategy: kebab
        group_by: tags
        fallback_group: misc
```

### 6.3 按标签挂载

```yaml
mounts:
  - id: jira-readonly
    source: jira_http
    select:
      tags: [issue, read]
    command:
      under: [ops, jira]
```

### 6.4 组合型挂载

长期建议支持复合能力。组合型挂载不直接映射一个外部 operation，而是把多个 operation 串成一个新的高层 operation。

```yaml
mounts:
  - id: triage-sync
    type: composite
    command:
      path: [ops, triage, sync]
    machine:
      stable_name: triage.sync
      expose_via: [cli, invoke, mcp]
    workflow:
      steps:
        - use:
            source: github_mcp
            operation: list_issues
        - use:
            source: jira_http
            operation: create_issue
```

第一阶段不一定实现组合型挂载，但模型上建议预留。

### 6.5 帮助信息模型

动态挂载命令的 `--help` 不应是静态文本，而应来自 mount + operation + provider 的合成结果。

建议 mount 支持：

```yaml
mounts:
  - id: github-list-issues
    help:
      summary: 列出仓库 issues
      description: 查询指定仓库的 issue 列表。
      examples:
        - "cts dev github issues list --repo owner/repo"
        - "cts manage invoke github-list-issues --input-json '{\"repo\":\"owner/repo\"}'"
      notes:
        - "需要 GitHub MCP server 已配置"
      param_overrides:
        repo:
          help: GitHub 仓库，格式 owner/repo
        limit:
          help: 返回条数
```

推荐字段：

- `summary`
- `description`
- `examples`
- `notes`
- `param_overrides`
- `hide_sections`

帮助信息优先级建议为：

1. mount `help` 显式覆盖
2. operation descriptor 中的 description / examples / schema descriptions
3. provider 原生文档，例如 MCP tool 描述、OpenAPI summary、CLI manifest help
4. 运行时补充的风险、surface、机器入口、默认值

### 6.6 Reliability 与幂等

mount 不只要表达“能不能调”，还要表达“失败时如何处理、重复执行是否安全”。

```yaml
mounts:
  - id: stripe-customer-create
    source: stripe_api
    operation: create_customer
    reliability:
      timeout_seconds: 20
      retry:
        max_attempts: 1
        retry_on: [timeout, rate_limit]
      idempotency:
        required: true
        strategy: hash_args
        header_name: Idempotency-Key
        ttl_seconds: 3600
```

推荐字段：

- `timeout_seconds`
- `retry`
- `rate_limit`
- `idempotency`
- `concurrency`
- `degraded_ok`

### 6.7 Drift Policy

mount 最终直接承接 northbound 稳定合同，因此也应该能表达“上游变了以后怎么对账”。

```yaml
mounts:
  - id: gh-repo-list
    source: gh_cli
    operation: repo_list
    drift_policy:
      pin_operation_fingerprint: "sha256:abcd..."
      accept_additive_changes: true
      on_breaking_change: disable_mount
```

推荐字段：

- `pin_operation_fingerprint`
- `accept_additive_changes`
- `on_missing_operation`
- `on_breaking_change`
- `notify`

## 7. Command 路径规则

建议一条命令路径由多个 token 组成，例如：

```yaml
command:
  path: [dev, github, issues, list]
```

这样做的好处：

- 容易做命名空间
- 容易做权限隔离
- 容易做批量导入
- 容易做补全

建议支持：

- `path` 直接指定固定路径
- `under` 指定前缀路径
- `path_template` 通过 operation 元数据生成路径
- `machine_name_template` 生成稳定机器名称

例如：

```yaml
command:
  under: [cloud]
  path_template: ["{provider}", "{resource}", "{action}"]
```

机器名称示例：

```yaml
machine:
  stable_name: github.issue.list
```

## 8. 参数映射

Operation 的输入 schema 最终要映射成 CLI 参数。

推荐支持以下规则：

### 8.1 标量参数

```yaml
params:
  repo:
    flag: --repo
    required: true
  limit:
    flag: --limit
    type: int
```

### 8.2 布尔参数

```yaml
params:
  archived:
    flag: --archived
    type: bool
```

### 8.3 列表参数

```yaml
params:
  labels:
    flag: --label
    repeated: true
```

### 8.4 对象参数

对象参数必须支持三种输入方式：

- 扁平化 flags
- `--json` 整体传入
- 从文件读入

示例：

```bash
cts dev github issues create --title bug --body "detail"
cts dev github issues create --input-json '{"title":"bug","body":"detail"}'
cts dev github issues create --input-file payload.json
```

所有参数映射最终都应可进入 `--help` 输出，至少展示：

- 参数名
- 类型
- 是否必填
- 默认值
- 参数描述
- 示例

## 9. 参数转换与模板

不同后端常常要求不同字段名和结构，因此 mount 层需要支持轻量转换。

```yaml
mounts:
  - id: jira-create
    source: jira_http
    operation: create_issue
    transform:
      request:
        projectKey: ${args.project}
        summary: ${args.title}
        description: ${args.body}
```

长期建议支持：

- 变量替换
- JMESPath 表达式
- 简单模板
- 默认值
- profile 注入

## 10. Alias

Alias 用于给命令做短路径或兼容旧路径。

```yaml
aliases:
  - from: [jira, issue, get]
    to: [ops, jira, issue, get]
```

注意：

- alias 只服务人类 UX
- 不建议把 alias 当成 AI 或自动化系统的稳定引用

## 11. Policies

策略建议从配置第一天就进入模型。

```yaml
policies:
  require_confirm_for_write: true
  deny_sources_in_prod:
    - shell
  allowed_cli_bins:
    - gh
    - kubectl
    - terraform
```

也支持 mount 级别策略：

```yaml
mounts:
  - id: terraform-apply
    source: terraform_cli
    operation: apply
    policy:
      confirm: true
      allowed_profiles: [dev, staging]
```

同时建议支持 surface 级别策略：

```yaml
mounts:
  - id: terraform-apply
    machine:
      expose_via: [cli, invoke]
    policy:
      deny_surfaces: [mcp, http]
```

这可以避免高风险命令被自动暴露给 AI 或远程程序。

## 11.1 AI 与机器友好字段

建议 mount 支持机器可读元数据：

```yaml
mounts:
  - id: github-list-issues
    machine:
      stable_name: github.issue.list
      examples:
        - input:
            repo: owner/repo
      annotations:
        safe_for_agent: true
        side_effect_free: true
```

推荐字段：

- `stable_name`
- `examples`
- `annotations`
- `expose_via`
- `default_output`
- `supports_dry_run`

## 12. 推荐的配置约束

### 12.1 Source 名字稳定

一旦对外使用，尽量不要频繁改 source 名，否则 mount 和 profile 引用都会受影响。

### 12.2 Mount id 永久稳定

即使命令路径变化，`mount.id` 最好保持不变，用于缓存、审计和迁移。

对 AI/自动化系统来说，`mount.id` 应当被视作稳定合同。

### 12.3 所有 write 操作显式标记

必须能让系统识别：

- read
- write
- destructive
- privileged

### 12.4 CLI source 默认 deny-all

任意 CLI 风险最高，推荐默认必须通过 allowlist 或 manifest 才能执行。

### 12.5 人类路径可变，机器合同稳定

建议把以下对象区分开：

- `command.path` 是人类 UX，可重构
- `mount.id` 是稳定 id，不轻易修改
- `machine.stable_name` 是程序友好名称，适合 AI 或外部系统引用

### 12.6 Secret 不进共享配置

建议：

- 项目配置里只存 `auth_ref`
- 真正凭证通过 env、keyring、session store 注入
- 日志和前端接口默认只暴露脱敏状态

### 12.7 写操作显式声明 Reliability 与 Drift 策略

尤其是 `write`、`destructive`、`privileged` 操作，建议显式配置：

- `reliability.idempotency`
- `reliability.retry`
- `drift_policy`
