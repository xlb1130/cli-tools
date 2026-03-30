# 当前实现状态与分阶段开发计划

- Status: Working Draft
- Snapshot Date: 2026-03-30
- Scope: 对照当前仓库代码与现有 RFC/专题文档，给出“已完成 / 未完成 / 下一阶段”的实际落地视图

## 1. 这份文档解决什么问题

前面的 RFC 和专题文档定义了 `cts` 的长期目标，但当前仓库已经不再是纯设计稿，而是一个可运行的 Python MVP。

因此需要一份单独文档回答三个更现实的问题：

- 现在到底已经做到了什么
- 哪些能力在文档里已经承诺，但代码还没落地
- 接下来应该按什么阶段推进，才能既不推翻当前骨架，又能持续扩展到更多 API / CLI / MCP / 未来 plugin

这份文档以“当前代码”为准，不以理想目标替代现状。

## 2. 当前已经完成的基础能力

截至 2026-03-30，当前仓库已经具备以下可运行能力。

### 2.1 配置与编译链路

- 支持单文件配置与分文件配置
- 支持 `imports`
- 支持相对路径、绝对路径、glob、目录导入、递归导入
- 支持导入环检测
- 支持顶层 `mounts`、`aliases` 的追加合并
- 支持字典深度合并
- 支持 `source`、`mount`、`profile`、`auth_profile`、`plugin`、`hook` 的来源文件标注
- 支持 `cts manage config paths`
- 支持 `cts manage config build`
- 已支持 `plugins` / `hooks` 顶层配置模型

### 2.2 统一运行时

- 已形成 `source -> operation -> mount -> dynamic command` 的基本编译链
- 支持 `mount.id` 稳定入口
- 支持 `cts manage source add`
- 支持 `cts manage source show|test|remove`
- 支持 `cts manage mount add`
- 支持 `cts manage mount show|remove|import`
- 支持 `cts manage alias list|add|remove`
- 支持 `cts manage invoke <mount-id>`
- 支持 `cts manage explain <mount-id>`
- 支持 `cts manage inspect mount|source|operation`
- 支持 `cts manage inspect drift`
- 支持 `cts manage catalog export`
- 支持 `cts manage sync`
- 支持 `cts manage reconcile drift`
- 支持 `cts manage doctor`
- 支持 `cts manage docs`
- 支持 `cts manage workflow list|execute`
- 支持动态命令生成
- 支持动态命令 `--help`
- 支持 `cts manage completion script --shell <bash|zsh|fish>`
- 支持基于 JSON Schema 子集的参数校验
- 支持基础结构化错误输出
- 已支持 source discovery snapshot 持久化
- 已支持 discovery 失败时使用 memory/cache fallback 继续编译
- 已支持统一 schema provenance 缓存，并在 `help` / `inspect` / `sync` 之间复用
- 已支持 `cts manage sync` 写入 import report 与 capability snapshot
- 已支持独立 `secret` 基础层与统一 secret manager
- 已支持 `env` / `file` / `literal` secret provider
- 已支持 `cts manage secret list|show`
- 已支持 auth session store 与 `cts manage auth list|status|login|refresh|logout|validate`
- 已支持 HTTP `/api/secrets` / `/api/secrets/{name}`

### 2.3 Plugin / Hook 扩展基础

- 已支持 Python in-process plugin 加载
- 支持 `module` / `path` 两种插件定位方式
- plugin 可注册新的 provider type
- source 可直接使用 plugin 注册的 `type`
- `cts manage source add` 已可识别当前配置中 plugin 注册的 provider type
- 已支持配置驱动的 hook 绑定
- 当前 hook 已接入：
  - `discovery.before|after|error`
  - `help.before|after`
  - `explain.before|after|error`
  - `invoke.before|after|error`
  - `surface.http.request.before|after|error`
- 已支持 hook `priority`
- 已支持 hook `when` 条件过滤
- 已支持 `fail_mode=raise|warn|ignore`
- 已支持稳定 `HookError`
- 已支持 plugin provider 重复注册跳过与冲突记录
- 已有回归测试覆盖 plugin provider 注册与 hook 改写 `help` / `explain` / `invoke`

### 2.4 已有 southbound provider

