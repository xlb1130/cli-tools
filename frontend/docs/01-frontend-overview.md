# 前端总览

## 1. 目标

`cts` 前端页面的目标是提供一个本地可视化控制台，让用户不用先记住所有命令，就能理解当前系统里“已经接进来了什么、暴露成了什么命令、能不能给 AI 用、风险多大”。

第一版页面建议聚焦以下几个问题：

- 当前加载的是哪些配置文件
- 当前 profile 是什么
- 有哪些 source
- 有哪些 mount
- 每个 mount 对应的人类命令路径是什么
- 每个 mount 对应的稳定机器入口是什么
- 哪些命令可以通过 MCP / HTTP / invoke 暴露
- 哪些是高风险命令
- 最近一次配置加载、sync 和执行发生了什么

## 2. 非目标

第一版页面不建议做：

- 在线编辑复杂配置文件
- 完整命令执行终端
- 替代 CLI 的所有高级操作
- 实时日志中心
- 权限系统后台

第一版优先做“看得清、查得到、能定位”。

## 3. 页面范围

建议先做一个单页应用，但包含多个视图。

### 3.1 Dashboard

展示全局摘要：

- 配置文件路径
- 当前 profile
- source 总数
- mount 总数
- CLI 路径总数
- 允许暴露给 AI 的 mount 数量
- 高风险命令数量
- 最近一次 sync 时间
- 最近一次 config reload 状态
- 最近一次执行摘要

### 3.2 Sources 页面

按卡片或表格展示：

- source 名称
- 类型
- provider
- profile_scope
- discovery 模式
- expose_to_surfaces
- 健康状态

### 3.3 Mounts 页面

这是最重要的页面。

每条 mount 至少展示：

- `mount.id`
- `machine.stable_name`
- 命令路径
- source
- operation
- risk
- expose_via
- 是否需要确认
- 示例输入
- 动态 `--help` 预览入口

### 3.4 Mount 详情页

点击某条 mount 后展示：

- 基本信息
- 输入 schema
- 输出 schema
- capability card
- 渲染后的 `--help`
- explain 示例
- 人类命令调用示例
- `cts manage invoke` 示例
- 是否能通过 MCP / HTTP 暴露

### 3.5 Catalog 页面

提供机器视角总览：

- capability card 列表
- 过滤与搜索
- 导出 JSON

### 3.6 Extensions 页面

这一页专门服务于 plugin/provider/hook 的 northbound 调试。

建议展示：

- 已加载 plugin 列表
- 每个 plugin 注册了哪些 provider type
- 每个 plugin 暴露了哪些 hook handler
- hook 绑定到了哪些 lifecycle event
- 每个 lifecycle event 的 payload contract
- provider conflict 当前如何处理
- 最近一次 hook dispatch / hook failure 时间线
- 时间线过滤与继续加载更早事件
- hook `when` 条件的命中解释
- 一个轻量的 Hook Lab，可直接 explain / simulate
- Hook Lab 支持加载官方 sample payload
- Hook Lab 支持保存并复用本地调试场景
- 页面会显示 simulate 的风险边界和限制说明

这页的价值不是“展示配置”，而是回答：

- 扩展到底有没有被真正加载
- provider 最终归谁拥有
- hook 的 priority / fail_mode / when 到底怎么生效
- 最近一次调试事件发生在什么 mount / source 上

## 4. 用户操作

第一版建议支持这些操作：

- 搜索 source / mount / stable name
- 按风险等级筛选
- 按 source 类型筛选
- 按 surface 筛选
- 展开 schema
- 复制命令示例
- 手动触发 refresh / sync

第二版再考虑：

- 从页面触发 explain
- 从页面执行只读命令
- 从页面启停某个 surface
- 日志页面

## 5. 推荐页面信息层级

每个 mount 建议同时展示三层信息：

### 第一层：快速识别

- 名字
- 路径
- 风险
- 来源

### 第二层：机器合同

- `mount.id`
- `stable_name`
- `input_schema`
- `supported_surfaces`

### 第三层：运行信息

- 最近同步时间
- provider 状态
- explain 示例
- policy 限制

## 6. 最重要的产品原则

### 6.1 人类视角和机器视角同时存在

页面不能只显示“命令长什么样”，也要显示“机器应该怎么调”。

### 6.2 只读优先

第一版页面以只读为主，更安全，也更容易落地。

### 6.3 页面只是控制台，不是第二套核心逻辑

配置解析、catalog 生成、policy 判断、schema 归一化都必须由后端 `cts` 服务完成，前端只消费结构化结果。
