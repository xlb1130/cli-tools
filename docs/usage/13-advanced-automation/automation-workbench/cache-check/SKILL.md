---
name: cache-check
description: Use when the user needs Redis-backed investigation through CTS, including cache presence, stale values, hot keys, lock state, queue behavior, rate-limit clues, or release validation. This skill focuses on the Redis-backed `cts ops cache ...` commands.
---

# Cache Check

Use this skill for Redis-oriented troubleshooting.

## Primary Command Area

- `cts ops cache ...`

## Workflow

1. Identify the relevant key pattern, queue, lock, or cache namespace.
2. Check existence, freshness, and suspicious spikes.
3. Relate cache findings back to the user-visible symptom.

## Guardrails

- Prefer read-only operations.
- Be explicit when cache evidence is suggestive rather than conclusive.