- `cli`
- `shell`
- `http`
- `openapi`
- `graphql`
- `mcp`
- plugin 注册 provider

但其中只有一部分已经达到“真实可扩展接入”的程度，详见后文缺口分析。

### 2.5 MCP 现状

- 已支持 MCP source 编译
- 已支持通过 `mcp-cli` 或本地 Node bridge 执行
- 已支持 live discovery
- 已验证远程 `streamable_http` MCP server 的真实 discovery 与 tool invoke
- 已能把发现到的 MCP tools 动态挂载为 `cts` 命令

### 2.6 测试与示例

- 已有 demo CLI 示例
- 已有 split-config 示例
- 已有 MCP 示例
- 已有 OpenAPI importer 回归测试
- 已有 GraphQL importer 回归测试
- 已有 CLI `source import-help` / manifest 生成器回归测试
- 已有 CLI `source import-completion` 回归测试
- 已有 discovery cache / sync report / capability snapshot 回归测试
- 当前基础测试通过，覆盖 demo、split config、MCP provider 主路径、plugin provider / hook 主路径、hook priority/filter/fail_mode、discovery cache fallback、sync 落盘主路径、OpenAPI 导入与 dry-run 请求构建主路径、GraphQL 导入与 introspection 主路径、CLI help 导入与 manifest 执行主路径、CLI completion 导入与 manifest 执行主路径
- 已覆盖 auth/session/secret 主路径，包括 `auth_profile.source=secret`、northbound secret inventory 与 dry-run 脱敏

## 3. 文档中已经提出，但当前还没完成的能力

下面按专题能力域归类，而不是按文件名简单罗列。

### 3.1 CLI 产品面还没收口的部分

当前 CLI 已可运行，但离文档里定义的 MVP 命令集还有缺口：

- `inspect` 已能展示 origin file，但 profile 解析结果、surface 暴露决策还不完整
- `source remove` / `mount remove` / `mount import` 已实现，但批量治理与更强的冲突提示仍然偏薄
- `alias` 目前只有基础 `list|add|remove`，还没有冲突清理、批量迁移、兼容期治理命令
- shell completion 已支持 script 导出，但还没有 install/bootstrap 命令

结论：

- 当前 CLI 适合做核心验证
- 已经具备基础“可管理平台”形态，但治理面仍未收口

### 3.2 Discovery / 导入 / Schema 获取仍然偏薄

虽然 discovery 基础设施已经明显前进，但“规模化导入与上游治理”仍未真正完成：

- 已有按 source 落盘的 discovery cache、schema provenance、operation fingerprint
- 已有 `sync` import report 与 capability snapshot
- 已有 live discovery 失败时的 cache fallback
- 已支持 `discovery.mode=cache_only`
- 已支持 `discovery.cache_ttl` 在 compile 阶段复用新鲜 snapshot
- OpenAPI provider 已支持从本地/远程 spec 导入 operation、input schema、response schema、method/path/help notes
- OpenAPI provider 已支持 path/query/header/requestBody 归一化，并生成可执行 dry-run 请求计划
- GraphQL provider 已支持从本地/远程 introspection JSON 或 live introspection 导入 query/mutation
- GraphQL provider 已支持归一化 argument schema、生成默认 operation document，并生成可执行 dry-run 请求计划
- CLI provider 已支持 `source import-help`，可从真实 CLI `--help` 生成 manifest
- CLI provider 已支持 `source import-completion`，可从 completion 输出生成 manifest
- CLI provider 已支持 `source import-manpage`，可从 plain-text man page 生成 manifest
- CLI provider 已支持 `source import-schema`，可从 JSON schema 子命令生成 manifest
- CLI provider 已支持消费 importer 生成的 `command_argv + option_bindings` 结构
- `sync` 已支持基础 import diff / drift classify
- 已支持 `inspect drift`
- 已支持 breaking drift 的 mount freeze / manual review 治理
- 已支持 additive / compatible drift 的 policy-driven auto accept
- 已支持基础 `reconcile drift`
- `catalog export` 与 HTTP `/api/catalog`、`/api/drift` 已暴露 drift/governance 状态
- 已有基础 source freshness / TTL 运行时策略，但还没有完整治理合同、策略面板和 drift 联动
- capability snapshot 还没有进入独立 catalog/AI export 合同

