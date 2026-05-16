# Distribution Rules

## Goal

Define a repeatable and low-risk distribution contract for all assets owned by `app-context-init`.

## Ownership Model

- `app-context-init/assets/own-docs/` is the source of project-specific governance material.
- `app-context-init/assets/common-docs/` is the source of cross-skill execution contracts.
- `app-context-init/assets/common-scripts/` is the source of reusable automation helpers.
- `app-context-init/assets/templates/` is the source of managed configuration templates.

## Target Paths

- Own docs go to `~/.cts/automation-workbench/docs/`.
- Common docs go to `~/.cts/common/docs/`.
- Common scripts and `hooks/` go to `~/.cts/common/scripts/`.
- MCP config goes to `~/.config/mcp/mcp_servers.json`.

## Distribution Principles

- Target directories should be created if missing.
- Re-distribution must be idempotent.
- User-authored files outside managed targets must not be touched.
- Distribution should emit a report with created, updated, skipped, and failed items.

## Architect-Level Constraints

- Distribution must be deterministic across repeated runs.
- File layout must remain stable so scripts and docs can reference fixed paths.
- Managed assets should be replaceable without requiring manual cleanup.
