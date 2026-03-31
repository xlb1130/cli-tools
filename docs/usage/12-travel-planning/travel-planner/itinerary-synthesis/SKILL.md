---
name: itinerary-synthesis
description: Use when the user needs a final structured itinerary after route, rail, and web findings have been collected through CTS. This skill combines facts into a practical travel plan with timing, budget, and reminders.
---

# Itinerary Synthesis

Use this skill when the evidence gathering is mostly done and the user needs a coherent final plan.

## Inputs To Combine

- map travel times
- rail timing and options
- attraction or city information
- user constraints

## Output Format

- objective
- constraints
- main plan
- fallback plan
- time blocks
- budget notes
- reminders

## Guardrails

- Keep the plan realistic and time-ordered.
- If key facts are missing, ask for or note the missing constraint instead of pretending certainty.