结论：

- 当前能“调用”
- 已开始具备“可缓存、可回退、可追踪”的基础
- 还不能稳定支撑“规模化导入”和“上游变化治理”

### 3.3 帮助系统已经有骨架，但还不够丰富

当前动态 `--help` 已经能根据挂载命令和参数 schema 动态生成，但距离文档目标还有差距：

- provider 级帮助信息没有完全编译进最终帮助输出
- schema provenance 已进入动态 `--help`
- drift 状态已进入动态 `--help`
- `--help` 还没有基于 auth 状态、surface 暴露状态做动态提示
- 已支持 completion script 导出，但还没有 install/bootstrap 与回归治理
- 没有帮助快照测试

结论：

- “动态 help 可用”已经完成
- “动态 help 成为一等治理界面”还没有完成

### 3.3.1 Hook 系统已进入 foundation+governance MVP 阶段，但治理能力仍有明显缺口

当前已经有：

- plugin 注册 provider
- 配置驱动 hook 绑定
- `before/after/error` 三类基础 hook 语义
- hook warning 日志
- hook ordering / priority
- `when` 条件执行与 filter
- 稳定 `HookError`
- provider 注册冲突记录与暴露

但还缺少：

- per-hook schema / payload contract 文档快照
- config load 前置 hook
- auth / policy / workflow 级 hook
- async / streaming hook
- 更完整的 replay tooling 与 hook sandbox 能力

当前已新增一层 northbound debug MVP：

- HTTP `/api/extensions/summary`
- HTTP `/api/extensions/plugins`
- HTTP `/api/extensions/providers`
- HTTP `/api/extensions/hooks`
- HTTP `/api/extensions/contracts`
- HTTP `/api/extensions/events`
- HTTP `POST /api/extensions/hooks/explain`
- HTTP `POST /api/extensions/hooks/simulate`
- 前端 Extensions 页面
- hook dispatch start / complete / skipped / error 调试事件
- plugin/provider/hook inventory 可视化
- hook payload contract northbound 暴露
- extensions events 支持过滤与游标式继续加载
- hook `when` filter explain
- Hook Lab explain/simulate 面板
- contract sample payload / sample context
- simulate 风险边界与 side-effect 提示
- Hook Lab 本地保存/复用调试场景

### 3.4 日志、审计、run history 仍处于最小实现阶段

日志和可观测性是目前最大的实现缺口之一。

当前已经有：

- `app.jsonl`
- `audit.jsonl`
- SQLite `history.db`
- discovery snapshot cache
- `sync` import report
- capability snapshot
- `runs list/show` 最小查看入口
- `invoke` / `explain` 的基础执行留痕
- 基础敏感字段脱敏
- `secret` / `auth` / explain dry-run 请求中的敏感头与字段已脱敏
- `doctor` 中的 runtime path 输出
- hook failure warning 日志
- 配置加载日志
- discovery / schema import 日志
- HTTP `/api/logs/config`
- HTTP `/api/logs/discovery`
- HTTP `/api/logs/app`

但仍然缺少：

- 更细粒度的 help compile 日志治理
- 专门的前端日志页面与更完整筛选/详情交互

虽然 `run_id` / `trace_id` 现在已经能进入执行日志和 run history，且 HTTP 已可查询部分日志，但前端日志视图和更稳定的查询合同还没有完全接齐。

### 3.5 错误模型已完成第一版合同，但还不完整

当前已经有第一版稳定化：

- `ErrorEnvelope`
- 基础 `error.type`
- 基础 `error.code`
- 按错误类型区分的 exit code
- `HookError`

但还没有达到 RFC 里要求的完整“稳定错误合同”程度：

- 没有 Config / Auth / Policy / Timeout / Drift 等专用错误类型映射

### 3.6 Secret 管理已进入 MVP，但仍未完成完整外部凭据治理

当前已经有：

- 顶层 `secrets` 配置模型
- 独立 secret manager
- `env` / `file` / `literal` 三种解析方式
- `auth_profile.source=secret` 已可用
- CLI 与 HTTP 可查看 secret 脱敏状态

但还缺少：

