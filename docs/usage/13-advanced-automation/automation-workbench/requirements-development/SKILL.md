---
name: requirements-development
description: Use when the user wants to turn a requirement into implementation-ready context through CTS, including Yunxiao task context, data and config inspection, risk analysis, task breakdown, deployment planning, and optional DingTalk notifications. This skill should commonly use yunxiao-task-sync, data-query, config-check, cache-check, log-analysis, release-verify, and dingtalk-notify.
---

# Requirements Development

Use this skill when the user starts from a demand, ticket, or feature request.

## Usually Pair With

- [yunxiao-task-sync](../yunxiao-task-sync/SKILL.md)
- [data-query](../data-query/SKILL.md)
- [config-check](../config-check/SKILL.md)
- [cache-check](../cache-check/SKILL.md)
- [log-analysis](../log-analysis/SKILL.md)
- [release-verify](../release-verify/SKILL.md)
- [dingtalk-notify](../dingtalk-notify/SKILL.md)

## Workflow

1. Read the requirement and its delivery context from Yunxiao when available.
2. Build the current-state model:
- impacted services
- impacted tables
- impacted config
- impacted cache
- backward-compatibility concerns
3. Produce implementation tasks, test points, release points, and rollback notes.
4. If asked to code, implement after the context is complete.
5. Sync task decomposition back to Yunxiao when useful.
6. Notify DingTalk only for agreed milestones such as start, testing, or done.

## Required Output

- goal and scope
- current-state findings
- affected components
- risks
- implementation plan
- testing and release plan

## Guardrails

- Do not jump straight to code if the current-state model is missing.
- Prefer evidence from data, config, cache, and recent logs over assumptions.
