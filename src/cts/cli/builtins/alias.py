from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

import click

from cts.cli.lazy import CTSApp, apply_update, prepare_edit_session, render_payload
from cts.execution.errors import RegistryError


def register_alias_commands(
    alias_group,
    *,
    pass_app,
    pass_help_app,
    get_state: Callable,
    fail: Callable,
    maybe_confirm: Callable,
    progress_steps: Any,
    conflict_signatures: Callable,
    split_command_segments: Callable,
    find_alias_payload: Callable,
) -> None:
    @alias_group.command(name="list", help="List configured command aliases.", short_help="List configured command aliases.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_help_app
    def alias_list(app, output_format: str) -> None:
        items = []
        for raw in app.config.aliases:
            if not isinstance(raw, dict):
                continue
            items.append({"from": raw.get("from"), "to": raw.get("to")})
        click.echo(render_payload({"items": items}, output_format))

    @alias_group.command(name="add", help="Create an alias for an existing command path.", short_help="Create an alias for an existing command path.")
    @click.argument("alias_from")
    @click.argument("alias_to")
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write into a specific loaded config file.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def alias_add(ctx: click.Context, alias_from: str, alias_to: str, target_file: Optional[Path], output_format: str) -> None:
        state = get_state(ctx)
        try:
            session = prepare_edit_session(state.config_path, target_file=target_file)
            app = CTSApp(
                session.loaded,
                active_profile=state.profile,
                explicit_config_path=str(state.config_path) if state.config_path else None,
                requested_profile=state.profile,
            )
            from_tokens = split_command_segments([alias_from])
            to_tokens = split_command_segments([alias_to])
            target_mount = app.catalog.find_by_path(to_tokens)
            if target_mount is None:
                raise RegistryError(f"alias target path not found: {' '.join(to_tokens)}", code="alias_target_not_found")
            existing = app.catalog.find_by_path(from_tokens)
            if existing is not None:
                raise RegistryError(f"alias path already exists: {' '.join(from_tokens)}", code="alias_conflict")

            baseline_conflicts = conflict_signatures(app.catalog.conflicts)

            def mutator(payload: Dict[str, Any]) -> None:
                aliases = payload.setdefault("aliases", [])
                if not isinstance(aliases, list):
                    raise RegistryError("aliases payload must be a list", code="aliases_payload_invalid")
                aliases.append({"from": from_tokens, "to": to_tokens})

            updated, compiled_app = apply_update(
                session,
                mutator,
                compile_runtime=True,
                profile=state.profile,
                baseline_conflicts=baseline_conflicts,
            )
            resolved_alias_mount = compiled_app.catalog.find_by_path(from_tokens) if compiled_app else None
            payload = {
                "ok": True,
                "action": "alias_add",
                "file": str(session.target_path),
                "created_file": session.created,
                "warnings": list(session.warnings),
                "alias": {"from": from_tokens, "to": to_tokens},
                "mount_id": resolved_alias_mount.mount_id if resolved_alias_mount else target_mount.mount_id,
                "next_commands": [
                    f"cts {' '.join(from_tokens)} --help",
                    "cts manage alias list",
                ],
                "config": find_alias_payload(updated.get("aliases", []), from_tokens),
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "alias_add", output_format)

    @alias_group.command(name="remove", help="Remove a configured command alias.", short_help="Remove a configured command alias.")
    @click.argument("alias_from")
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Remove from a specific loaded config file.")
    @click.option("--yes", is_flag=True, help="Skip interactive confirmation.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def alias_remove(ctx: click.Context, alias_from: str, target_file: Optional[Path], yes: bool, output_format: str) -> None:
        state = get_state(ctx)
        try:
            session = prepare_edit_session(state.config_path, target_file=target_file)
            from_tokens = split_command_segments([alias_from])
            removed: Optional[Dict[str, Any]] = None
            maybe_confirm(f"Remove alias '{' '.join(from_tokens)}'?", assume_yes=yes, output_format=output_format)
            with progress_steps(output_format, f"Removing alias '{' '.join(from_tokens)}'", ["Validate alias", "Write config"]) as progress:
                progress.advance("Validating alias")

                def mutator(payload: Dict[str, Any]) -> None:
                    nonlocal removed
                    aliases = payload.setdefault("aliases", [])
                    if not isinstance(aliases, list):
                        raise RegistryError("aliases payload must be a list", code="aliases_payload_invalid")
                    remaining = []
                    for item in aliases:
                        if removed is None and isinstance(item, dict) and item.get("from") == from_tokens:
                            removed = item
                            continue
                        remaining.append(item)
                    if removed is None:
                        raise RegistryError(f"alias not found: {' '.join(from_tokens)}", code="alias_not_found")
                    payload["aliases"] = remaining

                progress.advance("Writing config")
                updated, _ = apply_update(session, mutator, compile_runtime=False)
            payload = {
                "ok": True,
                "action": "alias_remove",
                "file": str(session.target_path),
                "created_file": session.created,
                "warnings": list(session.warnings),
                "alias": removed,
                "remaining_count": len(updated.get("aliases", [])),
                "next_command": "cts manage alias list",
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "alias_remove", output_format)
