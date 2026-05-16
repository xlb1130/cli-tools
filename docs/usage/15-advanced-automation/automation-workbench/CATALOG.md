# Automation Workbench Catalog

## Package Positioning

`automation-workbench` is a skill pack for engineering automation scenarios built on CTS. The root is a container for:

- package metadata
- the child skills
- 22 executable child skills

The primary unit of design is the engineering scenario, not the raw MCP call. MCP is an execution substrate; each skill should explain when the scenario is triggered, what evidence to collect first, how to decide, and what output to produce.

## Skill Index

| slug | 中文 | role | depends on |
|---|---|---|---|
| `app-context-init` | 应用上下文初始化 | initialize the shared engineering workspace and MCP substrate | none |
| `performance-baseline` | 性能基线 | judge whether a change caused measurable performance regression | `app-context-init` |
| `code-review-assistant` | 代码审查辅助 | review change risk before merge or release | none |
| `integration-test-platform` | 集成测试平台 | validate multi-service behavior before release | `app-context-init` |
| `dingtalk-webhook-notify` | 钉钉 Webhook 消息 | notify milestone, incident, or release outcomes | none |
| `implementation-acceptance` | 实现验收 | decide whether delivered behavior is acceptable | `integration-test-platform` |
| `incident-diagnosis` | 问题诊断与排查 | converge on root cause from runtime evidence | `log-query`, `data-management`, `resource-management` |
| `log-query` | 日志查询 | establish the runtime fact surface for debugging or release validation | `app-context-init` |
| `mcp-cli-bootstrap` | MCP CLI 安装与使用 | verify the local MCP execution substrate | `app-context-init` |
| `resource-management` | 资源管理 | inspect config, cache, cluster, and runtime health under real incidents | `app-context-init` |
| `alert-response-containment` | 告警响应与止血 | stop impact growth before full repair | `incident-diagnosis` |
| `solution-review` | 方案评审 | challenge design decisions before implementation | `technical-solution-writing` |
| `engineering-collaboration` | 研发协作 | keep tasks, risks, and milestones synchronized across roles | `requirements-development` |
| `release-checklist-generator` | 发布检查清单生成 | turn change scope into executable release controls | `requirements-development` |
| `release-verify` | 发布校验 | verify whether a release should continue, observe, or roll back | `log-query`, `data-management`, `resource-management` |
| `requirements-development` | 需求开发 | turn a business ask into engineering-ready context | `data-management`, `resource-management` |
| `security-review` | 安全审查 | identify security blockers before release | `resource-management` |
| `self-evolution` | 自进化 | convert incidents and successes into reusable rules | `app-context-init` |
| `task-scheduling-execution` | 任务调度与执行 | run recurring engineering tasks with tracking and escalation | `app-context-init` |
| `technical-solution-writing` | 技术方案撰写 | produce decision-ready technical design documents | `requirements-development` |
| `implementation-plan-writing` | 编写实现计划 | convert scope into milestones, ordering, and validation steps | `requirements-development` |
| `data-management` | 数据管理 | answer engineering questions with production-like data facts | `app-context-init` |

## Asset Layout

All distributable assets are owned by `app-context-init` and stored under `app-context-init/assets/`.

### Own Docs

Distributed from `app-context-init/assets/own-docs/` to `~/.cts/automation-workbench/docs/`.

1. `01-guardrails.md`
2. `02-quality-check-report.md`
3. `03-checkpoints.md`
4. `04-git-workflow.md`
5. `05-health-check.md`
6. `06-switch-guidelines.md`
7. `07-implementation-acceptance.md`
8. `08-client-compatibility.md`
9. `09-diamond-guidelines.md`
10. `10-self-evolution.md`
11. `11-reliability-five-pieces.md`
12. `12-coding-guidelines.md`
13. `13-integration-test-config.md`
14. `14-release-checklist.md`
15. `15-security-baseline.md`
16. `16-task-anchor-check.md`
17. `17-testing-guidelines.md`
18. `18-post-coding-checklist.md`

### Common Docs

Distributed from `app-context-init/assets/common-docs/` to `~/.cts/common/docs/`.

1. `01-context-object.md`
2. `02-error-handling.md`
3. `03-token-tracking.md`
4. `04-file-permissions.md`
5. `05-path-conventions.md`
6. `06-metrics-tracking.md`
7. `07-duration-baseline.md`
8. `08-execution-tracking.md`

### Common Scripts

Distributed from `app-context-init/assets/common-scripts/` to `~/.cts/common/scripts/`.

- `utils.py`
- `report_uploader.py`
- `task_reporter.py`
- `token_collector.py`
- `self_evolution_reporter.py`
- `task_id_generator.py`
- `hooks/`

## Distribution Rules

