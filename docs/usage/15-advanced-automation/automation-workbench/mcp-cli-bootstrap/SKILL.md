---
name: mcp-cli-bootstrap
description: Use when the user needs to install, verify, or troubleshoot mcp-cli usage, including node checks, command style verification, config bootstrap, and connectivity smoke checks.
---

# MCP CLI 安装与使用

## When To Use

- 首次准备 `mcp-cli`
- `mcp-cli` 版本或命令风格不明确
- 需要校验配置文件与 server 是否可用

## Preconditions

- `app-context-init` should own the target config and default server aliases.

## Inputs

- node environment
- target `mcp_servers.json`
- target server name

## Workflow

1. Check `node`, `npm`, `npx`, and `mcp-cli`.
2. Verify that `~/.config/mcp/mcp_servers.json` exists and is readable.
3. Validate the local CLI patterns:
   - `mcp-cli`
   - `mcp-cli info <server>`
   - `mcp-cli grep <pattern>`
   - `mcp-cli call <server> <tool> <json>`
4. Run a minimal connectivity or discovery check against the configured aliases.

## Core MCP Commands

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json
mcp-cli -d -c ~/.config/mcp/mcp_servers.json
mcp-cli -c ~/.config/mcp/mcp_servers.json info mysql
mcp-cli -c ~/.config/mcp/mcp_servers.json grep "*query*"
mcp-cli -c ~/.config/mcp/mcp_servers.json call mysql <tool> '{"sql":"select 1"}'
```

## Output Contract

- environment check result
- install or upgrade result
- config path
- smoke-check result

## Guardrails

- Keep secrets out of checked-in config.
- Prefer verification commands that do not mutate remote systems.
- Do not invent a second config path outside `app-context-init`.

## Related Skills

- `app-context-init`
- `resource-management`
