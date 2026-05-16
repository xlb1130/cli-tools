# 路径约定

## 目标

统一目录布局，降低排查和迁移成本。

## 推荐路径

- `~/.cts/automation-workbench/`：工作台主目录。
- `~/.cts/common/`：可跨 skill 复用的公共资产。
- `~/.config/mcp/mcp_servers.json`：mcp-cli 配置。
- `~/.cts/automation-workbench/docs/`：分发后的自有文档。
- `~/.cts/common/docs/`：分发后的通用文档。
- `~/.cts/common/scripts/`：分发后的公共脚本。

## 命名原则

- 路径表达用途，不表达临时实现细节。
- 目录名保持稳定，便于脚本和文档引用。
- 临时产物和长期资产分开。
