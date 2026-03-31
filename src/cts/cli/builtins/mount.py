from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import click

from cts.cli.lazy import (
    CTSApp,
    apply_assignment,
    apply_update,
    build_mount_details,
    prepare_edit_session,
    render_payload,
    tokenize_identifier,
)
from cts.execution.errors import RegistryError


def register_mount_commands(
    mount_group,
    *,
    pass_app,
    get_state: Callable,
    fail: Callable,
    maybe_confirm: Callable,
    progress_steps: Any,
    status: Callable,
    conflict_signatures: Callable,
    split_command_segments: Callable,
    build_param_payload: Callable,
    parse_assignment_value: Callable,
    find_mount_payload: Callable,
) -> None:
    @mount_group.command("add")
    @click.argument("source_name")
    @click.argument("operation_id")
    @click.option("--id", "mount_id", default=None, help="Stable mount id. Defaults to <source>-<operation>.")
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write into a specific loaded config file.")
    @click.option("--path", "command_path_values", multiple=True, help='Full command path. Example: --path "ops jira issue get".')
    @click.option("--as", "command_path_values", multiple=True, help="Alias of --path for CLI ergonomics.")
    @click.option("--under", "under_values", multiple=True, help="Command prefix used together with the operation id tokens.")
    @click.option("--alias", "alias_values", multiple=True, help="Repeatable alias command path.")
    @click.option("--stable-name", default=None)
    @click.option("--summary", default=None)
    @click.option("--description", default=None)
    @click.option("--note", "notes", multiple=True)
    @click.option("--example", "examples", multiple=True)
    @click.option("--expose", "surfaces", multiple=True)
    @click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default=None)
    @click.option("--param", "param_specs", multiple=True, help="Parameter spec in name[:type] form.")
    @click.option("--required", "required_params", multiple=True, help="Repeatable required parameter name.")
    @click.option("--param-help", "param_help_items", multiple=True, help="Parameter help in name=text form.")
    @click.option("--param-default", "param_default_items", multiple=True, help="Parameter default in name=value form.")
    @click.option("--param-flag", "param_flag_items", multiple=True, help="Parameter flag in name=--flag form.")
    @click.option("--set", "assignments", multiple=True, help="Arbitrary mount override, for example --set policy.confirm=true.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def mount_add(
        ctx: click.Context,
        source_name: str,
        operation_id: str,
        mount_id: Optional[str],
        target_file: Optional[Path],
        command_path_values: tuple[str, ...],
        under_values: tuple[str, ...],
        alias_values: tuple[str, ...],
        stable_name: Optional[str],
        summary: Optional[str],
        description: Optional[str],
        notes: tuple[str, ...],
        examples: tuple[str, ...],
        surfaces: tuple[str, ...],
        risk: Optional[str],
        param_specs: tuple[str, ...],
        required_params: tuple[str, ...],
        param_help_items: tuple[str, ...],
        param_default_items: tuple[str, ...],
        param_flag_items: tuple[str, ...],
        assignments: tuple[str, ...],
        output_format: str,
    ) -> None:
        state = get_state(ctx)
        try:
            with progress_steps(output_format, f"Adding mount '{mount_id or operation_id}'", ["Validate mount", "Compile config"]) as progress:
                session = prepare_edit_session(state.config_path, target_file=target_file)
                app = CTSApp(
                    session.loaded,
                    active_profile=state.profile,
                    explicit_config_path=str(state.config_path) if state.config_path else None,
                    requested_profile=state.profile,
                )
                if source_name not in app.config.sources:
                    raise RegistryError(f"source not found: {source_name}", code="source_not_found")

                final_mount_id = mount_id or f"{source_name}-{operation_id}".replace(".", "-").replace("_", "-")
                progress.advance("Validating mount")
                if app.catalog.find_by_id(final_mount_id) is not None:
                    raise RegistryError(f"mount already exists: {final_mount_id}", code="mount_exists")

                command_path = split_command_segments(command_path_values)
                under_path = split_command_segments(under_values)
                alias_paths = [split_command_segments([item]) for item in alias_values]
                if not command_path and not under_path:
                    command_path = tokenize_identifier(operation_id)

                baseline_conflicts = conflict_signatures(app.catalog.conflicts)

                def mutator(payload: Dict[str, Any]) -> None:
                    mounts = payload.setdefault("mounts", [])
                    if not isinstance(mounts, list):
                        raise RegistryError("mounts payload must be a list", code="mounts_payload_invalid")
                    mount_payload: Dict[str, Any] = {
                        "id": final_mount_id,
                        "source": source_name,
                        "operation": operation_id,
                    }
                    command_payload: Dict[str, Any] = {}
                    if command_path:
                        command_payload["path"] = command_path
                    if under_path:
                        command_payload["under"] = under_path
                    if alias_paths:
                        command_payload["aliases"] = alias_paths
                    if command_payload:
                        mount_payload["command"] = command_payload

                    machine_payload: Dict[str, Any] = {}
                    if stable_name:
                        machine_payload["stable_name"] = stable_name
                    if surfaces:
                        machine_payload["expose_via"] = list(surfaces)
                    if machine_payload:
                        mount_payload["machine"] = machine_payload

                    help_payload: Dict[str, Any] = {}
                    if summary:
                        help_payload["summary"] = summary
                    if description:
                        help_payload["description"] = description
                    if notes:
                        help_payload["notes"] = list(notes)
                    if examples:
                        help_payload["examples"] = list(examples)
                    if help_payload:
                        mount_payload["help"] = help_payload

                    if risk:
                        mount_payload["policy"] = {"risk": risk}

                    params_payload = build_param_payload(
                        param_specs=param_specs,
                        required_params=required_params,
                        param_help_items=param_help_items,
                        param_default_items=param_default_items,
                        param_flag_items=param_flag_items,
                    )
                    if params_payload:
                        mount_payload["params"] = params_payload

                    for assignment in assignments:
                        path, value = parse_assignment_value(assignment)
                        apply_assignment(mount_payload, path, value)

                    mounts.append(mount_payload)

                progress.advance("Compiling config")
                updated, compiled_app = apply_update(
                    session,
                    mutator,
                    compile_runtime=True,
                    profile=state.profile,
                    baseline_conflicts=baseline_conflicts,
                )
            compiled_mount = compiled_app.catalog.find_by_id(final_mount_id) if compiled_app else None
            payload = {
                "ok": True,
                "action": "mount_add",
                "mount_id": final_mount_id,
                "file": str(session.target_path),
                "created_file": session.created,
                "warnings": list(session.warnings),
                "next_commands": [
                    f"cts manage mount show {final_mount_id}",
                    "cts manage mount list",
                ],
                "config": find_mount_payload(updated.get("mounts", []), final_mount_id),
                "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "mount_add", output_format)

    @mount_group.command("list")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def mount_list(app, output_format: str) -> None:
        payload = {"mounts": [mount.to_summary() for mount in app.catalog.mounts], "conflicts": app.catalog.conflicts}
        click.echo(render_payload(payload, output_format))

    @mount_group.command("show")
    @click.argument("mount_id")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def mount_show(app, mount_id: str, output_format: str) -> None:
        mount = app.catalog.find_by_id(mount_id)
        if not mount:
            fail(click.get_current_context(), RegistryError(f"mount not found: {mount_id}", code="mount_not_found"), "show_mount", output_format)
            return
        payload = build_mount_details(app, mount)
        payload["next_commands"] = [
            f"cts {' '.join(mount.command_path)} --help",
            f"cts manage runs list --mount-id {mount_id}",
        ]
        click.echo(render_payload(payload, output_format))

    @mount_group.command("remove")
    @click.argument("mount_id")
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Remove from a specific config file.")
    @click.option("--yes", is_flag=True, help="Skip interactive confirmation.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def mount_remove(ctx: click.Context, mount_id: str, target_file: Optional[Path], yes: bool, output_format: str) -> None:
        state = get_state(ctx)
        try:
            session = prepare_edit_session(state.config_path, target_file=target_file)
            app = CTSApp(
                session.loaded,
                active_profile=state.profile,
                explicit_config_path=str(state.config_path) if state.config_path else None,
                requested_profile=state.profile,
            )

            mount = app.catalog.find_by_id(mount_id)
            if not mount:
                raise RegistryError(f"mount not found: {mount_id}", code="mount_not_found")
            maybe_confirm(
                f"Remove mount '{mount_id}' from source '{mount.source_name}'?",
                assume_yes=yes,
                output_format=output_format,
            )
            with progress_steps(output_format, f"Removing mount '{mount_id}'", ["Validate target", "Write config"]) as progress:
                progress.advance("Validating target")

                def mutator(payload: Dict[str, Any]) -> None:
                    mounts = payload.get("mounts", [])
                    if not isinstance(mounts, list):
                        return
                    remaining = [m for m in mounts if not (isinstance(m, dict) and m.get("id") == mount_id)]
                    if len(remaining) == len(mounts):
                        return
                    if remaining:
                        payload["mounts"] = remaining
                    else:
                        payload.pop("mounts", None)

                progress.advance("Writing config")
                apply_update(session, mutator, compile_runtime=False)

            payload = {
                "ok": True,
                "action": "mount_remove",
                "mount_id": mount_id,
                "file": str(session.target_path),
                "source": mount.source_name,
                "operation_id": mount.operation.id,
                "next_command": "cts manage mount list",
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "mount_remove", output_format)

    @mount_group.command("import")
    @click.argument("source_name")
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write to a specific config file.")
    @click.option("--prefix", default=None, help="Mount ID prefix (default: source name).")
    @click.option("--under", "under_path", multiple=True, help="Command path prefix for all imported mounts.")
    @click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default=None, help="Override risk level for all operations.")
    @click.option("--filter", "operation_filter", multiple=True, help="Only import operations matching these IDs (supports wildcards).")
    @click.option("--exclude", "exclude_filter", multiple=True, help="Exclude operations matching these IDs (supports wildcards).")
    @click.option("--dry-run", is_flag=True, help="Preview what would be imported without making changes.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def mount_import(
        ctx: click.Context,
        source_name: str,
        target_file: Optional[Path],
        prefix: Optional[str],
        under_path: tuple[str, ...],
        risk: Optional[str],
        operation_filter: tuple[str, ...],
        exclude_filter: tuple[str, ...],
        dry_run: bool,
        output_format: str,
    ) -> None:
        state = get_state(ctx)
        try:
            session = prepare_edit_session(state.config_path, target_file=target_file)
            app = CTSApp(
                session.loaded,
                active_profile=state.profile,
                explicit_config_path=str(state.config_path) if state.config_path else None,
                requested_profile=state.profile,
            )

            if source_name not in app.config.sources:
                raise RegistryError(f"source not found: {source_name}", code="source_not_found")

            operations = app.source_operations.get(source_name, {})
            if not operations:
                with status(output_format, f"Discovering operations for source '{source_name}'..."):
                    app.sync(source_name)
                operations = app.source_operations.get(source_name, {})

            if not operations:
                raise RegistryError(
                    f"no operations found for source '{source_name}'",
                    code="no_operations",
                    suggestions=["确保 source 配置正确并能正常 discovery。"],
                )

            filtered_ops = []
            for op_id, op in list(operations.items()):
                if operation_filter and not any(fnmatch.fnmatch(op_id, pattern) for pattern in operation_filter):
                    continue
                if exclude_filter and any(fnmatch.fnmatch(op_id, pattern) for pattern in exclude_filter):
                    continue
                filtered_ops.append((op_id, op))

            if not filtered_ops:
                raise RegistryError("no operations match the specified filters", code="no_matching_operations")

            mount_prefix = prefix or source_name.replace("_", "-").replace(".", "-")
            under_tokens = list(under_path)
            new_mounts = []
            skipped_existing = []

            for op_id, op in filtered_ops:
                mount_id = f"{mount_prefix}-{op_id.replace('.', '-').replace('_', '-')}"
                if app.catalog.find_by_id(mount_id):
                    skipped_existing.append(mount_id)
                    continue

                command_path = tokenize_identifier(op_id)
                mount_entry = {
                    "id": mount_id,
                    "source": source_name,
                    "operation": op_id,
                }
                if command_path:
                    mount_entry["command"] = {"path": command_path}
                if under_tokens:
                    if "command" not in mount_entry:
                        mount_entry["command"] = {}
                    mount_entry["command"]["under"] = under_tokens
                if risk:
                    mount_entry["policy"] = {"risk": risk}
                elif op.risk and op.risk != "read":
                    mount_entry["policy"] = {"risk": op.risk}
                help_entry = {}
                if op.title:
                    help_entry["summary"] = op.title
                if op.description:
                    help_entry["description"] = op.description
                if help_entry:
                    mount_entry["help"] = help_entry
                new_mounts.append(mount_entry)

            if dry_run:
                payload = {
                    "ok": True,
                    "action": "mount_import_dry_run",
                    "source": source_name,
                    "total_operations": len(operations),
                    "filtered_operations": len(filtered_ops),
                    "mounts_to_create": len(new_mounts),
                    "skipped_existing": len(skipped_existing),
                    "mounts": new_mounts[:50],
                    "truncated": len(new_mounts) > 50,
                }
                click.echo(render_payload(payload, output_format))
                return

            if not new_mounts:
                raise RegistryError(
                    f"all {len(filtered_ops)} matching operations already have mounts",
                    code="all_mounts_exist",
                )

            baseline_conflicts = conflict_signatures(app.catalog.conflicts)

            def mutator(payload: Dict[str, Any]) -> None:
                mounts = payload.setdefault("mounts", [])
                if not isinstance(mounts, list):
                    raise RegistryError("mounts payload must be a list", code="mounts_payload_invalid")
                mounts.extend(new_mounts)

            with progress_steps(output_format, f"Importing mounts from '{source_name}'", ["Prepare mounts", "Compile config"]) as progress:
                progress.advance(f"Preparing {len(filtered_ops)} operation(s)")
                for idx, (op_id, op) in enumerate(filtered_ops, start=1):
                    progress.update_current(f"Preparing mounts ({idx}/{len(filtered_ops)}: {op_id})")
                progress.advance(f"Creating {len(new_mounts)} mount(s)")
                apply_update(
                    session,
                    mutator,
                    compile_runtime=True,
                    profile=state.profile,
                    baseline_conflicts=baseline_conflicts,
                )

            payload = {
                "ok": True,
                "action": "mount_import",
                "source": source_name,
                "file": str(session.target_path),
                "created_file": session.created,
                "total_operations": len(operations),
                "filtered_operations": len(filtered_ops),
                "mounts_created": len(new_mounts),
                "skipped_existing": skipped_existing,
                "mount_ids": [m["id"] for m in new_mounts],
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "mount_import", output_format)
