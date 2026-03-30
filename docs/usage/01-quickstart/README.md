# Quickstart

**目标**：30 秒内跑通，不需要任何配置文件。

---

## 最快路径

```bash
# 1. 安装
pip install cts

# 2. 导入一个命令（无需配置文件）
cts import cli hello --exec "echo Hello, World!" --apply

# 3. 执行
cts hello
# 输出: Hello, World!
```

完成。不需要配置文件，不需要 manifest。

---

## 还能做什么

```bash
# 导入 MCP Server（同样无需配置文件）
cts import mcp my-mcp --server-config '{"type":"sse","url":"https://mcp.api-inference.modelscope.net/6d85ac1213db43/sse"}' --apply
cts my-mcp <tool-name> --param value

# 看看当前挂载了什么
cts mount list

# 用稳定 ID 调用
cts invoke hello

# 预览执行计划
cts explain hello
```

---

## 下一步

- 想导入更复杂的 CLI：[本地 CLI](../02-local-cli/README.md)
- 想用配置文件管理多个命令：查看 examples/
- 想理解 mount 命名规则：[Mount 设计](../08-mounts/README.md)