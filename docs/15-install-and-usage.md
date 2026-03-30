# cts 安装与使用指南

本文把 `cts` 的使用方式分成两类：

- 普通用户：不关心源码，只想把 `cts` 安装到电脑上然后直接使用
- 开发者：需要拉取仓库、修改代码、运行测试或构建 UI

如果你的目标是“像普通软件一样安装并使用”，请优先看“普通用户安装”与“UI 使用”两节。

## 1. cts 是什么

`cts` 是一个统一能力入口工具，用来把 HTTP、CLI、OpenAPI、GraphQL、MCP 等不同来源的能力，编译成稳定的命令路径和统一调用入口。

核心模型：

```text
source -> operation -> mount -> command/surface
```

- `source`：能力来源
- `operation`：某个来源里的具体操作
- `mount`：给操作绑定稳定 ID 和命令路径
- `surface`：对外使用方式，例如 CLI、HTTP、UI

## 2. 先说结论

这份仓库目前已经具备：

- Python CLI 安装与运行能力
- 本地 HTTP 服务能力
- 前端 UI 开发模式
- 前端 UI 静态构建后托管能力

但从“真正普通用户安装”的角度看，还要区分两种情况：

### 2.1 如果维护方已经发布安装包

这是普通用户最合适的安装方式。推荐直接安装发布好的包，而不是下载源码。

可接受的发布形态包括：

- PyPI 包
- 公司内部 Python 包仓库
- GitHub Release 附带的 `.whl` 文件
- 预装 `cts` 的桌面包或系统包

### 2.2 如果维护方还没有发布安装包

那就还不能算“真正面向普通用户的一键安装”。这时只能走：

- 从源码安装
- 或者由维护方先构建 wheel，再分发给用户

当前这个仓库能完整支持“源码安装”和“wheel 分发安装”，但文档不能把这两种方式混成“普通用户安装”。

## 3. 普通用户安装

这一节面向“不下载源码”的真实用户。

### 3.1 推荐方式：安装已发布的包

如果 `cts` 已经发布到 PyPI 或内部源，推荐优先使用 `pipx`：

```bash
pipx install cts
```

如果使用公司内部源，通常形态类似：

```bash
pipx install --index-url <your-index-url> cts
```

如果没有 `pipx`，也可以使用用户级安装：

```bash
python3 -m pip install --user cts
```

安装完成后验证：

```bash
cts --help
cts --version
```

### 3.2 从已发布的 wheel 安装

如果维护方提供的是一个发布好的 `.whl` 文件，也属于普通用户安装方式，因为你不需要下载源码仓库。

示例：

```bash
python3 -m pip install --user ./cts-0.1.0-py3-none-any.whl
```

或者：

```bash
python3 -m pip install --user https://example.com/releases/cts-0.1.0-py3-none-any.whl
```

安装完成后验证：

```bash
cts --help
```

### 3.3 macOS / zsh 下 PATH 说明

如果你使用的是：

```bash
python3 -m pip install --user ...
```

那么可执行文件通常会安装到：

```text
~/Library/Python/3.9/bin
```

或类似版本目录。

如果执行 `cts --help` 提示找不到命令，需要把这个目录加入 `PATH`，例如写入 `~/.zprofile`：

```bash
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
```

然后重新打开终端，或者执行：

```bash
source ~/.zprofile
```

### 3.4 当前仓库状态说明

截至当前仓库状态，这个项目更偏向“源码仓库 + 本地运行”形态。也就是说：

- 开发者安装流程是完整的
- 普通用户安装流程只有在“已经发布包”或“已经提供 wheel”时才成立

如果你要把它交付给真正终端用户，建议维护方至少提供下面任意一种：

1. 发布到 PyPI
2. 发布 wheel 到 Release 页面
3. 提供 `pipx install <package>` 的官方安装方式
4. 提供桌面安装包或系统包

## 4. UI 使用

之前文档缺少这一部分，这里补全。

`cts` 的 UI 不是单独读取本地 YAML 文件，而是基于本地 `cts` HTTP 服务读取数据。也就是说，UI 依赖后端服务。

UI 主要用来查看：

- 已加载配置
- source 列表
- mount 列表
- catalog 信息
- 风险级别、surface、schema、示例

### 4.1 UI 的两种使用方式

#### 方式 A：开发模式

适合前端开发或本地联调。

先启动后端：

```bash
cts --config <your-config> serve http
```

再启动前端开发服务器：

```bash
cd frontend/app
npm install
npm run dev
```

如果后端不是默认地址 `http://127.0.0.1:8787`，可以这样启动前端：

```bash
VITE_CTS_API_TARGET=http://127.0.0.1:9000 npm run dev
```

然后在浏览器打开 Vite 输出的本地地址。

#### 方式 B：本地托管已构建 UI

适合演示、本地使用或交付。

先构建前端：

```bash
cd frontend/app
npm install
npm run build
```

构建产物默认会输出到 `src/cts/ui_dist`，这样在打包 Python wheel 时可以一起带上。

然后让 `cts` 同时提供 API 和 UI：

```bash
cts --config <your-config> serve http --ui
```

