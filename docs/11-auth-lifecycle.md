# 认证与会话生命周期

## 1. 为什么不能只把认证当成 source 的一个字段

`cts` 要接的不只是 HTTP API，还包括：

- MCP server
- OpenAPI / GraphQL
- 任意 CLI
- shell 脚本
- plugin / 内部 RPC

这些来源的鉴权形式差异极大。如果认证只散落在各 source 里，后面会出现：

- 无法统一登录流程
- 无法统一 token 刷新
- 前端不知道当前 source 是否已登录
- 日志里无法稳定记录 auth 状态
- provider 各自发明一套 session 管理

所以认证必须是一等能力。

## 2. 设计目标

认证层至少要满足：

- 支持多种 auth 类型
- 支持多个环境与多个账号
- 支持 headless 和交互式两种模式
- 支持登录、刷新、注销、状态查看
- 支持 provider 级 delegated auth
- 对 AI 与自动化系统暴露稳定状态

## 3. 推荐的统一模型

建议把认证拆成三层。

### 3.1 `auth_profiles`

用于定义“认证方式和凭证来源”。

```yaml
auth_profiles:
  jira-dev:
    type: bearer
    source: env
    token_env: JIRA_DEV_TOKEN

  github-oauth:
    type: oauth2
    grant_type: device_code
    client_id_env: GITHUB_CLIENT_ID
    scopes: [repo, read:org]
    session_store: keyring
```

### 3.2 source 绑定

source 只引用 auth，而不重复定义完整认证逻辑。

```yaml
sources:
  jira_http:
    type: http
    base_url: https://jira.example.com/rest/api/3
    auth_ref: jira-dev
```

### 3.3 运行时 auth session

运行时维护会话状态，例如：

- 是否已登录
- access token 何时过期
- refresh token 是否可用
- 上次刷新时间
- 最近一次失败原因

## 4. 应支持的认证类型

## 4.1 静态环境变量

适合：

- API key
- bearer token
- basic auth

优点是简单，缺点是缺少生命周期管理。

## 4.2 文件或密钥链存储

适合：

- 长期 token
- refresh token
- CLI 登录态

建议优先接：

- 系统 keyring
- 明确加密的本地文件

## 4.3 OAuth2 / Device Code / Browser Login

这类对于 SaaS API 很重要。

`cts` 不一定第一期全实现，但模型必须预留：

- login
- callback / device verification
- refresh
- revoke

## 4.4 CLI 委托会话

很多 CLI 自己已经做了登录，例如：

- `gh auth login`
- `aws sso login`
- `gcloud auth login`

这时 `cts` 可以把认证委托给 CLI provider，通过：

- 读取状态
- 调用 CLI 登录命令
- 解析 CLI 当前账号与过期时间

## 4.5 MCP 透传认证

某些 MCP server 的登录态不在 `cts` 内，而在 server 自己或其配置中。

这时 `cts` 至少要能表达：

- 当前 server 是否可用
- 是否需要外部完成登录
- 如果失败，如何引导用户去修

## 4.6 Plugin / 自定义协议认证

plugin 应能声明：

- 支持哪些 auth 类型
- 是否支持 bootstrap
- 是否支持 refresh
- 认证状态如何回传

## 5. 会话状态机建议

建议统一状态：

- `unconfigured`
- `configured`
- `login_required`
- `active`
- `expiring`
- `refreshing`
- `expired`
- `failed`
- `revoked`

这样前端和 CLI 都能统一显示状态。

## 6. 生命周期流程

## 6.1 Bootstrap / Login

来源可能是：

- `cts auth login jira-dev`
- 首次执行时按需触发
- provider 自动引导

## 6.2 Validate

执行前检查：

- source 是否有 `auth_ref`
- 对应 auth profile 是否存在
- session 是否可用
- 是否需要刷新

## 6.3 Refresh

建议支持三类 refresh：

- 自动刷新
- 执行失败后重试刷新一次
- 用户手动刷新

## 6.4 Revoke / Logout

要求：

- 清理本地 session
- 如协议支持，通知上游撤销
- 写审计日志

## 7. 配置建议

建议顶层增加：

```yaml
auth_profiles:
  stripe-prod:
    type: bearer
    source: keyring
    keyring_service: cts
    keyring_account: stripe-prod
    refresh:
      enabled: false

  github-oauth:
    type: oauth2
    grant_type: device_code
    session_store: keyring
    refresh:
      enabled: true
      skew_seconds: 300
```

profile 级建议只做“默认引用”，不直接放 secret：

```yaml
profiles:
  dev:
    auth_defaults:
      github: github-oauth
      jira: jira-dev
```

## 8. Provider 侧职责

Provider 建议支持这些能力：

- 识别 auth 要求
- 从 auth resolver 获取已归一化凭证
- 必要时引导 bootstrap
- 支持可选 `refresh_auth()`
- 把鉴权失败归一化成 `AuthError`

不同 provider 的要求：

- HTTP/OpenAPI/GraphQL：注入 header/query/cookie
- CLI：注入 env、profile、credential file
- MCP：调用外部登录/状态检查流程或透传错误
- plugin：遵循统一 auth session 协议

## 9. 建议的命令

- `cts auth list`
- `cts auth status [name]`
- `cts auth login <name>`
- `cts auth refresh <name>`
- `cts auth logout <name>`
- `cts doctor auth`

这些命令还能为前端提供相同 backend 能力。

## 10. 安全与存储要求

默认要求：

- 不把 access token 明文写进共享项目配置
- refresh token 优先走 keyring
- 日志与错误对象里默认脱敏
- `cts explain` 不输出真实凭证

建议区分：

- 声明型配置
- 运行态 session
- 可轮换 secret

不要把三者混在同一个 YAML 里。

## 11. 前端页面需要展示什么

前端控制台建议至少展示：

- 每个 source 绑定的 auth profile
- 当前状态
- 最近刷新时间
- 是否即将过期
- 最近一次错误
- 可执行的动作：login / refresh / logout

前端不应直接读本地 secret，只通过 `cts` backend 获取脱敏状态。

## 12. 日志与审计要求

建议新增事件：

- `auth_resolve_start`
- `auth_resolve_failed`
- `auth_login_start`
- `auth_login_complete`
- `auth_refresh_start`
- `auth_refresh_complete`
- `auth_refresh_failed`
- `auth_logout`

关键字段建议：

- `auth_profile`
- `auth_type`
- `session_state`
- `expires_at`
- `refresh_attempted`
- `refresh_succeeded`

## 13. 对 AI 与自动化系统的特殊要求

AI 或脚本最需要的是“知道能不能调”，而不是拿到 token 本身。

因此建议 `cts explain`、catalog、前端 API 中暴露：

- 是否需要 auth
- 当前 auth 是否就绪
- 是否支持自动刷新
- 如果不就绪，应该调用哪个 login 动作

## 14. 最终建议

认证层不要从“某个 HTTP header 怎么配”出发，而要从“长期会话怎么治理”出发。

这样未来无论接：

- MCP
- 任意 API
- 任意 CLI
- plugin

都能复用统一的 auth profile、session 生命周期和前端状态模型。
