---
name: bug-analysis-fix
description: Use when the user wants to analyze a production or test failure, locate root cause, verify impact, propose or implement a fix, and optionally sync the result to Yunxiao or DingTalk. This skill should commonly use log-analysis, data-query, config-check, cache-check, jvm-diagnosis, yunxiao-task-sync, and dingtalk-notify.
---

# Bug Analysis Fix

Use this skill for incident handling and bug repair work.

## Usually Pair With

- [log-analysis](../log-analysis/SKILL.md)
- [data-query](../data-query/SKILL.md)
- [config-check](../config-check/SKILL.md)
- [cache-check](../cache-check/SKILL.md)
- [jvm-diagnosis](../jvm-diagnosis/SKILL.md)
- [yunxiao-task-sync](../yunxiao-task-sync/SKILL.md)
- [dingtalk-notify](../dingtalk-notify/SKILL.md)

## Workflow

1. Confirm environment, service, time window, and symptom.
2. Use logs first.
3. Use data query to verify scope and reproduce patterns.
4. Check config and cache if behavior may be environment- or state-dependent.
5. Use JVM diagnosis for Java runtime issues.
6. Only after evidence is stable, state root cause and fix plan.
7. If code changes are in scope, implement and verify them.
8. Sync the conclusion to Yunxiao and notify DingTalk only at meaningful milestones.

## Required Output

- symptom
- impact scope
- evidence
- root cause
- fix or mitigation
- verification result

## Guardrails

- Do not claim root cause without direct evidence.
- Do not notify for every intermediate observation.
- If the issue is still ambiguous, report competing hypotheses and the next discriminating check.
