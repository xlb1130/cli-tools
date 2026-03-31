---
name: travel-planner
description: Use when the user wants itinerary planning through CTS by combining map routing, 12306 rail planning, and web search research. This is the parent skill for travel planning and should route to the narrower child skills for city routing, rail planning, web research, and itinerary synthesis.
---

# Travel Planner

Use this as the parent skill for the travel-planning stack in `docs/usage/13-travel-planning`.

## When To Use

Use this skill when the user wants:

- a city or cross-city travel plan
- train-first trip planning with local route connections
- scenic spot or city-day itinerary design
- a structured route with timing, cost, and fallbacks

If the task is mostly one narrow capability, also use the matching child skill:

- [city-route-planning](./city-route-planning/SKILL.md)
- [rail-trip-planning](./rail-trip-planning/SKILL.md)
- [travel-web-research](./travel-web-research/SKILL.md)
- [itinerary-synthesis](./itinerary-synthesis/SKILL.md)

## Operating Rules

1. Clarify constraints first.
Collect origin, destination, date, traveler count, budget, preferred pace, and special constraints before planning.

2. Prefer transport facts over generic advice.
Use map and rail results as the factual backbone. Use search mainly for supplementary context.

3. Separate primary and backup plans.
Always give at least one main option and one fallback when timing or ticket availability may vary.

4. Keep outputs executable.
Default output sections:
- goal
- constraints
- recommended plan
- backup plan
- timing
- cost
- reminders

## Default Flow

1. Use rail planning when cross-city transport is involved.
2. Use city routing for station-to-hotel or point-to-point movement.
3. Use web research for attraction hours, weather, or practical tips.
4. Use itinerary synthesis to combine all findings into one plan.
