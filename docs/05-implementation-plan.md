# 实施路线图与工程拆分

## 1. 推荐技术栈

如果以长期可扩展为目标，建议：

- 语言：Python 3.11+
- CLI 框架：Click
- 配置模型：Pydantic
- HTTP 客户端：httpx
- 输出渲染：rich
- YAML：PyYAML 或 ruamel.yaml
- JSON Schema 校验：jsonschema
- 缓存与状态：SQLite + 本地文件

原因：

- Python 适合做编排平台和多协议适配层
- Click 更适合动态命令树
- Pydantic 适合做复杂配置和统一模型

## 2. 推荐仓库结构

```text
cts/
  pyproject.toml
  frontend/
  src/cts/
    __init__.py
    main.py
    app.py
    cli/
      root.py
      builtins/
        config.py
        source.py
        mount.py
        inspect.py
        invoke.py
        explain.py
        catalog.py
        serve.py
        auth.py
        sync.py
        doctor.py
      help.py
    config/
      loader.py
      merger.py
      models.py
      compatibility.py
      migration.py
      origins.py
    registry/
      sources.py
      mounts.py
      aliases.py
      policies.py
    discovery/
      service.py
      cache.py
      normalize.py
      catalog.py
      schema_import.py
      drift.py
    composition/
      compiler.py
      workflow.py
    execution/
      router.py
      resolver.py
      validator.py
      runner.py
      hooks.py
      planner.py
      help_compiler.py
      reliability.py
      formatter.py
      errors.py
      audit.py
      logging.py
    providers/
      base.py
      mcp_cli.py
      http.py
      openapi.py
      graphql.py
      cli.py
      shell.py
      plugin.py
    plugins/
      loader.py
      protocol.py
      hooks.py
    surfaces/
      mcp.py
      http.py
      jsonrpc.py
      ui.py
    auth/
      resolver.py
      keyring.py
      oauth.py
      sessions.py
    utils/
      jsonschema.py
      templates.py
      subprocess.py
      redact.py
  docs/
```

## 3. 模块职责

### 3.1 `config`

负责：

- 读全局配置
- 读项目配置
- 合并 profile
- 展开环境变量
- 校验配置结构
- 处理版本迁移
- 做兼容性检查
- 处理 imports / glob / 递归导入
- 记录 source / mount / profile 的来源文件

### 3.2 `registry`

负责：

- 查询 source
- 查询 mount
- 处理 alias
- 冲突检测

### 3.3 `discovery`

负责：

- 调 provider discover
- 归一化 operation
- 获取与缓存 schema provenance
- 更新缓存
- 做 schema drift 检测与对账

### 3.4 `execution`

负责：

- 命令解析
- operation 解析
- 参数验证
- provider 调度
- hook 调度
- 输出格式化
- 审计
- 运行日志与 run history
- 超时、重试、限流和幂等治理

### 3.5 `providers`

负责：

- 与真实世界系统交互

### 3.5.1 plugin provider extension

负责：

- 让第三方插件注册新的 provider type
- 让 source 直接使用 plugin 注册的 `type`
- 保持 provider 接口、help/schema/explain/invoke 与内置 provider 对等

### 3.6 `composition`

负责：

- workflow/composite operation 编译
- 步骤依赖与变量传递
- 组合能力注册

### 3.7 `surfaces`

负责：

- `invoke` 稳定机器入口
- MCP bridge
- HTTP / JSON-RPC gateway
- Web 控制台入口
- 北向暴露策略

### 3.8 `auth`

负责：

- auth profile 解析
- session 存储与读取
- OAuth / device flow
- token refresh
- 统一鉴权状态输出

## 4. 分阶段路线图

## Phase 0：核心设计与文档

目标：

- 固化统一模型
- 定义配置文件
- 定义 Provider 接口

当前这组文档就属于这一阶段。

## Phase 1：最小可运行 MVP

范围建议严格控制在：

- 配置加载
- source 注册
- mount 注册
- 稳定机器调用入口
- 动态命令树
- HTTP provider
- CLI provider
- MCP provider 基于 `mcp-cli`
- `cts inspect`
- `cts sync`
- `cts doctor`

此阶段重点不是支持很多协议，而是打通端到端闭环。

