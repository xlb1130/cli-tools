---
name: config-check
description: Use when the user needs to inspect or compare service configuration through CTS, especially environment drift, missing switches, wrong namespace values, or release-time config validation. This skill focuses on the Nacos-backed `cts ops config ...` commands.
---

# Config Check

Use this skill for configuration validation through `cts`.

## Primary Command Area

- `cts ops config ...`

## Workflow

1. Confirm environment, namespace, service, and expected behavior.
2. Inspect the active configuration values.
3. Compare expected versus actual values.
4. Call out risky differences, missing toggles, or suspicious defaults.

## Guardrails

- Prefer read-only inspection unless the task explicitly asks for mutation.
- Highlight environment mismatches clearly.
