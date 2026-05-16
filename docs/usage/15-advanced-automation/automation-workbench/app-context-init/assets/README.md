# App Context Assets

## 目标

这一目录承载 `app-context-init` 负责分发和维护的全部资产，包括治理文档、通用执行契约、公共脚本和模板配置。

它回答四个问题：

- 哪些资产属于初始化 skill 自己维护
- 这些资产分发到哪里
- 谁应该读哪一组文档
- 新增资产时应遵循什么结构

## 目录结构

- `own-docs/`
  面向工程治理与交付控制，强调架构、质量、稳定性、发布和安全约束。
- `common-docs/`
  面向所有 skill 复用的统一执行契约，强调上下文、权限、追踪、指标和错误处理。
- `common-scripts/`
  面向脚本复用和自动化基础能力。
- `templates/`
  面向初始化阶段生成或合并的配置模板。

## 分发目标

- `own-docs/` -> `~/.cts/automation-workbench/docs/`
- `common-docs/` -> `~/.cts/common/docs/`
- `common-scripts/` -> `~/.cts/common/scripts/`
- `templates/mcp-servers.json.example` -> `~/.config/mcp/mcp_servers.json`
- `templates/settings.conf.example` -> `~/.cts/settings.conf`
- `templates/agent-context-snippet.md.example` -> `./CLAUDE.md`, `./AGENTS.md` 等 agent context 文件

## 推荐 MCP Aliases

默认模板中的 alias 采用面向场景的命名，不直接暴露底层实现细节：

- `dingtalk`
- `yunxiao`
- `mysql`
- `gitlab`
- `playwright`
- `redis`
- `grafana`
- `kubernetes`

这些 alias 由 `app-context-init` 统一初始化，其他 skill 只消费，不重新定义。

## Agent Context Injection

初始化不应只分发完整文档，还应把规范摘要注入到 agent 常读的上下文文件里，例如：

- `./CLAUDE.md`
- `./AGENTS.md`

注入内容应包括：

- 护栏规则摘要
- 哪个文件是干什么的
- 什么时候应该读哪个文件
- 对应源文件路径
- 场景优先而不是工具优先的执行原则
- 推荐 MCP alias
- 文档资产所在路径
- 安全与敏感信息约束

详细规则参考 [agent-context-injection.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/usage/15-advanced-automation/automation-workbench/app-context-init/references/agent-context-injection.md)。

## 阅读顺序

### 第一次接入 automation-workbench

1. `own-docs/01-guardrails.md`
2. `common-docs/05-path-conventions.md`
3. `common-docs/04-file-permissions.md`
4. `own-docs/14-release-checklist.md`
5. `own-docs/15-security-baseline.md`

### 需求进入与方案阶段

1. `own-docs/03-checkpoints.md`
2. `own-docs/16-task-anchor-check.md`
3. `own-docs/08-client-compatibility.md`
4. `own-docs/12-coding-guidelines.md`
5. `common-docs/01-context-object.md`

### 排障与发布阶段

1. `own-docs/05-health-check.md`
2. `own-docs/11-reliability-five-pieces.md`
3. `own-docs/14-release-checklist.md`
4. `common-docs/06-metrics-tracking.md`
5. `common-docs/08-execution-tracking.md`

## 文档分层原则

### own-docs

适合放入：

- 组织级约束
- 架构治理原则
- 发布与稳定性控制点
- 安全和兼容性底线

不适合放入：

- 单一 skill 的临时用法
- 易过期的局部命令说明
- 与业务无关的底层实现细节

### common-docs

适合放入：

- 所有 skill 共享的数据结构
- 统一错误处理和追踪口径
- 路径、权限、指标、耗时等横切规则

不适合放入：

- 特定业务域规则
- 特定系统专属约束

### common-scripts

适合放入：

- 任务 ID 生成
- 统一上报
- Token 采集
- 通用 hook 和工具函数

不适合放入：

- 单个业务域专属脚本
- 高风险写操作默认入口
- 强依赖某一条交付链路的编排逻辑

## 对 skill 的映射

- `app-context-init`
  依赖全部资产，负责分发、校验与 agent context 注入。
- `requirements-development`
  重点依赖 `01-context-object.md`、`03-checkpoints.md`、`16-task-anchor-check.md`。
- `incident-diagnosis`
  重点依赖 `01-guardrails.md`、`05-health-check.md`、`11-reliability-five-pieces.md`、`08-execution-tracking.md`。
- `release-verify`
  重点依赖 `14-release-checklist.md`、`06-metrics-tracking.md`、`07-duration-baseline.md`。
- `security-review`
  重点依赖 `15-security-baseline.md`、`04-file-permissions.md`。
- `self-evolution`
  重点依赖 `10-self-evolution.md`、`03-token-tracking.md`、`08-execution-tracking.md`。

## 新增文档约定

新增文档前先判断：

- 它是治理资产还是执行契约
- 它是长期稳定规则还是易变用法
- 它是否会被多个 skill 复用

默认结构参考 [document-structure.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/usage/15-advanced-automation/automation-workbench/app-context-init/references/document-structure.md)。

脚本职责参考 [common-scripts/README.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/usage/15-advanced-automation/automation-workbench/app-context-init/assets/common-scripts/README.md)。

Agent context 注入规则参考 [agent-context-injection.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/usage/15-advanced-automation/automation-workbench/app-context-init/references/agent-context-injection.md)。