### Phase 1 最小命令集

- `cts config build|paths`
- `cts source add|list|show|test`
- `cts mount add|list|show`
- `cts invoke <mount-id>`
- `cts explain <mount-id>`
- `cts catalog export`
- `cts sync [source]`
- `cts inspect mount|source|operation`
- 动态 mount 命令执行
- 动态 mount `--help`

### Phase 1 必须支持的 source 类型

- `mcp`
- `http`
- `cli`

原因：

- 覆盖你当前最关心的 MCP
- HTTP 是最通用能力源
- CLI 是差异化能力

### Phase 1 必须达成的 AI/自动化能力

- 稳定 `mount.id` 调用入口
- 统一 JSON 输入输出
- 结构化错误模型
- `explain` / `dry-run`
- catalog 导出
- 结构化日志与 run_id

### Phase 1 必须达成的运维可观测性能力

- 配置加载日志
- discovery/schema import 日志
- 执行日志
- audit log
- 敏感字段脱敏
- 稳定 exit code 与错误合同
- 分文件配置加载与来源追踪

### Phase 1 必须达成的人类可用性能力

- 动态命令完整支持 `--help`
- 参数级帮助与示例
- 按 provider/tool 动态生成帮助内容

## Phase 2：规模化导入

增加：

- OpenAPI provider
- GraphQL provider
- plugin / hook foundation
- mount 批量导入
- CLI manifest 生成器
- alias 与迁移工具
- config migration assistant
- compatibility checker
- auth session 管理与基础 refresh 流程
- schema drift 检测
- reliability policy 编排
- MCP bridge
- HTTP / JSON-RPC serve 模式
- 组合型 workflow mount
- Web 控制台

## Phase 3：治理与生态

增加：

- 外部 plugin 协议
- hook ordering / filtering / condition / async model
- keyring 与登录流程
- OAuth / device flow
- schema drift reconciliation workflow
- provider / binary version gate
- 更完整的 policy engine
- 审计日志
- shell completion
- docs generator
- provider SDK versioning
- 统一 rate limit / budget center
- capability registry UI

## Phase 4：高级能力

增加：

- 流式输出
- 批处理
- 并发运行
- TUI 浏览器
- 远程 registry
- job / async operation 管理

## 5. MVP 功能切分建议

为了降低风险，建议按下面顺序开发。

### Step 1：统一模型

先写：

- `SourceConfig`
- `MountConfig`
- `OperationDescriptor`
- `CapabilityCard`
- `ExecutionPlan`
- `SchemaProvenance`
- `InvokeRequest`
- `InvokeResult`

### Step 2：配置加载与 registry

先能做到：

- 读取配置
- 列出 source
- 列出 mount
- 做冲突检测
- 导出 catalog

### Step 2.5：Schema 导入与缓存

补 `schema_import`，负责：

- 按 provider 获取参数格式
- 记录 provenance 和 confidence
- 写入 discovery cache
- 记录 schema import 日志

### Step 3：HTTP provider

它最容易打通闭环，先用它验证：

- 参数映射
- 输出格式化
- profile 注入
- explain / render-request
- help 描述来源

### Step 4：CLI provider

接着验证“任意 CLI 也是一等公民”。

建议先只做 manifest 驱动，不做复杂自动发现。

同时确保 CLI manifest 中的参数说明和示例能进入动态 `--help`。

### Step 5：MCP provider

接 `mcp-cli`，先用 subprocess 方式跑通 invoke，再补 discovery。

同时预留 schema probe 能力，用于按策略获取更完整的 MCP 参数格式。

### Step 6：稳定机器入口

先把 `cts invoke <mount-id>` 和 `cts explain <mount-id>` 做稳定，这对 AI 和自动化系统比动态路径更重要。

### Step 7：动态命令树

最后把 mount 真正挂成 `cts a b c`，而不是只通过稳定入口调用。

### Step 8：帮助编译器

补 `help_compiler`，把：

- mount help 覆盖
- provider help 片段
- schema 参数说明
- 风险与机器入口信息

编译成最终的 `--help` 输出。

### Step 9：日志与审计

补：

- `execution/logging.py`
- `execution/audit.py`
- `utils/redact.py`

并统一：

