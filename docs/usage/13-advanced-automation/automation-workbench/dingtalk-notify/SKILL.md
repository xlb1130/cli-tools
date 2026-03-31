---
name: dingtalk-notify
description: Use when the user needs DingTalk robot messages through CTS for task completion, deployment milestones, failure escalation, incident conclusion, or other important checkpoints. This skill focuses on the DingTalk bot-backed `cts delivery notify ...` commands.
---

# DingTalk Notify

Use this skill only for meaningful notifications.

## Primary Command Area

- `cts delivery notify ...`

## Notification Triggers

- task completed
- testing started or completed
- deployment started
- deployment succeeded
- deployment failed
- rollback started or completed
- incident conclusion confirmed

## Message Rules

Every message should try to include:

- event type
- task or release id
- environment
- current result
- owner
- next action

## Guardrails

- Do not send noisy intermediate updates.
- If the event is not actionable or important, skip notification.
- Prefer short, scannable messages.
