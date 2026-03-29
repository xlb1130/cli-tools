# cts 前端控制台方案

这个目录用于承载 `cts` 的独立前端页面方案与实现。它的目标不是替代 CLI，而是给 `cts` 提供一个本地可视化控制台，用来展示：

- 已加载的配置文件
- 已注册的 `source`
- 已挂载的 `mount`
- 已生成的命令路径
- 稳定机器调用入口
- 风险级别、可见 surface、schema、示例

这套前端的核心定位是：

- 面向人类的可视化控制台
- 基于本地 `cts` 进程提供的数据接口
- 与 CLI、`invoke`、MCP bridge、HTTP gateway 共存

## 关键结论

前端页面**不应该直接读取本地配置文件路径**。更合理的架构是：

1. `cts` 启动一个本地 HTTP 服务
2. 本地服务读取配置文件、discovery cache、catalog
3. 前端页面通过 API 获取结构化数据并展示

原因：

- 浏览器直接读取本地文件受安全限制
- 统一通过 `cts` 后端读取，才能复用同一套配置解析、profile 合并、discovery、policy 和 catalog 逻辑
- 后续要接入 Electron/Tauri、浏览器、远程 UI 时，接口层也能复用

## 建议目录结构

```text
frontend/
  README.md
  app/
    package.json
    src/
  docs/
    01-frontend-overview.md
    02-ui-architecture.md
    03-api-contract.md
    04-implementation-phases.md
  mock/
    catalog-summary.json
```

## 推荐技术栈

建议前端独立使用：

- React
- TypeScript
- Vite
- TanStack Router 或 React Router
- TanStack Query
- Zod
- 一个轻量 UI 层，第一版不必上重型设计系统

原因：

- 启动快，独立目录实现简单
- 类型契约清晰，适合和 Python 后端 API 对接
- 未来可嵌进桌面壳或本地管理页

## 建议的启动方式

当前已经支持两种方式。

开发模式：

```bash
cts --config <your-config> serve http
cd frontend/app
npm install
npm run dev
```

默认 Vite 会把 `/api` 代理到 `http://127.0.0.1:8787`。如果后端不是这个地址，可设置：

```bash
VITE_CTS_API_TARGET=http://127.0.0.1:9000 npm run dev
```

构建后由 `cts` 托管静态页面：

```bash
cd frontend/app
npm run build

cts --config <your-config> serve http --ui
```

也支持显式指定静态目录：

```bash
cts --config <your-config> serve http --ui-dir frontend/app/dist
```

执行后：

- Python 后端读取配置与 catalog
- 启动本地 API
- 如果传入 `--ui` 或 `--ui-dir`，同时托管前端静态资源
- 浏览器打开本地页面

## 文档索引

- [前端总览](docs/01-frontend-overview.md)
- [UI 架构与数据流](docs/02-ui-architecture.md)
- [API 契约](docs/03-api-contract.md)
- [分阶段实施](docs/04-implementation-phases.md)
