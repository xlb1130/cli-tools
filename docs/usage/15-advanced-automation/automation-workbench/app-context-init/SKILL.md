---
name: app-context-init
description: Use when the local CTS automation environment must be initialized or repaired, including node and mcp-cli checks, `~/.config/mcp/mcp_servers.json` bootstrap, own-doc distribution, common-doc and script distribution, `~/.cts/settings.conf` creation or merge, and managed context injection into `CLAUDE.md`-like files.
---

# 应用上下文初始化

## When To Use

- 首次使用 automation-workbench
- `~/.cts/settings.conf` 缺失
- `~/.cts/common/` 缺失或不完整
- `mcp-cli` 不存在或配置未就绪

## Preconditions

- 具备本机文件读写权限
- 可执行 `node`、`npm`、`npx`
- 可执行 `python3`

## Inputs

- target environment
- whether to install `mcp-cli` if missing
- whether to overwrite distributed docs and scripts

## MCP Ownership

This is the only skill that should:

- install or verify `mcp-cli`
- create or update `~/.config/mcp/mcp_servers.json`
- inject managed governance context into `CLAUDE.md`, `AGENTS.md`, or equivalent workspace agent context files
- standardize server aliases such as `dingtalk`, `yunxiao`, `mysql`, `gitlab`, `redis`, `grafana`, `kubernetes`, and `playwright`
- record the recommended servers and tool families for child skills

The injected context should tell the agent:

- which file is for what purpose
- when each file should be used
- where the source document lives
- which MCP aliases are expected

Child skills should consume these aliases through `mcp-cli`, not mutate config.

## Workflow

1. Check `node`, `npm`, `npx`, `python3`, and `mcp-cli`.
2. Create `~/.cts/`, `~/.cts/common/`, and `~/.cts/automation-workbench/` if missing.
3. Read templates, docs, and scripts from `app-context-init/assets/`.
4. Bootstrap `~/.config/mcp/mcp_servers.json` from template.
5. Distribute own docs to `~/.cts/automation-workbench/docs/`.
6. Distribute common docs to `~/.cts/common/docs/`.
7. Distribute common scripts and hooks to `~/.cts/common/scripts/`.
8. Create or merge `~/.cts/settings.conf` using managed block mode.
9. Inject the managed summary block into `CLAUDE.md`, `AGENTS.md`, or equivalent workspace agent context files, focusing on file purpose, when-to-use guidance, and source paths.
10. Verify the configured aliases with `mcp-cli`, `mcp-cli info <server>`, and representative `mcp-cli call <server> <tool> <json>` commands.
11. Emit an installation report with created, updated, skipped, and failed items.

## Core MCP Commands

```bash
mcp-cli -c ~/.config/mcp/mcp_servers.json
mcp-cli -d -c ~/.config/mcp/mcp_servers.json
mcp-cli -c ~/.config/mcp/mcp_servers.json info yunxiao
mcp-cli -c ~/.config/mcp/mcp_servers.json info yunxiao <tool>
mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <tool> '{"key":"value"}'
cat input.json | mcp-cli -c ~/.config/mcp/mcp_servers.json call yunxiao <tool>
```

## Output Contract

- environment check result
- mcp-cli version and config path
- configured server aliases
- distributed asset summary
- settings merge result
- injected agent context targets
- next action if something failed

## Guardrails

- Do not overwrite the whole `~/.cts/settings.conf`.
- Do not overwrite the whole `CLAUDE.md` or `AGENTS.md`; only update the managed block.
- Do not delete user files outside managed target paths.
- Preserve executable bits for scripts.

## Related Skills

- `mcp-cli-bootstrap`
- `resource-management`
- `self-evolution`
