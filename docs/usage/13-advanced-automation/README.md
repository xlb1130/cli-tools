# 高阶实战：自动问题分析、自动需求开发与自动部署

这一篇不是讲“怎么连一个 MCP server”，而是讲怎么把多个 MCP 工具串成一条可持续运行的工程链路：

- 出问题时自动分析
- 需求来了后自动生成开发上下文
- 开发完成后自动部署并验证

如果你还没跑通过单个 MCP source，先看 [MCP Provider](../07-mcp/README.md)。

这一目录下还提供了一组可复用的 skill，方便 AI 按场景使用这些 `cts` 命令：

- 父 skill：[automation-workbench](automation-workbench/SKILL.md)
- 子 skill：[bug-analysis-fix](automation-workbench/bug-analysis-fix/SKILL.md)
- 子 skill：[requirements-development](automation-workbench/requirements-development/SKILL.md)
- 子 skill：[data-query](automation-workbench/data-query/SKILL.md)
- 子 skill：[log-analysis](automation-workbench/log-analysis/SKILL.md)
- 子 skill：[config-check](automation-workbench/config-check/SKILL.md)
- 子 skill：[cache-check](automation-workbench/cache-check/SKILL.md)
- 子 skill：[jvm-diagnosis](automation-workbench/jvm-diagnosis/SKILL.md)
- 子 skill：[release-verify](automation-workbench/release-verify/SKILL.md)
- 子 skill：[yunxiao-task-sync](automation-workbench/yunxiao-task-sync/SKILL.md)
- 子 skill：[dingtalk-notify](automation-workbench/dingtalk-notify/SKILL.md)

---

## 先理解这套组合在解决什么

你给出的这组 MCP，覆盖了研发交付里最常见的几个面：

- `aliyun-sls`：日志检索、错误定位、时间窗口分析
- `mysql`：业务数据核对、异常样本抽取、发布后数据验证
- `redis`：缓存、队列、限流、会话类问题排查
- `nacos`：配置中心、服务注册、环境差异检查
- `jvm-mcp-server`：远程 JVM / Arthas 诊断
- `yunxiao`：需求、任务、研发协作、代码流程联动
- `jenkins-mcp`：构建、部署、回滚、流水线状态检查
- `dingding-bot`：任务完成通知、关键节点播报、异常升级提醒

把它们串起来后，可以形成这样一条闭环：

```text
告警 / 需求
  -> AI 调用 SLS / MySQL / Redis / Nacos / JVM 做事实采集
  -> 输出问题结论或需求上下文
  -> AI 调用 Yunxiao 创建/更新任务
  -> AI 辅助开发与变更说明
  -> AI 调用 Jenkins 部署
  -> AI 再用 SLS / MySQL / Redis / Nacos 做发布后验证
  -> AI 调用 DingTalk Bot 通知相关群组
```

---

## 推荐架构

建议把职责拆成三层：

### 第 1 层：MCP 原生工具层

这一层只负责“能连上工具，并正确执行”。

- `yunxiao`
- `jenkins-mcp`
- `mysql`
- `nacos`
- `aliyun-sls`
- `redis`
- `jvm-mcp-server`
- `dingding-bot`

### 第 2 层：`cts` 统一命令层

这一层把分散的 MCP tools 统一编译成稳定命令，解决三个问题：

- 给工具起稳定入口，不让 AI 每次都临时猜工具名
- 用 mount 把不同 MCP 的能力组织成清晰命令树
- 让 CLI / HTTP / MCP surface 共享同一套能力目录

### 第 3 层：AI Agent 编排层

这一层才是你真正的“自动问题分析 / 自动需求开发 / 自动部署”。

建议按四个 Agent 场景组织：

- `incident-agent`：自动问题分析
- `dev-agent`：自动需求开发辅助
- `release-agent`：自动部署与发布验证
- `notify-agent`：任务完成和关键节点通知

---

## 第一步：准备统一的 `mcp-servers.json`

先把你给出的配置合并成一个文件，例如 `./ops/mcp-servers.json`：