- 系统 keyring / keychain
- 外部 secret manager / vault
- plugin 注册 secret provider
- source/header/body/query 层面的通用 `secret_ref` 注入
- secret rotation / provenance / last_checked_at
- secret 访问审计与策略控制
- 没有 DiscoveryError / SurfaceError 等更细分的稳定类型
- 没有恢复语义分类
- 没有 retryable / user_fixable 的系统级判定规则
- 没有 raw cause 脱敏保留策略
- 没有 northbound surface 的统一错误映射

结论：

- 当前错误输出对开发调试够用
- 对自动化、前端、长期脚本依赖还不够稳定

### 3.6 Reliability / 限流 / 幂等基本未落地

文档已经单独定义了 reliability 层，但当前代码中只有零散 timeout 透传，缺少统一执行治理：

- 没有统一 retry policy
- 没有 backoff / jitter
- 没有限流预算中心
- 没有并发控制
- 没有 idempotency key
- 没有 write / destructive 风险分级下的可靠性差异化处理
- 没有 workflow 级别可靠性语义

结论：

- 当前适合手工执行和开发验证
- 不适合高频自动化或存在写操作风险的生产场景

### 3.7 Auth 生命周期已进入 MVP，但还没有形成完整 delegated auth 平台

当前已经有：

- auth session store
- `cts manage auth list|status|login|refresh|logout|validate`
- HTTP `/api/auth/profiles`
- HTTP `POST /api/auth/login|refresh|logout`
- source 与 auth profile 的基础凭证解析
- auth 过期检测与基础恢复建议

未完成项包括：

- keyring / file store
- OAuth2 / device flow
- CLI delegated auth session
- 更完整的 delegated auth provider 合同
- 更细粒度的多账号/多环境治理

### 3.8 版本治理、兼容性、迁移、drift 仍未形成闭环

虽然配置模型已经预留了字段，且 drift 已进入可运行阶段，但整体治理闭环还没形成：

- 没有 compatibility checker
- 没有 config migration assistant
- 没有 catalog/state migration
- 已有 schema fingerprint 持久化
- `sync` 已接入基础 drift snapshot / diff / classify
- 已有 mount freeze / manual review 基础决策
- 已有 additive / compatible auto accept 基础决策
- 已有基础 `reconcile drift`
- 还没有更完整策略驱动冻结与恢复流程

这是中长期必须补的能力，因为 `cts` 的核心不是“一次接入”，而是“长期可维护”。

### 3.9 Northbound surface 已进入可运行 MVP，但还不是完整平台合同

当前已经有：

- `cts manage serve http`
- `cts manage serve jsonrpc`
- `cts manage serve mcp`
- 前端后端 API 已有一批只读接口：
  - `/api/app/summary`
  - `/api/sources`
  - `/api/mounts`
  - `/api/mounts/{id}`
  - `/api/mounts/{id}/help`
  - `/api/mounts/{id}/explain`
  - `/api/catalog`
  - `/api/runs`
- 已有扩展调试接口：
  - `/api/extensions/summary`
  - `/api/extensions/plugins`
  - `/api/extensions/providers`
  - `/api/extensions/hooks`
  - `/api/extensions/contracts`
  - `/api/extensions/events`
- 已有日志与治理只读接口：
  - `/api/drift`
  - `/api/logs/config`
  - `/api/logs/discovery`
  - `/api/logs/app`
- 已有第一批轻交互接口：
  - `POST /api/reload`
  - `POST /api/sync`
  - `POST /api/sync/{source}`
- `POST /api/extensions/hooks/explain`
- `POST /api/extensions/hooks/simulate`
- `cts manage ui` 已实现，可启动 HTTP API 并托管内置 UI

结论：

- 当前可作为统一本地 CLI
- 也已经具备 HTTP / JSON-RPC / MCP 三类 northbound 雏形
- 但离稳定、统一、长期可依赖的平台合同还有明显距离

### 3.10 前端目录已进入 MVP 实现态

`frontend/` 当前已经有：

- 方案文档
- `frontend/app` React + TypeScript + Vite 工程
- Dashboard / Sources / Source Detail / Mounts / Mount Detail / Catalog / Runs / Run Detail 页面
- Extensions 页面
- Auth / Drift / Logs / Alias 页面
- 对 `/api/*` 的只读接入
- Mount 详情页 explain 面板
- Dashboard 的 reload / sync 按钮
- Sources / Mounts / Aliases / Auth 已有第一批轻交互管理入口
- `npm run build` 可通过
- `cts manage serve http --ui` 可托管构建产物
- `cts manage serve http --ui --open` 可直接打开浏览器

