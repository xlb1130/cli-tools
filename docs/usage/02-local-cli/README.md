# 本地 CLI Provider

导入和挂载本地命令行工具。

---

## 三种方式，从简单到复杂

### 方式 1：一行命令导入（最简单）

适合：快速试一个命令，不想写配置文件。

```bash
cts import cli mycmd --exec "echo hello" --apply
cts mycmd
```

---

### 方式 2：配置文件 + 内联操作定义

适合：管理多个命令，希望配置清晰。

```yaml
# cts.yaml
version: 1
sources:
  mycli:
    type: cli
    operations:
      greet:
        input_schema:
          type: object
          properties:
            name: { type: string }
        provider_config:
          argv_template: ["echo", "Hello, {name}!"]

mounts:
  - id: mycli-greet
    source: mycli
    operation: greet
    command: { path: [mycli, greet] }
```

```bash
cts --config cts.yaml mycli greet --name World
```

---

### 方式 3：配置文件 + 独立 Manifest（最灵活）

适合：复杂项目，需要管理大量操作。

配置文件：

```yaml
# cts.yaml
version: 1
sources:
  mycli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
      manifest: ./operations.yaml

mounts:
  - id: mycli-greet
    source: mycli
    operation: greet
    command: { path: [mycli, greet] }
```

Manifest 文件：

```yaml
# operations.yaml
version: 1
operations:
  - id: greet
    title: Greeting
    input_schema:
      type: object
      properties:
        name: { type: string }
    argv_template: ["echo", "Hello, {name}!"]
    output:
      mode: text
```

```bash
cts --config cts.yaml mycli greet --name World
```

---

## 如何选择

| 场景 | 推荐方式 |
|------|----------|
| 快速试一个命令 | 方式 1：一行命令导入 |
| 管理 2-5 个命令 | 方式 2：配置文件 + 内联 |
| 管理 10+ 个命令 | 方式 3：独立 Manifest |
| 团队共享配置 | 方式 3：独立 Manifest |

---

## 常用参数

```bash
# 预览不应用
cts import cli mycmd --exec "..." --format json

# 查看生成的配置
cts --config cts.yaml config build

# 检查配置有效性
cts --config cts.yaml config lint
```

---

## 相关链接

- [完整示例](./examples/)
- [Mount 设计](../08-mounts/README.md)
- [执行方式](../09-execution/README.md)