```json
{
  "mcpServers": {
    "yunxiao": {
      "command": "npx",
      "args": ["-y", "alibabacloud-devops-mcp-server"],
      "env": {
        "YUNXIAO_ACCESS_TOKEN": "YUNXIAO_ACCESS_TOKEN"
      }
    },
    "jenkins-mcp": {
      "command": "uvx",
      "args": ["jenkins-mcp"],
      "env": {
        "JENKINS_URL": "https://your-jenkins-server/",
        "JENKINS_USERNAME": "your-username",
        "JENKINS_PASSWORD": "your-password",
        "JENKINS_USE_API_TOKEN": "false"
      }
    },
    "mysql": {
      "command": "npx",
      "args": ["-y", "@f4ww4z/mcp-mysql-server"],
      "env": {
        "MYSQL_HOST": "your_host",
        "MYSQL_USER": "your_user",
        "MYSQL_PASSWORD": "your_password",
        "MYSQL_DATABASE": "your_database"
      }
    },
    "nacos": {
      "type": "stdio",
      "command": "uvx",
      "args": ["jewei-mcp-nacos"],
      "env": {
        "NACOS_HOST": "localhost",
        "NACOS_API_PORT": "8848",
        "NACOS_CONSOLE_PORT": "8080",
        "NACOS_USERNAME": "nacos",
        "NACOS_PASSWORD": "your-password",
        "NACOS_NAMESPACE": "dev",
        "NACOS_VERSION": "3",
        "NACOS_READ_ONLY": "false"
      }
    },
    "aliyun-sls": {
      "command": "npx",
      "args": ["-y", "aliyun-sls-mcp"],
      "env": {
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "your-access-key-id",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your-access-key-secret",
        "SLS_REGIONS": "cn-hangzhou,cn-shenzhen"
      }
    },
    "redis": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-redis", "redis://localhost:6379"]
    },
    "jvm-mcp-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/jvm-mcp-server",
        "run",
        "jvm-mcp-server"
      ],
      "env": {
        "ARTHAS_SSH_HOST": "user@remote-host",
        "ARTHAS_SSH_PORT": "22",
        "ARTHAS_SSH_PASSWORD": "your-password"
      }
    },
    "dingding-bot": {
      "command": "npx",
      "args": ["-y", "mcp-dingding-bot"],
      "env": {
        "DINGTALK_BOT_ACCESS_TOKEN": "<YOUR_ACCESS_TOKEN>",
        "DINGTALK_BOT_SECRET": "<YOUR_SECRET>"
      }
    }
  }
}
```

建议不要把真实密钥直接写入 Git 仓库。更稳妥的做法：

- 配置文件放占位符
- 真正的凭证通过本机环境变量注入
- 至少区分 `dev` / `test` / `prod` 三套连接

---

## 第二步：把多个 MCP source 导进 `cts`

如果你已经有统一的 `mcp-servers.json`，最直接的方式是逐个导入。

```bash
cts import mcp yunxiao --server-name yunxiao --config-file ./ops/mcp-servers.json --under delivery --under demand --apply
cts import mcp jenkins --server-name jenkins-mcp --config-file ./ops/mcp-servers.json --under delivery --under deploy --apply
cts import mcp mysql --server-name mysql --config-file ./ops/mcp-servers.json --under ops --under data --apply
cts import mcp nacos --server-name nacos --config-file ./ops/mcp-servers.json --under ops --under config --apply
cts import mcp sls --server-name aliyun-sls --config-file ./ops/mcp-servers.json --under ops --under logs --apply
cts import mcp redis --server-name redis --config-file ./ops/mcp-servers.json --under ops --under cache --apply
cts import mcp jvm --server-name jvm-mcp-server --config-file ./ops/mcp-servers.json --under ops --under jvm --apply
cts import mcp notify --server-name dingding-bot --config-file ./ops/mcp-servers.json --under delivery --under notify --apply
```

导入后先不要急着让 AI 自动执行，先检查 discovery：

```bash
cts manage source show yunxiao --format json
cts manage source show jenkins --format json
cts manage source show sls --format json

cts manage source test yunxiao --discover --format json
cts manage source test jenkins --discover --format json
cts manage source test sls --discover --format json

cts manage mount list --format json
```

如果某个 source 没发现出 tools，优先检查：

- 本机是否安装了 `node` / `npm` / `uv` / `uvx`
- 对应 MCP server 自己能不能独立启动
- 环境变量是否真实可用
- 网络、白名单、堡垒机、SSH 是否已打通

---

## 第三步：给自动化链路设计命令分组

不要把所有工具直接裸暴露给 AI。更建议先按场景规划路径。

一个比较顺手的分组方式是：

