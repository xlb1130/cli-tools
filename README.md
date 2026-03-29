# cts 设计文档

这个仓库当前保存 `cts` 的架构设计方案。`cts` 的目标不是只包装 MCP，而是提供一个长期可扩展的统一 CLI 平台，把 MCP、HTTP、OpenAPI、GraphQL、任意本地或远程 CLI、Shell 脚本等能力统一挂载成层级命令。

文档索引：

- [RFC 总纲：cts 统一能力平面主架构](docs/00-rfc-master-architecture.md)
- [平台总览](docs/01-platform-overview.md)
- [配置模型与命令映射](docs/02-config-model.md)
- [Provider SDK 与接入协议](docs/03-provider-sdk.md)
- [运行时、执行流与安全](docs/04-runtime-execution.md)
- [实施路线图与工程拆分](docs/05-implementation-plan.md)
- [AI 友好与北向接口设计](docs/06-ai-friendly-architecture.md)
- [导入与参数 Schema 发现](docs/07-import-and-schema-discovery.md)
- [日志与可观测性](docs/08-observability-and-logs.md)
- [错误处理与恢复](docs/09-error-handling-and-recovery.md)
- [版本治理与迁移](docs/10-versioning-and-migration.md)
- [认证与会话生命周期](docs/11-auth-lifecycle.md)
- [可靠性、限流与幂等](docs/12-reliability-and-rate-limits.md)
- [Schema 漂移与对账](docs/13-schema-drift-and-reconciliation.md)
- [当前实现状态与分阶段开发计划](docs/14-status-and-roadmap.md)
- [前端控制台](frontend/README.md)
- [示例配置](docs/examples/cts.example.yaml)

建议阅读顺序：

1. 先看 RFC 总纲，统一主架构、稳定合同和核心决定。
2. 再看平台总览，快速建立 `source -> operation -> mount -> surface` 心智模型。
3. 再看配置模型，理解 `source`、`mount`、`profile`、`policy`。
4. 接着看 Provider SDK，确认 MCP、HTTP、CLI 等怎么接。
5. 再看导入与参数 Schema 发现，确认不同 API、CLI、MCP 怎么拿参数格式。
6. 接着看认证与会话生命周期，确认不同来源的登录、刷新、注销怎么统一。
7. 再看可靠性、限流与幂等，确认超时、重试、配额、重复执行如何治理。
8. 然后看 Schema 漂移与对账，确认上游 API、CLI、MCP 变化后怎么发现和修复。
9. 再看日志与可观测性，确认配置加载、导入、执行全过程怎么留痕。
10. 再看错误处理与恢复，确认失败时怎么稳定、可恢复、可观察。
11. 然后看版本治理与迁移，确认配置、缓存、provider、surface 怎么演进不炸兼容性。
12. 再看 AI 友好与北向接口、前端控制台与实施路线图，确定 northbound 形态和 MVP 落地顺序。
