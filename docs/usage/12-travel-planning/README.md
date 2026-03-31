# 高阶实战：行程规划

这一篇是另一个高阶场景，不是研发自动化，而是把多个 MCP 工具组合成一套“出行规划助手”：

- 用高德 MCP 做地点检索、路线规划、城市内通勤判断
- 用 12306 MCP 做车次、余票、换乘方案查询
- 用必应搜索 MCP 补充景点、天气、营业时间、攻略信息

如果你还没跑通过单个 MCP source，先看 [MCP Provider](../07-mcp/README.md)。

这一目录下还提供了一组可复用的 skill：

- 父 skill：[travel-planner](travel-planner/SKILL.md)
- 子 skill：[city-route-planning](travel-planner/city-route-planning/SKILL.md)
- 子 skill：[rail-trip-planning](travel-planner/rail-trip-planning/SKILL.md)
- 子 skill：[travel-web-research](travel-planner/travel-web-research/SKILL.md)
- 子 skill：[itinerary-synthesis](travel-planner/itinerary-synthesis/SKILL.md)

---

## 这套组合在解决什么

单独使用地图、铁路、搜索都能回答一部分问题，但行程规划通常需要把它们串起来：

```text
用户目标
  -> 高德 MCP 判断城市内地点、距离、通勤时长
  -> 12306 MCP 查询跨城车次、出发时间、换乘成本
  -> 必应搜索 MCP 补充景点信息、开放时间、注意事项
  -> AI 汇总成可执行行程
```

适合场景：

- 周末短途出行
- 跨城高铁+地铁接驳
- 多景点一日游
- 商务出差路线规划

---

## 推荐架构

建议拆成三层：

### 第 1 层：MCP 工具层

- 高德 MCP
- 12306 MCP
- Bing Search MCP

### 第 2 层：`cts` 命令层

把这些 MCP 编译成稳定命令路径，例如：

- `cts travel map ...`
- `cts travel rail ...`
- `cts travel search ...`

### 第 3 层：AI 行程编排层

由 `travel-planner` skill 负责：

- 先明确出发地、目的地、时间、预算、偏好
- 先做交通可行性判断
- 再做景点和活动筛选
- 最后产出结构化行程方案

---

## 统一 `mcp-servers.json` 示例

下面的服务名和命令请按你自己的实际 MCP server 调整。这里给的是推荐命名方式。

```json
{
  "mcpServers": {
    "gaode-mcp": {
      "command": "npx",
      "args": ["-y", "your-gaode-mcp-server"],
      "env": {
        "AMAP_API_KEY": "your-amap-api-key"
      }
    },
    "cn12306-mcp": {
      "command": "npx",
      "args": ["-y", "your-12306-mcp-server"]
    },
    "bing-cn-mcp-server": {
      "command": "npx",
      "args": ["-y", "@zhw2590582/bing-cn-mcp-server"]
    }
  }
}
```

如果你已经有 Bing 的例子，可以参考：

- [examples/mcp/bing-mcp-servers.json](../../examples/mcp/bing-mcp-servers.json)
- [examples/mcp/bing-cts.yaml](../../examples/mcp/bing-cts.yaml)

---

## 导入到 `cts`

```bash
cts import mcp map --server-name gaode-mcp --config-file ./travel/mcp-servers.json --under travel --under map --apply
cts import mcp rail --server-name cn12306-mcp --config-file ./travel/mcp-servers.json --under travel --under rail --apply
cts import mcp search --server-name bing-cn-mcp-server --config-file ./travel/mcp-servers.json --under travel --under search --apply
```

检查 discovery：

```bash
cts manage source test map --discover --format json
cts manage source test rail --discover --format json
cts manage source test search --discover --format json
cts travel --help
```

---

## 推荐行程规划流程

### 场景 1：跨城周末出游

1. 先用 `rail` 查询候选车次、出发时间、时长和换乘复杂度
2. 再用 `map` 判断到站后去酒店、景点、商圈的通勤成本
3. 再用 `search` 补充景点热度、开放时间、闭馆日、天气和攻略
4. 最后输出推荐方案、备选方案和注意事项

### 场景 2：商务出差

1. 用 `rail` 查最稳妥的到达方案
2. 用 `map` 规划车站到客户地、酒店、机场或会议点的路线
3. 用 `search` 查附近餐饮、酒店评价、交通管制、天气
4. 输出按时间顺序的执行路线

### 场景 3：一日游规划

1. 用 `map` 先估算景点间移动成本
2. 用 `search` 查询景点开放时间和热门时段
3. 如果涉及跨城，再补 `rail`
4. 输出“上午 / 下午 / 晚上”的节奏化行程

---

## 一份可参考的 `cts.yaml`

```yaml
version: 1

sources:
  map:
    type: mcp
    adapter: mcp-cli
    config_file: ./travel/mcp-servers.json
    server: gaode-mcp
    discovery:
      mode: live

  rail:
    type: mcp
    adapter: mcp-cli
    config_file: ./travel/mcp-servers.json
    server: cn12306-mcp
    discovery:
      mode: live

  search:
    type: mcp
    adapter: mcp-cli
    config_file: ./travel/mcp-servers.json
    server: bing-cn-mcp-server
    discovery:
      mode: live

mounts:
  - id: travel-map
    source: map
    select:
      include: ["*"]
    command:
      under: [travel, map]

  - id: travel-rail
    source: rail
    select:
      include: ["*"]
    command:
      under: [travel, rail]

  - id: travel-search
    source: search
    select:
      include: ["*"]
    command:
      under: [travel, search]
```

---

## 产出建议

让 AI 输出行程时，建议固定成这几个部分：

- 行程目标
- 核心约束
- 推荐路线
- 备选路线
- 时间安排
- 费用估算
- 风险与提醒

---

## 边界控制

- 先确认日期、城市、人数、预算，不要直接开始规划
- 票务和营业时间可能变化，优先提示“请以实时结果为准”
- 搜索结果用于补充，不要让攻略内容覆盖实时交通事实
- 如果地图、铁路、搜索结果冲突，优先以实时交通工具查询结果为准