```text
delivery demand ...
delivery deploy ...
ops logs ...
ops data ...
ops cache ...
ops config ...
ops jvm ...
delivery notify ...
```

这样做的好处是：

- AI 更容易根据命令路径判断职责
- 团队成员看 `--help` 时也更容易理解
- 后面如果要对外暴露 HTTP / MCP surface，结构也更整齐

你可以用下面这些命令检查最终命令树：

```bash
cts delivery --help
cts ops --help
cts ops logs --help
cts ops data --help
cts delivery notify --help
```

---

## 第四步：搭四条自动化链路

下面是最常用、也最容易先落地的四条链路。

### 链路 1：自动问题分析

适用场景：

- 线上告警
- 慢 SQL / 大盘异常
- 配置发布后故障
- JVM 内存、线程、连接池问题

推荐工具组合：

- `aliyun-sls` 查日志与异常时间线
- `mysql` 抽取异常订单、用户、任务样本
- `redis` 检查缓存、锁、队列、热点 key
- `nacos` 对比生效配置
- `jvm-mcp-server` 远程做线程栈、内存、类加载、GC 诊断
- `yunxiao` 自动回填问题单
- `dingding-bot` 在定位完成后自动同步结论到群里

推荐执行顺序：

1. 先用 `sls` 锁定报错时间窗口和主异常类型
2. 再用 `mysql` 抽样确认影响范围
3. 再用 `redis` / `nacos` 看是否为缓存或配置问题
4. 如果是 Java 服务，再用 `jvm` 做深入诊断
5. 最后把结论、影响面、建议动作写回 `yunxiao`
6. 如果达到通知条件，再调用 `dingding-bot` 发群通知

适合给 Agent 的执行提示词：

```text
你是 incident-agent。
先收集事实，再下结论。
默认排查顺序：日志 -> 数据 -> 缓存 -> 配置 -> JVM。
输出必须包含：
1. 现象
2. 影响范围
3. 直接证据
4. 根因判断
5. 临时止血建议
6. 长期修复建议
如果证据不足，明确列出还缺什么，不要臆断。
只有在结论、影响范围和建议动作明确后，才发送钉钉通知。
```

### 链路 2：自动需求开发辅助

适用场景：

- 产品提了新需求
- 你要让 AI 先生成研发上下文
- 你要自动创建任务并给出技术拆分

推荐工具组合：

- `yunxiao` 读取需求、缺陷、迭代信息并创建任务
- `mysql` 了解现有数据结构和历史样本
- `nacos` 查看现网配置、开关、环境差异
- `redis` 确认缓存模型和 key 约定
- 必要时用 `aliyun-sls` 补充真实调用轨迹
- `dingding-bot` 在任务创建或方案确认后同步研发群

推荐执行顺序：

1. 从 `yunxiao` 拉取需求描述、关联缺陷、负责人、迭代信息
2. 用 `mysql` / `redis` / `nacos` 补齐现状上下文
3. 让 AI 输出技术方案草稿
4. 回写 `yunxiao` 子任务、风险点、测试点、发布点
5. 在需求进入开发、提测或完成时发送钉钉通知

适合给 Agent 的执行提示词：

```text
你是 dev-agent。
收到需求后先做“现状建模”，不要直接开始写代码。
至少补齐以下内容：
1. 目标与边界
2. 影响服务
3. 影响数据表
4. 影响缓存与配置
5. 接口与兼容性风险
6. 测试点
7. 发布与回滚点
最后再输出建议的开发任务拆分，并同步到 Yunxiao。
在任务状态发生关键变化时，可追加钉钉机器人通知。
```

### 链路 3：自动部署与发布验证

适用场景：

- 合并后自动发版
- 指定需求单自动部署测试环境
- 发布后自动做 smoke check

推荐工具组合：

- `jenkins-mcp` 触发构建、发布、回滚
- `nacos` 检查目标环境配置是否正确
- `aliyun-sls` 验证发布后错误率和关键日志
- `mysql` 验证核心业务数据是否正常写入
- `redis` 验证缓存预热、队列消费、限流状态
- `yunxiao` 自动更新发布状态
- `dingding-bot` 发送开始部署、部署完成、部署失败通知

推荐执行顺序：

1. 发布前先检查 `nacos` 配置和变更单信息
2. 触发 `jenkins` 构建与部署
3. 等待流水线完成后做 `sls` / `mysql` / `redis` 验证
4. 成功则回写 `yunxiao`
5. 失败则自动附带证据并触发回滚流程
6. 在开始、完成、失败、回滚时发钉钉通知

