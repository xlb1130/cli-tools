---
name: release-verify
description: Use when the user needs deployment execution or release verification through CTS, including Jenkins builds, pre-release checks, post-release smoke validation, rollback reasoning, and milestone notifications. This skill commonly pairs with log-analysis, data-query, config-check, cache-check, and dingtalk-notify.
---

# Release Verify

Use this skill for build, deployment, and post-release checks.

## Usually Pair With

- [log-analysis](../log-analysis/SKILL.md)
- [data-query](../data-query/SKILL.md)
- [config-check](../config-check/SKILL.md)
- [cache-check](../cache-check/SKILL.md)
- [dingtalk-notify](../dingtalk-notify/SKILL.md)

## Primary Command Areas

- `cts delivery deploy ...`
- `cts delivery notify ...`

## Workflow

1. Validate target environment and release identifier.
2. Check key config before deployment.
3. Trigger or inspect Jenkins pipeline.
4. Verify logs, data, and cache after release.
5. Recommend rollback if the evidence fails validation.
6. Notify only at start, success, failure, or rollback.

## Guardrails

- Treat production deployment as high risk.
- Prefer explicit verification evidence over pipeline status alone.
