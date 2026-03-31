---
name: log-analysis
description: Use when the user needs log-based diagnosis through CTS, such as error clustering, time-window analysis, release regression checks, trace keyword lookup, or incident evidence collection. This skill focuses on the SLS-backed `cts ops logs ...` commands.
---

# Log Analysis

Use this skill for log-centric diagnosis.

## Primary Command Area

- `cts ops logs ...`

## Workflow

1. Anchor the time window first.
2. Search for the main error or symptom keywords.
3. Group by error pattern, service, or instance when possible.
4. Extract a small set of representative evidence.
5. Correlate with data, config, cache, or deployment events if needed.

## Required Output

- time window
- key patterns
- affected services or instances
- representative evidence
- likely next check

## Guardrails

- Do not paste excessive log volume.
- Prefer clustered findings over a long list of raw lines.