适合给 Agent 的执行提示词：

```text
你是 release-agent。
部署前先做配置检查，部署后必须做验证。
验证至少覆盖：
1. Jenkins 流水线结果
2. 关键错误日志
3. 核心数据写入
4. 缓存 / 队列状态
5. 配置是否符合目标环境
如果验证失败，输出失败证据、影响面和回滚建议。
如果流程到达关键节点，发送简洁明确的钉钉播报。
```

### 链路 4：任务完成后或关键节点自动通知

适用场景：

- 需求单进入开发、提测、上线、完成
- 故障分析完成，需要同步结论
- Jenkins 发布开始、成功、失败、回滚
- 需要在群里自动广播关键事件

推荐工具组合：

- `yunxiao` 提供任务状态和负责人上下文
- `jenkins-mcp` 提供构建与部署状态
- `aliyun-sls` 提供故障证据摘要
- `dingding-bot` 负责向群发送消息

推荐执行顺序：

1. 先判断事件是否达到通知阈值
2. 聚合任务号、环境、结果、负责人、下一步动作
3. 生成简洁通知正文
4. 调用 `dingding-bot` 发送到目标群

建议通知内容至少包含：

- 事件类型
- 任务单号或发布单号
- 当前结果
- 影响环境
- 负责人
- 下一步动作

适合给 Agent 的执行提示词：

```text
你是 notify-agent。
只在任务完成或关键节点时发送钉钉通知，不要为普通中间步骤刷屏。
通知必须简洁，优先包含：
1. 事件类型
2. 任务或发布编号
3. 当前状态
4. 影响环境
5. 负责人
6. 下一步动作
如果事件还不构成通知条件，则跳过发送。
```

---

## 第五步：把“自动化”定义成标准执行模板

无论你是用 Claude Desktop、Cherry Studio、OpenWebUI，还是你自己的 Agent 框架，建议都把任务入口收敛成固定模板。

### 模板 1：自动问题分析

```text
输入：
- 服务名
- 时间范围
- 环境
- 告警现象

动作：
- 查询日志
- 抽取异常样本数据
- 检查缓存与配置
- 必要时执行 JVM 诊断
- 输出根因报告
- 更新 Yunxiao 问题单
```

### 模板 2：自动需求分析

```text
输入：
- 需求单号
- 环境
- 目标发布日期

动作：
- 读取 Yunxiao 需求详情
- 分析相关数据、缓存、配置、日志
- 输出技术方案、任务拆分、测试点、发布点
- 回写 Yunxiao 子任务或评论
```

### 模板 3：自动部署与验证

```text
输入：
- 分支或构建号
- 目标环境
- 发布单号

动作：
- 检查配置
- 触发 Jenkins 发布
- 验证日志、数据、缓存
- 成功则更新发布状态
- 失败则附带证据并建议回滚
```

### 模板 4：任务完成或关键节点通知

```text
输入：
- 事件类型
- 任务号或发布号
- 环境
- 当前状态
- 负责人

动作：
- 判断是否满足通知条件
- 生成简洁通知正文
- 发送钉钉机器人消息
- 记录已通知结果
```

---

## 第六步：一个可直接参考的 `cts.yaml`

如果你希望把这些 source 长期纳入治理，可以落成配置文件。

