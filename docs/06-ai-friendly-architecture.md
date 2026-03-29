# AI 友好与北向接口设计

## 1. 为什么要单独设计这一层

如果 `cts` 只考虑“人怎么在终端里敲命令”，它仍然只是一个强大的 CLI。

但如果要做到真正 AI 友好，`cts` 必须让 AI/Agent/自动化系统能够：

- 发现有哪些能力可用
- 理解每个能力的输入输出合同
- 用稳定接口发起调用
- 在调用前先看执行计划
- 得到结构化、稳定、可恢复的结果和错误
- 在需要时把 `cts` 整体再暴露成 MCP 或 HTTP 服务

因此 AI 友好不是“支持 JSON 输出”这么简单，而是一层独立的架构责任。

## 2. 北向接口的四种形态

`cts` 应同时支持四种北向消费方式。

### 2.1 人类友好的动态命令树

例如：

```bash
cts dev github issues list --repo owner/repo
```

适合：

- 工程师手动执行
- 团队共享命令路径

### 2.2 稳定机器调用入口

例如：

```bash
cts invoke github-list-issues --input-json '{"repo":"owner/repo"}' --output json
```

这应该是 AI、脚本、CI、自动化系统的首选入口。

原因：

- 不依赖动态命令路径
- 不依赖帮助文本解析
- 以 `mount.id` 作为稳定合同

### 2.3 本地 HTTP / JSON-RPC Gateway

例如：

```bash
cts serve http --bind 127.0.0.1:7788
cts serve jsonrpc --bind 127.0.0.1:7789
```

适合：

- 外部程序进程间调用
- Web UI 或守护进程调用
- 团队把 `cts` 当本地 capability gateway 用

### 2.4 MCP Bridge

例如：

```bash
cts serve mcp
```

这会把 `cts` 已挂载的能力重新暴露为一个 MCP server，让 Claude、Cursor、Codex、其他 agent 平台可以直接消费。

这一步非常关键，因为它让 `cts` 从“消费外部能力的 CLI”升级为“可被 AI 使用的统一工具平面”。

## 3. AI 友好的核心合同

所有对 AI 暴露的 mount，都建议生成统一的 capability card。

建议字段：

- `mount_id`
- `stable_name`
- `summary`
- `description`
- `risk`
- `input_schema`
- `output_schema`
- `examples`
- `tags`
- `supported_surfaces`
- `requires_confirmation`
- `supports_dry_run`
- `supports_stream`

这样 AI/自动化层不需要阅读人类帮助文本，也不需要猜测参数。

## 4. 稳定合同优先级

建议明确两类合同：

### 4.1 人类路径合同

例如：

```bash
cts ops jira issue get
```

这是可读路径，可以调整、重构、迁移。

### 4.2 机器合同

例如：

```bash
mount.id = jira-get-issue
stable_name = jira.issue.get
```

这应该尽量长期稳定。

结论：

- 人类路径是 UX
- `mount.id` 和 `stable_name` 才是 API contract

## 5. AI/自动化模式要求

建议从第一版开始就支持严格的 non-interactive 模式：

- 默认 `--output json`
- 不输出 ANSI 色彩
- 不输出模糊提示语
- 错误为结构化 JSON
- 退出码稳定
- 需要确认的操作直接返回 policy error，除非显式给 `--yes`

推荐命令：

```bash
cts invoke jira-get-issue --input-json '{"key":"ABC-123"}' --output json --non-interactive
```

## 6. Explain / Plan / Dry-run

AI 系统特别需要在执行前理解“将要发生什么”。

因此建议每个可执行 mount 支持：

- `explain`
- `dry-run`
- `render-request`

示例：

```bash
cts explain jira-get-issue --input-json '{"key":"ABC-123"}'
cts invoke jira-get-issue --input-json '{"key":"ABC-123"}' --dry-run
```

Explain 输出建议包括：

- 命中的 source / provider
- 命中的 operation
- 归一化后的参数
- 风险级别
- 是否需要确认
- 将访问的 URL、CLI argv 或 MCP target

## 7. Catalog 与可发现性

AI 要真正好用，必须能拿到完整能力目录。

建议提供：

```bash
cts catalog export --format json
cts inspect mount github-list-issues --format json
```

Catalog 应至少包含：

- 所有 mount
- 所有 source
- mount 和 source 关系
- schema、标签、风险、示例
- 哪些 mount 对哪些 northbound surface 可见

## 8. 组合能力比单次调用更重要

单 API 的封装很常见，但 AI/Agent 的真正价值常常来自跨系统编排，例如：

- 从 GitHub 读 issue，再写 Jira
- 从告警系统读告警，再执行内部 CLI，再通知 Slack
- 查 Kubernetes 状态，再触发发布工具，再查询工单系统

因此建议在 `cts` 的长期架构中保留 workflow/composite operation。

最小设计原则：

- workflow 自己也应当是 operation
- workflow 也应当能被 mount
- workflow 也应当出现在 catalog 中
- workflow 的输入输出也应当有 schema

## 9. AI 友好的配置增强点

建议 mount 配置支持以下机器字段：

```yaml
mounts:
  - id: github-list-issues
    machine:
      stable_name: github.issue.list
      expose_via: [cli, invoke, mcp]
      examples:
        - input:
            repo: owner/repo
      annotations:
        safe_for_agent: true
        side_effect_free: true
```

推荐含义：

- `stable_name` 供程序或 AI 引用
- `expose_via` 控制哪些北向接口可见
- `annotations` 存放 AI 友好元数据

## 10. Serve 模式的价值

只做 CLI 会让 `cts` 的复用边界停留在 shell。

如果支持：

- `cts serve mcp`
- `cts serve http`
- `cts serve jsonrpc`

那 `cts` 就能成为统一能力网关：

- 南向接各种 API、CLI、脚本
- 北向给 AI、自动化、网页、IDE 或其他服务使用

这是整个架构长期价值最大的部分之一。

## 11. 机器错误模型

AI 最怕“像人类一样写出来的错误文本”。

建议机器模式输出统一结构：

```json
{
  "ok": false,
  "error": {
    "type": "PolicyError",
    "code": "confirm_required",
    "message": "Operation requires confirmation",
    "details": {
      "mount_id": "terraform-apply"
    }
  }
}
```

## 12. 最终建议

如果把 AI 友好真正做进架构，`cts` 的定位会更清晰：

- 南向是多协议接入平台
- 中间是统一 operation 与 mount 平面
- 北向是 CLI、机器调用、MCP、HTTP 等统一暴露层

这样 `cts` 不只是“一个聚合命令行”，而是一个可以同时服务人类和 AI 的能力编排内核。
