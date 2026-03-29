# 版本治理与迁移

## 1. 为什么这层必须单独设计

`cts` 不是单一 CLI，而是一个长期演进的统一能力平面。它的变化面至少包括：

- 配置文件结构
- southbound provider SDK
- northbound surface 合同
- discovery cache / catalog / run history
- 动态挂载命令的人类路径
- AI 与自动化依赖的稳定机器合同

如果没有独立的版本治理层，后面每引入一种新协议、每调整一次配置模型、每升级一次 provider，都会把用户已有的 mount、自动化脚本和前端页面一起拖垮。

## 2. 需要被治理的版本对象

建议明确区分下面几类版本。

### 2.1 配置版本

用于描述 `config.yaml` 的结构版本。

### 2.2 Provider SDK 版本

用于描述 southbound provider 接口能力的演进，例如：

- 新增 `refresh_auth()`
- 新增 schema provenance 字段
- 新增 streaming 或 completion 能力

### 2.3 上游 API / CLI / MCP 版本

这是被接入系统本身的版本，例如：

- OpenAPI spec version
- GraphQL schema hash
- CLI binary version
- MCP server release version

### 2.4 Catalog / Capability Contract 版本

用于 northbound 稳定消费，例如：

- `cts catalog export`
- `cts explain`
- `cts invoke` 的 JSON 输入输出结构

### 2.5 Cache / State Schema 版本

用于：

- discovery cache
- schema cache
- run history
- auth session state

### 2.6 Frontend API 版本

用于前端控制台访问本地 `cts` backend 时的接口兼容治理。

## 3. 兼容性承诺应该怎么分层

不是所有对象都要“永久兼容”，但必须提前定义哪些稳定、哪些可变。

### 3.1 必须长期稳定的合同

建议长期稳定：

- `mount.id`
- `machine.stable_name`
- `cts invoke <mount-id>` 的调用语义
- `ErrorEnvelope.type/code`
- capability card 的核心字段

### 3.2 可以演进但必须给迁移工具的对象

建议允许演进，但必须提供 migration：

- `command.path`
- alias 结构
- 配置字段重命名
- surface 的扩展字段
- schema cache 的内部结构

### 3.3 可以自由变化的对象

例如：

- 控制台展示文案
- help 文本排序
- 默认颜色和前端布局
- 日志里的非核心扩展字段

## 4. 版本规则建议

## 4.1 配置版本

建议使用显式 `version` 字段：

```yaml
version: 1
```

升级原则建议：

- 同一主版本内可做向后兼容新增
- 出现删除字段、语义变化、默认行为重大变化时再升级主版本
- `cts config migrate` 负责把旧配置改写到新版本

## 4.2 Provider SDK 版本

建议 provider metadata 显式声明：

- 自身版本
- 依赖的最小 `cts` 版本
- 对接的上游 API 版本

这样可以在加载阶段提前报出：

- provider 太老
- `cts` 核心太老
- 上游版本超出已验证区间

## 4.3 上游能力版本

建议为不同类型记录不同的 fingerprint：

- HTTP/OpenAPI: spec URL + ETag/hash + fetched_at
- GraphQL: schema hash
- CLI: `binary version + manifest version`
- MCP: `server identity + tool fingerprint`
- plugin: plugin protocol version + plugin build version

## 4.4 Surface 版本

建议 northbound surface 都带显式版本前缀或版本字段，例如：

- HTTP API: `/api/v1/...`
- JSON-RPC: `protocol_version`
- catalog export: `catalog_version`

## 5. 配置中的兼容治理模型

建议增加顶层 `compatibility`：

```yaml
compatibility:
  min_cts_version: "0.1.0"
  catalog_version: 1
  error_contract_version: 1
  command_contract:
    mount_id_stable: true
    stable_name_stable: true
  migrations:
    auto_apply_patch_updates: true
```

source 级也建议支持：

```yaml
sources:
  gh_cli:
    type: cli
    executable: gh
    compatibility:
      min_binary_version: "2.45.0"
      tested_range: ">=2.45,<3.0"
      break_on_major_upgrade: true
```

mount 级建议支持：

```yaml
mounts:
  - id: github-list-issues
    machine:
      stable_name: github.issue.list
    compatibility:
      deprecates:
        command_paths:
          - [gh, issues, ls]
      replacement_mount: github-list-issues
```

## 6. 迁移要覆盖哪些场景

## 6.1 配置迁移

例如：

- `auth` 内联结构迁到 `auth_profiles`
- `retry.max_attempts` 重命名为 `reliability.retry.max_attempts`
- 某个 source 字段从 `server_name` 改成 `server`

建议支持：

- dry-run 预览
- 自动改写
- migration report

## 6.2 命令路径迁移

这类迁移最常见。

例如：

- `cts gh issues list`
- 迁到 `cts dev github issues list`

建议做法：

- 保留 `mount.id`
- 新路径生效
- 旧路径通过 alias 兼容一段时间
- `--help` 明确提示旧路径已废弃

## 6.3 Provider 与 source 迁移

例如：

- `mcp_cli` provider 未来替换为 `mcp_native`
- HTTP source 从手工配置迁到 OpenAPI 导入
- CLI manifest 从 v1 升级到 v2

建议原则：

- 尽量不改 `mount.id`
- 尽量不改 `machine.stable_name`
- 使用 operation fingerprint 做自动对账

## 6.4 Cache / State 迁移

包括：

- discovery cache
- run history
- auth session store
- frontend local cache

建议：

- 每类状态都带 `schema_version`
- 升级时先做惰性迁移
- 失败可回退到重建缓存

## 7. 迁移流程建议

建议统一成四步。

### 7.1 Detect

识别：

- 版本不兼容
- 字段已废弃
- source/provider 超出验证区间
- 上游二进制或 schema 变化

### 7.2 Explain

输出可读报告：

- 哪些对象受影响
- 是新增、废弃还是 breaking
- 哪些 mount 会被波及

### 7.3 Apply

提供三种策略：

- 自动迁移
- 生成 patch，等待确认
- 标记为 deprecated，暂不迁

### 7.4 Verify

迁移后自动校验：

- 配置可加载
- mount 仍能解析
- capability card 仍能生成
- `cts invoke` / `cts explain` 合同未破坏

## 8. 建议的命令

- `cts config migrate`
- `cts doctor compatibility`
- `cts inspect versions`
- `cts sync --check-drift`
- `cts catalog export --versioned`

这些命令不一定第一阶段都实现，但模型上建议预留。

## 9. 日志与审计要求

建议新增事件：

- `compat_check_start`
- `compat_check_failed`
- `migration_plan_created`
- `migration_applied`
- `migration_skipped`
- `migration_rolled_back`

关键字段建议记录：

- `from_version`
- `to_version`
- `migration_type`
- `affected_sources`
- `affected_mounts`
- `requires_manual_action`

## 10. 对 AI 与自动化系统的特别要求

AI 或脚本最怕“名字没变，但语义变了”。

因此建议：

- `mount.id` 语义变化时必须视为 breaking change
- `machine.stable_name` 如果改名，必须给 replacement
- capability card 增加 `deprecated` 与 `replacement_mount_id`
- `cts invoke` 返回中可附带 deprecation warning，但不能悄悄换行为

## 11. 最终建议

版本治理的关键不是“把所有东西都做成 semver”，而是把变化分清楚：

- 哪些是稳定合同
- 哪些允许重命名
- 哪些必须给迁移器
- 哪些只需提示不兼容

这样 `cts` 才能在不断接入新协议、新 CLI、新 surface 的同时，保持对人类、前端、AI 和自动化系统都足够稳定。
