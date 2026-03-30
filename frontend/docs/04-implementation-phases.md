# 分阶段实施

## 1. 第一阶段目标

先把前端做成一个只读控制台。

必须完成：

- 独立前端目录
- 本地 HTTP API
- Dashboard
- Sources 列表
- Mounts 列表
- Mount 详情页
- Catalog 导出入口

## 2. 推荐实现顺序

### Step 1：补后端 API

先在 Python 侧补这些接口：

- `GET /api/app/summary`
- `GET /api/sources`
- `GET /api/mounts`
- `GET /api/mounts/{id}`
- `GET /api/catalog`

### Step 2：定义前端类型

根据 API 定义：

- `AppSummary`
- `SourceSummary`
- `MountSummary`
- `MountDetail`
- `CapabilityCard`

### Step 3：搭页面壳

先做：

- 布局
- 路由
- 顶部状态条
- 左侧导航或顶部导航

### Step 4：先做 Mounts 页面

这是最有价值的页面，应优先实现。

### Step 5：补 Dashboard 和 Sources

把整体感补齐。

### Step 6：补详情页和 explain

让页面从“目录”升级到“可理解能力”。

## 3. 推荐阶段划分

### Phase A：只读 MVP

- 读配置
- 展示 sources
- 展示 mounts
- 支持搜索和筛选
- 支持复制命令

### Phase B：可解释

- mount 详情页
- explain 面板
- capability card 展示
- schema viewer

### Phase C：轻交互

- reload
- sync
- profile 切换展示

### Phase D：执行与管理

只有当安全边界明确后，再考虑：

- 执行只读命令
- 执行 explain
- 启停某些 surface

## 4. 推荐与核心 `cts` 的集成方式

长期建议最终提供：

```bash
cts manage ui
```

内部行为：

1. 加载配置
2. 启动本地 API
3. 托管前端静态资源
4. 打开浏览器

当前仓库已经可用的方式是：

```bash
cts manage serve http --ui
```

前端开发联调时也可以使用：

```bash
cts manage serve http
pnpm dev
```

## 5. 风险点

### 风险 1：前端重复实现配置逻辑

应对：

- 前端不解析配置文件
- 一律走后端归一化接口

### 风险 2：一上来就做执行按钮

应对：

- 第一版只读
- 执行能力后置

### 风险 3：页面只做人类视图，不做机器视图

应对：

- 列表和详情页同时展示 `mount.id`、`stable_name`、surface、schema

## 6. 最终建议

这套前端最好被理解为：

- `cts` 的本地可视化控制台
- 基于 `serve http` 的北向页面
- 展示配置、能力目录和命令合同

不是另起一套系统，也不是把核心逻辑搬进浏览器。
