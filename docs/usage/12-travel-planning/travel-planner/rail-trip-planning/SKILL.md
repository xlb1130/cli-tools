---
name: rail-trip-planning
description: Use when the user mainly needs 12306-backed train planning through CTS, such as train lookup, departure comparison, transfer feasibility, or timing selection for cross-city trips. This skill focuses on the rail-backed `cts travel rail ...` commands.
---

# Rail Trip Planning

Use this skill for train-centric itinerary work.

## Primary Command Area

- `cts travel rail ...`

## Workflow

1. Confirm departure city, arrival city, date, and preferred departure window.
2. Compare direct and transfer options.
3. Prioritize feasible timing, arrival convenience, and transfer simplicity.
4. Surface backup options if seat availability may change.

## Guardrails

- Treat 12306 results as time-sensitive.
- Avoid overcommitting to one option without a fallback.
