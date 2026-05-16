# Automation Workbench

`automation-workbench` is a skill pack for CTS-based engineering automation. The root directory is a package container, not a skill.

## Structure

- `CATALOG.md`: full skill index, migration map, and asset rules
- `manifest.yaml`: package metadata and distribution contract
- `app-context-init/assets/`: templates, docs, scripts, and hooks distributed by `app-context-init`
- `*/SKILL.md`: the actual skills

## Skills

1. `app-context-init`
2. `performance-baseline`
3. `code-review-assistant`
4. `integration-test-platform`
5. `dingtalk-webhook-notify`
6. `implementation-acceptance`
7. `incident-diagnosis`
8. `log-query`
9. `mcp-cli-bootstrap`
10. `resource-management`
11. `alert-response-containment`
12. `solution-review`
13. `engineering-collaboration`
14. `release-checklist-generator`
15. `release-verify`
16. `requirements-development`
17. `security-review`
18. `self-evolution`
19. `task-scheduling-execution`
20. `technical-solution-writing`
21. `implementation-plan-writing`
22. `data-management`

## Notes

- Run `app-context-init` before any skill that depends on `~/.cts/settings.conf`, `~/.cts/common/`, or `mcp-cli`.
- All distributable assets now live under `app-context-init/` so the initialization skill owns its own payload.
- `app-context-init` is also the only skill that should create or update `~/.config/mcp/mcp_servers.json`.
- Root files define conventions; child skill directories define behavior.