当前还没有：

- explain 历史与交互式表单生成
- mount 直接执行入口与执行结果治理 UI
- 更完整的日志中心能力，包括分页、聚合、跨页面联动与更细粒度筛选
- reliability / secrets 等专门页面
- source / mount / run 与 drift / logs / explain 的更深联动

### 3.11 Workflow / plugin / 生态扩展层已启动，但离可治理生态还很远

当前已经开始：

- in-process plugin loader
- plugin provider registration
- config-driven hook binding
- hook ordering / filtering / fail_mode 治理
- provider conflict 记录
- workflow CLI 与 JSON-RPC 执行入口
- docs generator CLI

以下能力仍处于 RFC 或 foundation 阶段：

- 外部 plugin protocol
- plugin packaging / version gate / capability declaration
- workflow DAG / parallel_groups / 更完整 composite operation
- docs generator
- capability registry UI
- streaming / async job / batch 模型

## 4. 当前阶段的总体判断

现在的仓库已经完成了最重要的第一步：

- 统一模型已建立
- 配置编译链已打通
- 动态命令与动态 `--help` 已可运行
- source / mount / alias 基础治理命令已可运行
- CLI / HTTP / MCP 三类核心 provider 已有主路径
- plugin provider / hook foundation 已落地

但仍然明显属于“可运行 MVP”，还不是“可治理平台”。

如果此时直接继续横向加更多 provider，后面会遇到三个问题：

- 导入结果无法沉淀和治理
- 错误 / 日志 / auth / drift 会越来越碎
- 前端和北向接口没有稳定 backend 可以复用

因此下一阶段最重要的不是盲目继续扩 southbound 数量，而是沿着已经落地的 plugin/hook foundation，把 discovery / import / cache / governance 补齐。

## 5. 推荐的分阶段开发计划

下面的阶段按“依赖关系”排序，而不是按想做什么排序。

### Phase 1：MVP 收口与合同固化

目标：

- 把当前 CLI 从“可运行骨架”提升到“稳定 MVP”

本阶段应完成：

- `cts manage config lint`
- `cts manage source show|test`
- `cts manage mount show`
- `inspect` 中补 origin file、generated 来源、surface 暴露信息
- 稳定错误码与 exit code 映射
- 帮助输出补 provider notes、风险、示例、机器入口信息
- 动态 help 的回归测试
- catalog / inspect / explain 输出字段稳定化
- `source add` / `mount add` / `alias` / completion script 基础治理命令

建议交付标准：

- 文档中的 Phase 1 命令集基本齐备
- 脚本可以稳定依赖 `invoke` / `explain` / `inspect`
- `--help` 成为可依赖的调试入口

当前状态：

- 该阶段已基本完成，但仍缺 completion install/bootstrap、help snapshot、inspect/help 细节补全等产品化收尾项

粗略工作量：

- 单人约 1 到 1.5 周

### Phase 2：Discovery、导入与缓存落地

目标：

- 让 `cts` 从“能跑一次”变成“能持续接入多个 API / CLI / MCP”

当前已经落地：

- discovery cache 目录与写入格式
- schema provenance / confidence 持久化
- `sync` 写 catalog snapshot / import report
- provider / plugin capability snapshot
- discovery fallback（memory/cache）
- source snapshot fingerprint 与 operation fingerprint
- `cache_only` / `cache_ttl` 基础运行时策略
- `sync` 基础 drift classify（initial / unchanged / additive / compatible / breaking）
- breaking drift 的 mount freeze / manual review 运行时阻断
- additive / compatible drift 的 top-level/source/mount 级 auto accept
- 基础 `reconcile drift` 解锁流程
- source/mount 级 drift impact analysis 基础字段
- `catalog export` 与 HTTP drift 只读接口

本阶段剩余重点：

- 自动接受后的审计、恢复策略与更完整 drift impact analysis
- 更完整的 cache freshness / TTL / refresh policy 治理
- capability snapshot 的 northbound contract 稳定化
- hook payload contract / 更细粒度 debug tooling / 可视化治理

