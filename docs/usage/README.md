# Usage Guide

`docs/usage` 这一组文档专门面向“怎么实际使用 `cts`”。

如果 `docs/00-15` 更偏架构、设计和长期演进，那么这个目录回答的是另一类问题：

> 我到底该怎么一步一步把能力接进来、挂起来、执行起来？

建议阅读顺序：

1. [01-quickstart](./01-quickstart/README.md)：最快跑通一个命令
2. [02-local-cli](./02-local-cli/README.md)：本地 CLI 命令的导入方式，从简单到进阶
3. [03-shell](./03-shell/README.md)：Shell 脚本和 shell 任务的挂载方式
4. [04-http](./04-http/README.md)：手工挂载 HTTP API
5. [05-openapi](./05-openapi/README.md)：从 OpenAPI spec 导入操作
6. [06-graphql](./06-graphql/README.md)：从 GraphQL schema / introspection 导入操作
7. [07-mcp](./07-mcp/README.md)：接入 MCP server 并批量导入 tools
8. [08-mounts](./08-mounts/README.md)：mount 的设计、命名、批量导入与暴露方式
9. [09-execution](./09-execution/README.md)：执行、explain、dry-run、inspect 和 serve
10. [10-plugins](./10-plugins/README.md)：通过 plugin 扩展新的 provider
11. [11-hooks](./11-hooks/README.md)：给 discovery / help / explain / invoke 绑定 hook

这组文档遵循几个原则：

- 先从最简单能跑通的路径开始，再逐步增加控制能力
- 示例文件尽量放在对应目录旁边，方便照抄
- 把 provider 接入、mount 设计、执行方式拆开讲清楚
- 需要时同时给出 CLI 驱动和配置驱动两种方式

说明：

- 每个目录下的 `examples/` 都是为了配合该章节的讲解
- 有些示例可以直接在当前仓库里运行
- 有些示例是模板，需要替换成你自己的 URL、认证信息或 schema 文件
