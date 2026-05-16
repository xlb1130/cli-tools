# Agent Context Injection

## Goal

Inject a concise, enforceable summary of automation-workbench rules into agent-facing workspace files such as `CLAUDE.md` and `AGENTS.md`, so the agent can consume operating constraints without reading the full document set first.

## Target Files

Recommended targets, in priority order:

1. `./CLAUDE.md`
2. `./AGENTS.md`
3. `./GEMINI.md`
4. Other workspace agent context files explicitly configured by the operator

## Injection Content

The injected block should summarize:

- which file is for what purpose
- when each file should be consulted
- preferred MCP aliases and their intent
- security and data handling constraints
- the scenario-first execution rule

It should not duplicate full documents verbatim, but it should be explicit enough that an agent can decide which file to open first.

## File Explanation Requirement

The injected block should not just say "read the docs". It should explicitly tell the agent:

- which file covers guardrails
- which file defines context shape
- which file defines release checks
- which file defines security boundaries
- which file defines health and reliability expectations
- which file defines path and filesystem rules

Each item should include:

- file path
- purpose
- when to use

## Injection Strategy

- Use a managed block merge, not full-file overwrite.
- Create the file if it does not exist and creation is allowed by the operator.
- If the file exists, preserve user-authored content outside the managed block.
- If multiple managed blocks exist, fail fast and request manual cleanup.

## Managed Block Markers

- Start: `<!-- cts automation-workbench managed context start -->`
- End: `<!-- cts automation-workbench managed context end -->`

## Architect-Level Constraints

- The injected summary must remain short enough to be practical as agent context.
- The injected summary must point to source documents instead of replacing them.
- The injected summary must optimize for routing the agent to the right file quickly.
- Updates should be deterministic so repeated initialization yields the same block when inputs are unchanged.