- The root package is not a skill.
- Child directories containing `SKILL.md` are the only executable skills.
- `app-context-init` owns all distributable docs, scripts, and templates.
- `app-context-init` is the only skill that should create or mutate `mcp-cli` config.
- `app-context-init` is also the only skill that should inject managed summaries into `CLAUDE.md`-like agent context files.
- Child skills should use `mcp-cli`, `mcp-cli info`, `mcp-cli grep`, and `mcp-cli call` against configured aliases instead of rewriting config.
- `~/.cts/settings.conf` must be updated with a managed block merge, never full-file overwrite.
- `CLAUDE.md`, `AGENTS.md`, and similar files must be updated by managed block merge rather than full-file overwrite.
- Distributed scripts should preserve executable permission where needed.
- Generated reports should be written under `~/.cts/automation-workbench/`.

## Skill Reading Map

The following map shows which documents each skill should treat as mandatory reading before being considered complete or production-ready.

| skill | must-read docs |
|---|---|
| `app-context-init` | `01-guardrails.md`, `04-file-permissions.md`, `05-path-conventions.md`, `distribution-rules.md`, `settings-merge-policy.md` |
| `performance-baseline` | `06-metrics-tracking.md`, `07-duration-baseline.md`, `11-reliability-five-pieces.md` |
| `code-review-assistant` | `12-coding-guidelines.md`, `15-security-baseline.md`, `18-post-coding-checklist.md` |
| `integration-test-platform` | `13-integration-test-config.md`, `17-testing-guidelines.md`, `08-execution-tracking.md` |
| `dingtalk-webhook-notify` | `01-guardrails.md`, `08-execution-tracking.md` |
| `implementation-acceptance` | `07-implementation-acceptance.md`, `17-testing-guidelines.md`, `14-release-checklist.md` |
| `incident-diagnosis` | `01-guardrails.md`, `05-health-check.md`, `11-reliability-five-pieces.md`, `08-execution-tracking.md`, `02-error-handling.md` |
| `log-query` | `05-health-check.md`, `06-metrics-tracking.md`, `08-execution-tracking.md` |
| `mcp-cli-bootstrap` | `05-path-conventions.md`, `04-file-permissions.md`, `distribution-rules.md` |
| `resource-management` | `05-health-check.md`, `06-switch-guidelines.md`, `09-diamond-guidelines.md`, `15-security-baseline.md` |
| `alert-response-containment` | `01-guardrails.md`, `06-switch-guidelines.md`, `11-reliability-five-pieces.md`, `14-release-checklist.md` |
| `solution-review` | `03-checkpoints.md`, `08-client-compatibility.md`, `12-coding-guidelines.md`, `15-security-baseline.md` |
| `engineering-collaboration` | `01-context-object.md`, `03-checkpoints.md`, `16-task-anchor-check.md`, `08-execution-tracking.md` |
| `release-checklist-generator` | `14-release-checklist.md`, `16-task-anchor-check.md`, `11-reliability-five-pieces.md` |
| `release-verify` | `14-release-checklist.md`, `05-health-check.md`, `06-metrics-tracking.md`, `07-duration-baseline.md`, `08-execution-tracking.md` |
| `requirements-development` | `01-context-object.md`, `03-checkpoints.md`, `08-client-compatibility.md`, `16-task-anchor-check.md` |
| `security-review` | `15-security-baseline.md`, `04-file-permissions.md`, `12-coding-guidelines.md` |
| `self-evolution` | `10-self-evolution.md`, `03-token-tracking.md`, `06-metrics-tracking.md`, `08-execution-tracking.md` |
| `task-scheduling-execution` | `01-guardrails.md`, `07-duration-baseline.md`, `08-execution-tracking.md`, `04-file-permissions.md` |
| `technical-solution-writing` | `03-checkpoints.md`, `08-client-compatibility.md`, `12-coding-guidelines.md`, `15-security-baseline.md` |
| `implementation-plan-writing` | `03-checkpoints.md`, `16-task-anchor-check.md`, `07-duration-baseline.md` |
| `data-management` | `01-guardrails.md`, `04-file-permissions.md`, `02-error-handling.md`, `08-execution-tracking.md` |

## Asset Maintenance Notes

- Governance rules belong in `own-docs/`.
- Reusable execution contracts belong in `common-docs/`.
- Shared helper code belongs in `common-scripts/`.
- Configuration seeds and report examples belong in `templates/`.
- Agent-facing managed summaries belong in `templates/agent-context-snippet.md.example`.
- New assets should be indexed from `app-context-init/assets/README.md`.

## Migration Map

| old skill | new skill |
|---|---|
| `bug-analysis-fix` | `incident-diagnosis` |
| `log-analysis` | `log-query` |
| `data-query` | `data-management` |
| `config-check` | `resource-management` |
| `cache-check` | `resource-management` |
| `jvm-diagnosis` | `resource-management` |
| `dingtalk-notify` | `dingtalk-webhook-notify` |
| `yunxiao-task-sync` | `engineering-collaboration` |
| `requirements-development` | `requirements-development` |
| `release-verify` | `release-verify` |