```yaml
version: 1

sources:
  yunxiao:
    type: mcp
    adapter: mcp-cli
    config_file: ./ops/mcp-servers.json
    server: yunxiao
    discovery:
      mode: live

  jenkins:
    type: mcp
    adapter: mcp-cli
    config_file: ./ops/mcp-servers.json
    server: jenkins-mcp
    discovery:
      mode: live

  mysql:
    type: mcp
    adapter: mcp-cli
    config_file: ./ops/mcp-servers.json
    server: mysql
    discovery:
      mode: live

  nacos:
    type: mcp
    adapter: mcp-cli
    config_file: ./ops/mcp-servers.json
    server: nacos
    discovery:
      mode: live

  sls:
    type: mcp
    adapter: mcp-cli
    config_file: ./ops/mcp-servers.json
    server: aliyun-sls
    discovery:
      mode: live

  redis:
    type: mcp
    adapter: mcp-cli
    config_file: ./ops/mcp-servers.json
    server: redis
    discovery:
      mode: live

  jvm:
    type: mcp
    adapter: mcp-cli
    config_file: ./ops/mcp-servers.json
    server: jvm-mcp-server
    discovery:
      mode: live

  notify:
    type: mcp
    adapter: mcp-cli
    config_file: ./ops/mcp-servers.json
    server: dingding-bot
    discovery:
      mode: live

mounts:
  - id: demand
    source: yunxiao
    select:
      include: ["*"]
    command:
      under: [delivery, demand]

  - id: deploy
    source: jenkins
    select:
      include: ["*"]
    command:
      under: [delivery, deploy]

  - id: data
    source: mysql
    select:
      include: ["*"]
    command:
      under: [ops, data]

  - id: config
    source: nacos
    select:
      include: ["*"]
    command:
      under: [ops, config]

  - id: logs
    source: sls
    select:
      include: ["*"]
    command:
      under: [ops, logs]

  - id: cache
    source: redis
    select:
      include: ["*"]
    command:
      under: [ops, cache]

  - id: jvm
    source: jvm
    select:
      include: ["*"]
    command:
      under: [ops, jvm]

  - id: notify
    source: notify
    select:
      include: ["*"]
    command:
      under: [delivery, notify]
```

使用时：

```bash
cts --config ./ops/cts.yaml manage source test sls --discover --format json
cts --config ./ops/cts.yaml manage mount list --format json
cts --config ./ops/cts.yaml delivery --help
cts --config ./ops/cts.yaml ops --help
cts --config ./ops/cts.yaml delivery notify --help
```

---

## 第七步：上线前的边界控制

这一步非常重要。自动化越强，越要限制权限边界。

建议至少做到：

- `prod` 环境的 `nacos` 默认只读
- `mysql` 只给查询账号，不给写权限
- `redis` 优先只读或限制危险命令
- `jenkins` 只开放指定 Job，不开放全局管理权限
- `jvm-mcp-server` 只允许指定机器、指定账号
- `dingding-bot` 只允许发到指定群，避免误发
- 发布类动作增加“二次确认”或“仅指定环境可执行”

如果你要让 AI 直接部署生产，建议再加两层保护：

- 只有 `release-agent` 能调用部署工具
- 只有 `notify-agent` 或指定场景 Agent 能调用通知工具
- 发布前必须先输出 `explain` 风格的执行计划，人工确认后再执行

---

## 一条最小可跑通的落地顺序

如果你想最快验证价值，不要一开始就接全套，建议按这个顺序：

1. 先接 `aliyun-sls + mysql + nacos`
2. 跑通“自动问题分析”
3. 再接 `yunxiao`
4. 跑通“自动生成问题单 / 需求任务”
5. 最后接 `jenkins + redis + jvm-mcp-server`
6. 再做“自动部署与发布验证”

这是因为：

- 自动分析最容易先看到价值
- 自动部署的风险最高，应该最后接
- `jvm` 和 `redis` 虽然强，但通常不是第一阶段刚需

---

## 常见排查建议

### `cts import mcp` 成功，但没有发现任何 tool

先看：

```bash
cts manage source test <source> --discover --format json
cts manage source show <source> --format json
```

重点排查：

- `server-name` 是否和 `mcp-servers.json` 一致
- `config_file` 路径是否正确
- 对应 MCP server 是否本机可启动
- Node / uv 依赖是否安装

### AI 会用工具，但不会按正确顺序排查

这通常不是工具问题，而是编排问题。优先补：

- 固定的场景提示词
- 固定的输出模板
- 固定的工具调用顺序
- 固定的通知触发条件

### 工具太多，AI 选择混乱

优先做两件事：

- 用 `cts` 重新组织 mount 路径
- 只把某个场景真正需要的那部分工具暴露给对应 Agent

---

## 总结

这套 MCP 组合很适合做“研运一体”的自动化闭环：

- `SLS / MySQL / Redis / Nacos / JVM` 负责事实采集与诊断
- `Yunxiao` 负责需求、任务、协作回写
- `Jenkins` 负责构建、部署、回滚
- `DingTalk Bot` 负责任务完成和关键节点通知
- `cts` 负责把零散工具编译成稳定命令入口

最推荐的落地方式不是“一次接满”，而是：

1. 先做自动问题分析
2. 再做自动需求开发辅助
3. 最后做自动部署与发布验证

这样风险最小，也最容易让团队快速看到收益。
