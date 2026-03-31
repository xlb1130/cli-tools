---
name: automation-workbench
description: Use when the task spans multiple CTS automation capabilities such as bug analysis, requirement analysis, data query, log analysis, config/cache checks, JVM diagnosis, deployment verification, Yunxiao task sync, or DingTalk notifications. This is the parent orchestration skill and should route work to the narrower child skills when a task is mostly one capability.
---

# Automation Workbench

Use this as the parent skill for the automation stack in `docs/usage/12-advanced-automation`.

## When To Use

Use this skill when the user wants to complete an end-to-end engineering task through `cts`, especially when the work spans more than one of:

- fault analysis and bug fixing
- requirement analysis and development planning
- log search
- data query
- config inspection
- cache inspection
- JVM diagnosis
- deployment and post-release verification
- Yunxiao task updates
- DingTalk notifications

If the task is mostly one narrow capability, also use the matching child skill:

- [bug-analysis-fix](./bug-analysis-fix/SKILL.md)
- [requirements-development](./requirements-development/SKILL.md)
- [data-query](./data-query/SKILL.md)
- [log-analysis](./log-analysis/SKILL.md)
- [config-check](./config-check/SKILL.md)
- [cache-check](./cache-check/SKILL.md)
- [jvm-diagnosis](./jvm-diagnosis/SKILL.md)
- [release-verify](./release-verify/SKILL.md)
- [yunxiao-task-sync](./yunxiao-task-sync/SKILL.md)
- [dingtalk-notify](./dingtalk-notify/SKILL.md)

## Operating Rules

1. Discover before acting.
Run the relevant `cts ... --help`, `cts manage source test <source> --discover --format json`, or `cts manage mount list --format json` commands first when the available mounts or operation names are unclear.

2. Prefer the narrowest tool path.
Typical prefixes:
- `cts ops logs ...`
- `cts ops data ...`
- `cts ops config ...`
- `cts ops cache ...`
- `cts ops jvm ...`
- `cts delivery demand ...`
- `cts delivery deploy ...`
- `cts delivery notify ...`

3. Collect facts before conclusions.
For analysis work, gather logs, data, config, cache, and JVM evidence before concluding root cause.

4. Use notifications sparingly.
Only send DingTalk messages for completion, failure, deployment milestones, or other clearly important checkpoints.

5. Keep outputs structured.
Default output sections:
- objective
- evidence
- conclusion
- next action

## Default Flow

1. Identify the dominant scenario.
2. Load the matching child skill.
3. Verify the required mounts exist in `cts`.
4. Run the minimum tool sequence needed.
5. Summarize evidence and next action.
6. Sync or notify only if the task calls for it.