建议交付标准：

- 新 source 可通过导入或 sync 形成可复用的本地描述
- 动态命令和 `--help` 不依赖每次都在线实时探测
- 后续 drift 检测具备可用基线
- plugin provider / hook 不再只是“能挂进来”，而是能被稳定治理

粗略工作量：

- 单人约 1.5 到 2.5 周

### Phase 3：治理层补齐

目标：

- 把平台最关键的“稳定性、安全性、可追踪性”补上

本阶段应完成：

- app log / audit log / run history
- 日志脱敏
- timeout / retry / backoff 基础策略
- read/write 风险分层的可靠性默认值
- auth session store
- auth validate / refresh 基础流程
- compatibility checker
- config migration 框架
- schema drift snapshot / diff / classify
- `sync` 接入 drift check

建议交付标准：

- 每次执行都有 run history 可查
- 错误类型、exit code、日志事件可稳定依赖
- 读操作具备安全的基础自动重试
- drift 对 mount 的影响可观测

粗略工作量：

- 单人约 2 到 3 周

### Phase 4：Northbound API 与前端控制台

目标：

- 把 `cts` 从本地 CLI 工具升级成可被 UI 和其他程序复用的本地平台

本阶段应完成：

- `cts manage serve http`
- 只读 API：`/api/app/summary`、`/api/sources`、`/api/mounts`、`/api/catalog`
- 详情 API：`/api/mounts/{id}`、`/api/mounts/{id}/help`
- `reload` / `sync` 动作 API
- `frontend/app/` 工程初始化
- Dashboard
- Sources 列表页
- Mounts 列表页
- Mount 详情页
- Catalog 页面

建议交付标准：

- 前端不直接读配置文件
- 前后端共用同一套 catalog / inspect / explain 后端模型
- UI 可以完成“看清楚当前接了什么、挂成了什么、能不能给 AI 用”

粗略工作量：

- 单人约 2 到 3 周

### Phase 5：组合能力与生态扩展

目标：

- 让 `cts` 从统一接入层升级到统一编排层与扩展平台

本阶段应完成：

- workflow / composite operation
- 外部 plugin protocol
- plugin packaging / versioning / capability declaration
- docs generator
- shell completion
- `cts manage ui`
- 前端 auth / drift / logs 治理页面

可后置的高级能力：

- streaming
- batch execution
- async job / handle
- 更完整的预算中心与并发调度

建议交付标准：

- 平台可以组合多个 provider 能力
- 第三方可以按协议扩展 provider / surface
- northbound 不再只局限于本地 CLI

粗略工作量：

- 单人约 3 周以上

## 6. 建议的最近两轮开发顺序

如果现在就开始继续开发，建议不要平均铺开，而是按下面两轮推进。

### 6.1 下一轮先做什么

优先完成 Phase 2 的规模化导入与治理闭环：

- reconcile / freeze / manual review 流程
- capability snapshot northbound contract 稳定化

原因：

- 现在 Phase 1 主链路已经基本打通
- Phase 2 的 cache / provenance / snapshot 与 hook governance 最小闭环已经落地
- 接下来真正卡住长期扩展性的，是“如何更便宜地导入更多类型上游”以及“如何治理导入后的变化”

### 6.2 再下一轮做什么

在此之后继续推进 Phase 2 的规模化导入：

- hook payload contract / 更细粒度 debug tooling
- capability snapshot northbound contract 稳定化

原因：

- 这是“支持多种 API”真正成立的前提
- 没有导入缓存、payload contract 和 provenance，越接入越难治理

## 7. 一句话结论

当前 `cts` 已经完成了“统一能力平面的可运行骨架”，并且已经进入 plugin/hook foundation 阶段。下一步最合理的方向是：

1. 在现有 plugin/hook foundation 上继续补 discovery/import/cache 与 drift 治理。
2. 再补日志、错误、auth、reliability 的稳定合同。
3. 再把现有 HTTP / JSON-RPC / MCP surface 和前端控制台做成更稳定的平台入口。
4. 最后再推进外部 plugin protocol、workflow 深化与生态层。

这样后面无论继续接 API、CLI、MCP、plugin，都会是增量扩展，而不是返工重构。
