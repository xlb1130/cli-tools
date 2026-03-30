# Quickstart

**目标**：5 分钟内理解 `cts` 最核心的运行模型，不先陷进 provider 细节。

---

## 第一步：先导入一个本地 shell 命令

这是当前最快的起点，不需要你先手写配置文件。

```bash
cts import shell hello --exec 'echo Hello cts!' --apply
cts hello
```

你会得到一个已经编译好的本地命令。

再看一下帮助：

```bash
cts hello --help
```

这时候你已经实际见到了：

- `source`: `hello`
- `operation`: `run`
- `mount`: `hello`
- `command path`: `hello`

---

## 第二步：看执行计划

```bash
cts explain hello
```

这一步的目的是建立一个直觉：

- `cts` 不是简单转发命令
- 它先把能力编译成统一模型，再决定怎么执行

---

## 第三步：看 source 和 mount

```bash
cts manage source show hello --format json
cts manage mount list --format json
```

如果你能看懂这两条命令的输出，就已经可以进入下一阶段了。

---

## 第四步：开始导入你自己的能力

接下来按你的场景继续：

- 接已有 CLI：看 [本地 CLI](../02-local-cli/README.md)
- 接 shell 脚本：看 [Shell 脚本](../03-shell/README.md)
- 接 MCP：看 [MCP Server](../07-mcp/README.md)
- 想理解命名和路径：看 [Mount 设计](../08-mounts/README.md)

---

## 你现在应该记住什么

只记这条就够了：

```text
source -> operation -> mount -> surface
```

以及两类最常见命令：

```bash
# 执行业务命令
cts <path...> [args]

# 看内部编译结果
cts manage ...
cts explain ...
```
