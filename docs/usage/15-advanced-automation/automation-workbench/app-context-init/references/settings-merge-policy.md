# Settings Merge Policy

## Goal

Protect user customization while keeping the automation-managed configuration block consistent and upgradeable.

## Hard Rules

- `~/.cts/settings.conf` must never be replaced wholesale.
- User-authored content outside the managed block is preserved.
- Missing managed block should be appended rather than inferred.

## Managed Block Markers

- Start: `# cts automation-workbench managed block start`
- End: `# cts automation-workbench managed block end`

## Merge Semantics

- Keys inside the managed block may be inserted, updated, or removed by versioned templates.
- Keys outside the managed block are treated as user-owned and immutable to automation.
- If the managed block exists multiple times, the merge should fail fast and request manual cleanup.

## Architect-Level Constraints

- Merge behavior must be deterministic.
- Template evolution must remain backward compatible where practical.
- The merge result should be diffable so operators can see what changed.

## Related Files

This policy applies to `~/.cts/settings.conf`. Agent-facing workspace files such as `CLAUDE.md` and `AGENTS.md` should follow the parallel policy in `agent-context-injection.md` instead of this exact marker format.
