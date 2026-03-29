# API 契约

## 1. 设计目标

前端 API 应该服务于“展示能力目录和配置状态”，而不是暴露所有执行能力。

第一版建议以只读接口为主，少量动作接口为辅。

## 2. 基本原则

- 所有返回都用 JSON
- 返回结构稳定
- `mount.id` 作为主要资源 id
- 所有时间字段使用 ISO 8601
- 所有错误返回统一结构

## 3. 建议接口

## 3.1 应用摘要

```http
GET /api/app/summary
```

返回示例：

```json
{
  "app": "cts",
  "profile": "dev",
  "config_files": [
    "/Users/x/.config/cts/config.yaml",
    "/workspace/.cts/config.yaml"
  ],
  "source_count": 6,
  "mount_count": 22,
  "surfaces": {
    "cli": true,
    "invoke": true,
    "mcp": false,
    "http": false
  },
  "last_sync_at": "2026-03-28T08:00:00Z"
}
```

## 3.2 Source 列表

```http
GET /api/sources
```

返回项建议包含：

- `name`
- `type`
- `provider`
- `enabled`
- `profile_scope`
- `expose_to_surfaces`
- `health`

## 3.3 Mount 列表

```http
GET /api/mounts
```

支持 query：

- `q`
- `risk`
- `source`
- `surface`

返回项建议包含：

- `id`
- `stable_name`
- `command_path`
- `source`
- `operation`
- `risk`
- `requires_confirmation`
- `supported_surfaces`

## 3.4 Mount 详情

```http
GET /api/mounts/{mount_id}
```

返回建议包含：

- mount 配置摘要
- operation descriptor
- capability card
- examples
- policy

## 3.5 Catalog

```http
GET /api/catalog
GET /api/catalog/{mount_id}
```

它面向机器和前端详情页。

## 3.6 Explain

```http
POST /api/mounts/{mount_id}/explain
```

请求：

```json
{
  "input": {
    "repo": "owner/repo"
  }
}
```

返回：

```json
{
  "mount_id": "github-list-issues",
  "provider": "mcp_cli",
  "risk": "read",
  "requires_confirmation": false,
  "rendered_request": {
    "command": [
      "mcp-cli",
      "call-tool",
      "github:list_issues"
    ]
  }
}
```

## 3.7 Help

```http
GET /api/mounts/{mount_id}/help
```

返回建议包含：

- `usage`
- `summary`
- `description`
- `arguments`
- `examples`
- `risk`
- `stable_name`
- `supported_surfaces`

## 3.8 Reload / Sync

```http
POST /api/reload
POST /api/sync
POST /api/sync/{source}
```

第一版可以只做：

- `reload` 重新读取配置
- `sync` 刷新 discovery cache

## 3.9 Logs

后续建议增加：

```http
GET /api/logs/runs
GET /api/logs/runs/{run_id}
GET /api/logs/config
GET /api/logs/sync
```

第一版可以先不实现完整日志查询接口，但后端日志结构应先定下来。

## 3.10 Extensions / Debug

为了让 plugin/provider/hook 不只是“能挂进来”，还要“能被人和前端调试”，当前 northbound API 已补充一组扩展调试接口：

```http
GET /api/extensions/summary
GET /api/extensions/plugins
GET /api/extensions/providers
GET /api/extensions/hooks
GET /api/extensions/contracts
GET /api/extensions/events
POST /api/extensions/hooks/explain
POST /api/extensions/hooks/simulate
```

用途分别是：

- `/api/extensions/summary`
  - 返回 plugin/provider/hook 总量、冲突数量、按事件聚合的 hook 计数
- `/api/extensions/plugins`
  - 返回每个 plugin 的来源、provider 注册结果、hook handler 与已绑定 hook
- `/api/extensions/providers`
  - 返回 provider 所有权信息
  - 区分 core provider 与 plugin provider
  - 返回 source / mount 关联数量
- `/api/extensions/hooks`
  - 返回所有 hook 绑定
  - 支持按 `event` 与 `plugin` 过滤
- `/api/extensions/contracts`
  - 返回 hook lifecycle 的 payload contract
  - 暴露每个 event 的字段、是否必填、允许改写哪些 payload key
  - 还会返回 sample payload、上下文需求和 simulate 风险边界
- `/api/extensions/events`
  - 返回最近的 hook dispatch / 扩展相关调试事件
  - 当前主要覆盖 `hook_dispatch_start|complete|skipped|error` 与 `hook_failed`
  - 支持按 `event`、`plugin`、`hook_event`、`level`、`mount_id`、`source` 过滤
  - 支持 `before_ts` 游标式翻页
- `/api/extensions/hooks/explain`
  - 输入 event、payload、可选 `mount_id` / `source_name`
  - 返回每个 hook 的命中判断、criteria、实际 context 值
- `/api/extensions/hooks/simulate`
  - 在 explain 基础上，可选择执行 hook handler 链
  - 不触发 southbound provider 调用
  - 用于验证 payload 改写、handler 顺序和 fail_mode 影响
  - 返回 simulation 元数据，明确 provider 调用已阻断、mount 执行已阻断，但 plugin handler 仍可能产生副作用

这一组接口的定位是：

- 给前端做扩展调试控制台
- 给 AI/脚本做 extension inventory 与治理检查
- 给插件开发者排查 provider 冲突、hook 绑定、when filter 生效情况

## 4. 错误结构

建议统一：

```json
{
  "ok": false,
  "error": {
    "type": "ConfigError",
    "code": "invalid_yaml",
    "message": "Failed to parse config file",
    "details": {
      "file": "/workspace/.cts/config.yaml"
    }
  }
}
```

## 5. API 与后端模块映射

建议 Python 端这样对应：

- `/api/app/summary` -> `config + registry + discovery.catalog`
- `/api/sources` -> `registry.sources`
- `/api/mounts` -> `registry.mounts`
- `/api/catalog` -> `discovery.catalog`
- `/api/extensions/*` -> `plugins.loader + provider.registry + app.jsonl debug events`
- `/api/mounts/:id/explain` -> `execution.planner`
- `/api/reload` -> `config.loader + registry rebuild`

## 6. 不建议第一版就开放的接口

先不要急着做：

- 任意命令执行
- 配置在线编辑
- 删除/新增 source
- 高风险命令执行按钮

第一版先把“可视化可读”做好。
