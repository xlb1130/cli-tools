---
name: data-query
description: Use when the user needs database facts through CTS, such as record lookup, scope estimation, anomaly sampling, release validation, or business data confirmation. This skill focuses on the MySQL-backed `cts ops data ...` commands.
---

# Data Query

Use this skill for MySQL-backed investigation through `cts`.

## Primary Command Area

- `cts ops data ...`

## Workflow

1. Discover the available data mounts or operations if needed.
2. Clarify the business key, time range, and environment.
3. Query the minimum data needed to answer the question.
4. Summarize findings in business terms, not raw rows only.

## Best Practices

- Prefer read-only validation queries.
- Use sampled evidence when full scans are unnecessary.
- Report counts, affected ranges, and concrete examples.

## Guardrails

- Avoid destructive SQL.
- If sensitive fields appear, summarize rather than exposing unnecessary raw values.