如果希望启动后自动打开浏览器：

```bash
cts --config <your-config> serve http --ui --open
```

如果静态目录不在默认位置，可显式指定：

```bash
cts --config <your-config> serve http --ui-dir src/cts/ui_dist
```

启动后，`cts` 会输出一个 JSON，其中包含：

- `base_url`
- `browser_url`
- `ui_enabled`
- `ui_dir`

浏览器打开 `browser_url` 即可进入 UI；如果使用了 `--open`，会自动打开默认浏览器。

### 4.2 UI 的当前定位

当前 UI 更适合：

- 本地控制台
- 配置可视化
- catalog 浏览
- mount/source 检查

它不是替代 CLI，而是对 CLI 的补充。

### 4.3 UI 相关文件

- 前端说明：[frontend/README.md](/Users/xielingbo/Documents/Project/python/cli-tools/frontend/README.md)
- 前端应用目录：[frontend/app](/Users/xielingbo/Documents/Project/python/cli-tools/frontend/app)

## 5. 基本使用

### 5.1 查看帮助

```bash
cts --help
cts --version
```

### 5.2 配置检查

```bash
cts --config cts.yaml config paths
cts --config cts.yaml config build --format yaml
cts --config cts.yaml config lint --format json
cts --config cts.yaml config lint --compile --format json
```

### 5.3 source 管理

```bash
cts --config cts.yaml source add http jira \
  --base-url https://jira.example.com \
  --format json
```

```bash
cts --config cts.yaml source list
cts --config cts.yaml source show jira --format json
cts --config cts.yaml source test jira --format json
cts --config cts.yaml source remove jira --format json
```

### 5.4 mount 管理

```bash
cts --config cts.yaml mount add jira get_issue \
  --id jira-get-issue \
  --path "ops jira issue get" \
  --summary "Get issue" \
  --param "key:string" \
  --required key \
  --format json
```

```bash
cts --config cts.yaml mount list
cts --config cts.yaml mount show jira-get-issue --format json
cts --config cts.yaml mount remove jira-get-issue --format json
```

### 5.5 调用 mount

动态命令调用：

```bash
cts --config cts.yaml ops jira issue get --key PROJ-123 --output json
```

通过稳定 ID 调用：

```bash
cts --config cts.yaml invoke jira-get-issue \
  --input-json '{"key":"PROJ-123"}' \
  --format json
```

查看执行计划：

```bash
cts --config cts.yaml explain jira-get-issue \
  --input-json '{"key":"PROJ-123"}' \
  --format json
```

说明：这一组 `jira` 命令是否真的能执行成功，取决于对应 source 是否已正确接好底层服务。

## 6. 额外可用命令

当前 CLI 还包含以下命令族：

```bash
cts catalog export --format json
cts doctor --format json
cts inspect source <name> --format json
cts inspect mount <id> --format json
cts runs list --format json
cts completion --help
cts docs --help
cts workflow --help
```

其中：

- `docs`：可根据 CTS 配置生成文档
- `workflow`：用于列出和执行 workflow

## 7. 快速体验 demo

仓库里有一个现成 demo：

- 配置文件：[examples/demo/cts.yaml](/Users/xielingbo/Documents/Project/python/cli-tools/examples/demo/cts.yaml)
- manifest：[examples/demo/echo-manifest.yaml](/Users/xielingbo/Documents/Project/python/cli-tools/examples/demo/echo-manifest.yaml)

如果你是开发者，或者已经把这个仓库安装到了本地，可以直接运行：

```bash
cts --config examples/demo/cts.yaml config lint --compile --format json
cts --config examples/demo/cts.yaml demo echo --help
cts --config examples/demo/cts.yaml demo echo --text hello --upper --output json
cts --config examples/demo/cts.yaml invoke demo-echo --input-json '{"text":"hello","upper":true}' --format json
```

## 8. 开发者从源码安装

这一节是开发者安装方式，不属于“普通用户安装”。

### 8.1 Python 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

也可以不做安装，直接在仓库里运行：

```bash
PYTHONPATH=src python3 -m cts.main --help
```

### 8.2 运行测试

```bash
pytest
```

或：

```bash
pytest tests/test_demo_cli.py
pytest tests/test_cli_management.py
```

### 8.3 前端开发

```bash
cts --config examples/demo/cts.yaml serve http
cd frontend/app
npm install
npm run dev
```

### 8.4 前端构建

```bash
cd frontend/app
npm install
npm run build
cts --config examples/demo/cts.yaml serve http --ui --open
```

## 9. 相关文档

- 架构总览：[docs/00-rfc-master-architecture.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/00-rfc-master-architecture.md)
- 平台总览：[docs/01-platform-overview.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/01-platform-overview.md)
- 配置模型：[docs/02-config-model.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/02-config-model.md)
- Provider SDK：[docs/03-provider-sdk.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/03-provider-sdk.md)
- 运行时设计：[docs/04-runtime-execution.md](/Users/xielingbo/Documents/Project/python/cli-tools/docs/04-runtime-execution.md)
- 前端说明：[frontend/README.md](/Users/xielingbo/Documents/Project/python/cli-tools/frontend/README.md)