- run_id / trace_id
- config/discovery/invoke 事件
- app log / audit log / run history

### Step 10：auth / reliability / migration 治理层

补：

- `auth/sessions.py`
- `auth/oauth.py`
- `execution/reliability.py`
- `config/migration.py`
- `discovery/drift.py`

目标：

- 统一 auth profile 与 refresh 流程
- 统一 timeout / retry / rate limit / idempotency
- 支持 config migration 与 compatibility check
- 支持 schema drift detection 与 reconcile 决策

## 6. CLI Provider 的实施建议

这是最容易失控的一块，建议分三期。

### 第一期

- 只支持 manifest 驱动
- 只支持结构化参数
- 只允许 allowlist 二进制
- 只支持 `json` 和 `raw` 输出

### 第二期

- 支持 `--help` 半自动导入
- 支持 completion 导入
- 支持 response parser

### 第三期

- 支持 CLI 专用 adapter
- 支持复杂命令族自动 discovery

## 7. MCP Provider 的实施建议

### 第一期

- 通过 `mcp-cli call-tool` 执行 tools
- 支持基于配置文件的 server 选择
- 手工 mount 单个 tool
- 支持 `explain`

### 第二期

- 补 `sync` 能力
- 自动导入所有 tools
- 处理 prompt/resource

### 第三期

- 评估是否增加原生 MCP SDK provider

## 8. 测试策略

建议从一开始就分三层测试。

### 8.1 单元测试

- 配置模型
- 参数映射
- 路由解析
- 命名冲突
- help 编译结果
- 日志脱敏
- run_id 传播
- 配置迁移与兼容检查
- reliability 策略决策
- drift 分类

### 8.2 Provider 测试

- HTTP mock
- CLI 假命令
- `mcp-cli` subprocess mock
- auth refresh / expiry mock

### 8.3 集成测试

- 从 `cts` 命令输入到结果输出的完整链路
- `invoke` / `explain` 的机器合同
- `catalog export` 的结构稳定性
- 动态挂载命令 `--help` 输出
- 配置加载与执行日志
- drift detection 与 mount freeze
- auth/login/refresh 状态流转

## 9. 风险与应对

### 风险 1：动态命令树复杂

应对：

- 先支持 `cts invoke <mount-id>`
- 命令树成熟后再暴露完整动态路径

### 风险 2：CLI 自动发现不可靠

应对：

- 明确以 manifest 为主
- 自动发现只作为辅助工具

### 风险 3：MCP discovery 依赖外部工具能力

应对：

- 先支持手工 mount
- 再做 cache 与 sync

### 风险 4：参数模型过于复杂

应对：

- 第一期只支持常见 JSON Schema 子集
- 复杂对象统一走 `--input-json`
- 保存 provenance，允许后续人工覆盖

### 风险 5：AI 友好只停留在 JSON 输出

应对：

- 从第一期就把 `invoke`、`explain`、`catalog export` 视作一等能力
- 区分人类路径和机器合同
- 提前设计 northbound surface，而不是后补

### 风险 6：动态命令能执行但不会自解释

应对：

- 把动态 `--help` 视为第一期核心能力
- 设计统一 help 编译器，而不是 scattered string 拼接
- 给不同 provider 明确帮助来源

### 风险 7：上游 schema 漂移导致 mount 静默失效

应对：

- 记录 fingerprint
- 在 `sync` 中做 drift check
- 对 breaking change 支持 freeze / warning / manual review

### 风险 8：认证散落在 provider 内部，无法统一刷新和前端展示

应对：

- 抽出 auth profile 与 session 层
- provider 只消费统一凭证对象
- 把 login / refresh / logout 设计成统一命令与 API

### 风险 9：重试策略不统一，导致写操作重复执行

应对：

- 把 timeout / retry / idempotency 提升到 execution 层
- 对 write / destructive 操作采用保守默认值
- 允许 mount 手工声明幂等策略

## 10. 最终建议

第一版不要试图“一次接入所有协议”，而要做一个稳定的骨架：

- 核心模型稳
- Provider 接口稳
- Mount 模型稳
- 动态命令树可扩展

只要这四件事稳，后面的 OpenAPI、GraphQL、内部网关、任意 CLI 都只是增量工作，而不是重构。
