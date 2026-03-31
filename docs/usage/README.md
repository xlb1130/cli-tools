# 使用指南

这组文档按“由简到难”的顺序组织，建议不要从 provider 细节开始硬读，而是先跑通，再扩展。

先记住一个总入口：

```bash
cts import <provider-type> ...
cts import wizard
cts import wizard <provider-type>
```

`import` 现在由 provider 自己定义参数和 wizard，内置 provider 与 plugin provider 走同一条导入链路。

## 推荐阅读顺序

### 第 1 步：先跑通一个最小例子

1. [5 分钟上手](01-quickstart/README.md)

这一篇解决两个问题：

- `cts` 到底编译出了什么
- `source / operation / mount` 在真实命令里长什么样

### 第 2 步：接入你自己的本地命令

2. [本地 CLI](02-local-cli/README.md)
3. [Shell 脚本](03-shell/README.md)

什么时候读哪篇：

- 你要接已有可执行程序，先看“本地 CLI”
- 你要包一段本地脚本或命令串，先看“Shell 脚本”

### 第 3 步：接外部能力源

4. [HTTP API](04-http/README.md)
5. [OpenAPI](05-openapi/README.md)
6. [GraphQL](06-graphql/README.md)
7. [MCP Server](07-mcp/README.md)

建议顺序：

- 已有裸 HTTP 接口：先读 HTTP
- 已有 OpenAPI 规范：直接读 OpenAPI
- 已有 GraphQL schema：直接读 GraphQL
- 已有 MCP server：直接读 MCP

### 第 4 步：进入稳定命名与执行模型

8. [Mount 设计](08-mounts/README.md)
9. [执行方式](09-execution/README.md)

这两篇适合在你已经能导入能力之后再看，因为它们关注的是：

- 怎么给命令起稳定名字
- 怎么通过 `invoke`、`explain`、`dry-run` 调用
- 怎么在不同 surface 之间保持一致

### 第 5 步：最后再做扩展开发

10. [Plugin](10-plugins/README.md)
11. [Hook](11-hooks/README.md)

只有在内置 provider 不够用，或者你要扩 southbound / northbound 行为时，再进入这两篇。

## 按场景选文档

如果你现在的目标是下面这些，可以直接跳：

- 想先确认项目能跑：看 [5 分钟上手](01-quickstart/README.md)
- 想导入一个单独命令：看 [本地 CLI](02-local-cli/README.md)
- 想导入一整棵子命令树：看 [本地 CLI](02-local-cli/README.md)
- 想接入远端 MCP tools：看 [MCP Server](07-mcp/README.md)
- 想理解命令路径、稳定 id、alias：看 [Mount 设计](08-mounts/README.md)
- 想理解 `invoke` 和 `explain`：看 [执行方式](09-execution/README.md)
- 想自己扩 provider：看 [Plugin](10-plugins/README.md)

## 一张脑图

```text
Quickstart
  -> Local CLI / Shell
    -> HTTP / OpenAPI / GraphQL / MCP
      -> Mounts / Execution
        -> Plugin / Hook
```

## 文档原则

- 先跑通，再理解原理
- 先单命令，再整棵树
- 先本地能力，再外部能力源
- 先使用，再扩展

## 相关入口

- [项目首页 README](../../README.md)
- [架构文档](../00-rfc-master-architecture.md)
- [配置模型](../02-config-model.md)
- [安装与使用说明](../15-install-and-usage.md)
