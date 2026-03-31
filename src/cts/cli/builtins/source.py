from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import click

from cts.cli.lazy import (
    CTSApp,
    apply_assignment,
    apply_update,
    build_app,
    build_source_check_result,
    build_source_details,
    build_source_summary,
    import_cli_completion,
    import_cli_help,
    import_cli_manpage,
    import_cli_schema,
    merge_operation_into_manifest,
    prepare_edit_session,
    render_payload,
)
from cts.execution.errors import RegistryError


def register_source_commands(
    source_group,
    *,
    pass_app,
    get_state: Callable,
    fail: Callable,
    maybe_confirm: Callable,
    progress_steps: Any,
    status: Callable,
    strip_internal_metadata: Callable,
    parse_assignment_value: Callable,
    parse_string_pair: Callable,
    emit_app_event: Callable,
) -> None:
    @source_group.command("add")
    @click.argument("provider_type")
    @click.argument("source_name")
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write into a specific loaded config file.")
    @click.option("--description", default=None)
    @click.option("--owner", default=None)
    @click.option("--tag", "tags", multiple=True, help="Repeatable source tag.")
    @click.option("--profile-scope", "profile_scopes", multiple=True, help="Repeatable profile scope.")
    @click.option("--auth-ref", default=None)
    @click.option("--auth-session", default=None)
    @click.option("--working-dir", type=click.Path(path_type=Path, file_okay=False), default=None)
    @click.option("--root", "root_dir", type=click.Path(path_type=Path, file_okay=False), default=None)
    @click.option("--bin", "executable", default=None, help="Executable for cli/shell sources.")
    @click.option("--base-url", default=None)
    @click.option("--endpoint", default=None)
    @click.option("--url", default=None, help="Remote endpoint for MCP or HTTP-like transports.")
    @click.option("--server", default=None, help="Named MCP server inside a config file.")
    @click.option("--config-file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="External config file, for example MCP server config.")
    @click.option("--transport-type", default=None)
    @click.option("--adapter", default=None)
    @click.option("--manifest", default=None, help="Discovery manifest path.")
    @click.option("--spec-url", default=None, help="OpenAPI spec URL.")
    @click.option("--spec-file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Local OpenAPI spec file.")
    @click.option("--schema-url", default=None, help="GraphQL introspection JSON URL.")
    @click.option("--schema-file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Local GraphQL introspection JSON file.")
    @click.option("--introspection", "introspection_mode", default=None, help="GraphQL schema introspection mode, for example live.")
    @click.option("--discover-mode", default=None, help="Override discovery.mode.")
    @click.option("--header", "headers", multiple=True, help="Repeatable header in key=value form.")
    @click.option("--env", "env_items", multiple=True, help="Repeatable env var in key=value form.")
    @click.option("--expose", "surfaces", multiple=True, help="Repeatable surface name.")
    @click.option("--pass-env/--no-pass-env", default=False, help="Whether to inherit current process env during execution.")
    @click.option("--enabled/--disabled", default=True)
    @click.option("--set", "assignments", multiple=True, help="Arbitrary source override, for example --set reliability.timeout_seconds=30.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def source_add(
        ctx: click.Context,
        provider_type: str,
        source_name: str,
        target_file: Optional[Path],
        description: Optional[str],
        owner: Optional[str],
        tags: tuple[str, ...],
        profile_scopes: tuple[str, ...],
        auth_ref: Optional[str],
        auth_session: Optional[str],
        working_dir: Optional[Path],
        root_dir: Optional[Path],
        executable: Optional[str],
        base_url: Optional[str],
        endpoint: Optional[str],
        url: Optional[str],
        server: Optional[str],
        config_file: Optional[Path],
        transport_type: Optional[str],
        adapter: Optional[str],
        manifest: Optional[str],
        spec_url: Optional[str],
        spec_file: Optional[Path],
        schema_url: Optional[str],
        schema_file: Optional[Path],
        introspection_mode: Optional[str],
        discover_mode: Optional[str],
        headers: tuple[str, ...],
        env_items: tuple[str, ...],
        surfaces: tuple[str, ...],
        pass_env: bool,
        enabled: bool,
        assignments: tuple[str, ...],
        output_format: str,
    ) -> None:
        state = get_state(ctx)
        try:
            with progress_steps(
                output_format,
                f"Adding source '{source_name}'",
                ["Validate provider", "Write config"],
            ) as progress:
                session = prepare_edit_session(state.config_path, target_file=target_file)
                available_types = CTSApp(
                    session.loaded,
                    active_profile=state.profile,
                    explicit_config_path=str(state.config_path) if state.config_path else None,
                    requested_profile=state.profile,
                ).provider_registry.supported_types()
                normalized_provider_type = provider_type.lower()
                progress.advance("Validating provider")
                if available_types and normalized_provider_type not in available_types:
                    raise RegistryError(
                        f"unsupported provider type: {provider_type}",
                        code="provider_type_unsupported",
                        suggestions=[
                            "检查是否已在配置中启用对应 plugin，或改用内置 provider。",
                            "当前可用 provider: " + ", ".join(sorted(available_types)),
                        ],
                    )
                if source_name in session.loaded.config.sources:
                    raise RegistryError(f"source already exists: {source_name}", code="source_exists")

                def mutator(payload: Dict[str, Any]) -> None:
                    sources = payload.setdefault("sources", {})
                    if not isinstance(sources, dict):
                        raise RegistryError("sources payload must be a mapping", code="sources_payload_invalid")
                    source_payload: Dict[str, Any] = {"type": normalized_provider_type, "enabled": enabled}
                    if description:
                        source_payload["description"] = description
                    if owner:
                        source_payload["owner"] = owner
                    if tags:
                        source_payload["tags"] = list(tags)
                    if profile_scopes:
                        source_payload["profile_scope"] = list(profile_scopes)
                    if auth_ref:
                        source_payload["auth_ref"] = auth_ref
                    if auth_session:
                        source_payload["auth_session"] = auth_session
                    if working_dir:
                        source_payload["working_dir"] = str(working_dir)
                    if root_dir:
                        source_payload["root"] = str(root_dir)
                    if executable:
                        source_payload["executable"] = executable
                    if base_url:
                        source_payload["base_url"] = base_url
                    if endpoint:
                        source_payload["endpoint"] = endpoint
                    if url:
                        source_payload["url"] = url
                    if server:
                        source_payload["server"] = server
                    if config_file:
                        source_payload["config_file"] = str(config_file)
                    if transport_type:
                        source_payload["transport_type"] = transport_type
                    if adapter:
                        source_payload["adapter"] = adapter
                    if spec_url or spec_file:
                        spec_payload: Dict[str, Any] = {}
                        if spec_url:
                            spec_payload["url"] = spec_url
                        if spec_file:
                            spec_payload["path"] = str(spec_file)
                        source_payload["spec"] = spec_payload
                    if schema_url or schema_file or introspection_mode:
                        schema_payload: Dict[str, Any] = {}
                        if schema_url:
                            schema_payload["url"] = schema_url
                        if schema_file:
                            schema_payload["path"] = str(schema_file)
                        if introspection_mode:
                            schema_payload["introspection"] = introspection_mode
                        source_payload["schema"] = schema_payload
                    if surfaces:
                        source_payload["expose_to_surfaces"] = list(surfaces)
                    if pass_env:
                        source_payload["pass_env"] = True
                    if manifest or discover_mode:
                        discovery_payload: Dict[str, Any] = {}
                        if manifest:
                            discovery_payload["manifest"] = manifest
                        if discover_mode:
                            discovery_payload["mode"] = discover_mode
                        source_payload["discovery"] = discovery_payload
                    if headers:
                        source_payload["headers"] = {key: value for key, value in (parse_string_pair(item, field_name="header") for item in headers)}
                    if env_items:
                        source_payload["env"] = {key: value for key, value in (parse_string_pair(item, field_name="env") for item in env_items)}
                    for assignment in assignments:
                        path, value = parse_assignment_value(assignment)
                        apply_assignment(source_payload, path, value)
                    sources[source_name] = source_payload

                progress.advance("Writing config")
                updated, _ = apply_update(session, mutator, compile_runtime=False)
            payload = {
                "ok": True,
                "action": "source_add",
                "source": source_name,
                "provider_type": normalized_provider_type,
                "file": str(session.target_path),
                "created_file": session.created,
                "warnings": list(session.warnings),
                "next_commands": [
                    f"cts source show {source_name}",
                    f"cts source test {source_name}",
                ],
                "config": strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "source_add", output_format)

    @source_group.command("list")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def source_list(app, output_format: str) -> None:
        payload = {"items": [build_source_summary(app, name, source) for name, source in app.config.sources.items()]}
        click.echo(render_payload(payload, output_format))

    @source_group.command("show")
    @click.argument("source_name")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def source_show(app, source_name: str, output_format: str) -> None:
        source = app.config.sources.get(source_name)
        if not source:
            fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "show_source", output_format)
            return
        payload = build_source_details(app, source_name, source)
        payload["next_commands"] = [
            f"cts source test {source_name}",
            f"cts mount import {source_name} --dry-run",
        ]
        click.echo(render_payload(payload, output_format))

    @source_group.command("test")
    @click.argument("source_name")
    @click.option("--discover", is_flag=True, help="Also run source discovery and report discovered operation count.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def source_test(app, source_name: str, discover: bool, output_format: str) -> None:
        source = app.config.sources.get(source_name)
        if not source:
            fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "test_source", output_format)
            return
        payload = build_source_check_result(app, source_name, source)
        if discover:
            with status(output_format, f"Running discovery for source '{source_name}'..."):
                sync_result = app.sync(source_name)
            sync_items = sync_result.get("items", [])
            payload["discovery"] = sync_items[0] if sync_items else {"ok": False, "source": source_name, "operation_count": 0}
            payload["discovery_report_path"] = sync_result.get("report_path")
            payload["capability_snapshot_path"] = sync_result.get("capability_snapshot_path")
            payload["ok"] = payload["ok"] and payload["discovery"].get("ok", False)
        click.echo(render_payload(payload, output_format))
        if not payload["ok"]:
            click.get_current_context().exit(6)

    @source_group.command("remove")
    @click.argument("source_name")
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Remove from a specific config file.")
    @click.option("--force", is_flag=True, help="Force removal even if mounts depend on this source.")
    @click.option("--yes", is_flag=True, help="Skip interactive confirmation.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def source_remove(
        ctx: click.Context,
        source_name: str,
        target_file: Optional[Path],
        force: bool,
        yes: bool,
        output_format: str,
    ) -> None:
        state = get_state(ctx)
        try:
            with progress_steps(
                output_format,
                f"Preparing source removal for '{source_name}'",
                ["Load configuration", "Analyze dependent mounts", "Prepare confirmation"],
            ) as progress:
                progress.advance("Loading configuration")
                session = prepare_edit_session(state.config_path, target_file=target_file)
                app = CTSApp(
                    session.loaded,
                    active_profile=state.profile,
                    explicit_config_path=str(state.config_path) if state.config_path else None,
                    requested_profile=state.profile,
                )

                if source_name not in app.config.sources:
                    raise RegistryError(f"source not found: {source_name}", code="source_not_found")

                progress.advance("Analyzing dependent mounts")
                dependent_mounts = [mount for mount in app.catalog.mounts if mount.source_name == source_name]

                progress.advance("Preparing confirmation")
            if dependent_mounts and not force:
                raise RegistryError(
                    f"source '{source_name}' has {len(dependent_mounts)} dependent mount(s)",
                    code="source_has_dependents",
                    suggestions=[
                        "使用 --force 强制删除（同时删除依赖的 mount）",
                        f"先手动删除依赖的 mount: {', '.join(m.mount_id for m in dependent_mounts[:5])}",
                    ],
                )
            mount_preview = ", ".join(m.mount_id for m in dependent_mounts[:5])
            maybe_confirm(
                (
                    f"Remove source '{source_name}'"
                    + (f" and {len(dependent_mounts)} dependent mount(s)" if dependent_mounts else "")
                    + (f" [{mount_preview}]" if mount_preview else "")
                    + "?"
                ),
                assume_yes=yes,
                output_format=output_format,
            )

            def mutator(payload: Dict[str, Any]) -> None:
                sources = payload.get("sources", {})
                if source_name in sources:
                    del sources[source_name]
                if not sources:
                    payload.pop("sources", None)

                if dependent_mounts:
                    mounts = payload.get("mounts", [])
                    if isinstance(mounts, list):
                        remaining = [
                            m for m in mounts
                            if not (isinstance(m, dict) and m.get("source") == source_name)
                        ]
                        if remaining:
                            payload["mounts"] = remaining
                        else:
                            payload.pop("mounts", None)

            with progress_steps(
                output_format,
                f"Removing source '{source_name}'",
                ["Validate dependencies", "Write config"],
            ) as progress:
                progress.advance("Validating dependencies")
                progress.advance("Writing config")
                apply_update(session, mutator, compile_runtime=False)

            payload = {
                "ok": True,
                "action": "source_remove",
                "source_name": source_name,
                "file": str(session.target_path),
                "removed_mounts": [m.mount_id for m in dependent_mounts] if dependent_mounts else [],
                "next_command": "cts source list",
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "source_remove", output_format)

    def _resolve_source_import_context(app, source_name: str, manifest_path: Optional[Path], stage: str, output_format: str):
        source = app.config.sources.get(source_name)
        if not source:
            fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), stage, output_format)
            return None, None
        if source.type not in {"cli", "shell"}:
            fail(
                click.get_current_context(),
                RegistryError(
                    f"source '{source_name}' is not a cli/shell source",
                    code="source_type_not_supported",
                    suggestions=["使用 `cli` 或 `shell` source，或改用对应 provider 的导入方式。"],
                ),
                stage,
                output_format,
            )
            return None, None

        resolved_manifest = manifest_path
        if resolved_manifest is None and source.discovery.manifest:
            resolved_manifest = app.resolve_path(source.discovery.manifest, owner=source)
        if resolved_manifest is None:
            fail(
                click.get_current_context(),
                RegistryError(
                    f"source '{source_name}' has no discovery.manifest configured",
                    code="manifest_path_required",
                    suggestions=["先在 source 上配置 discovery.manifest，或执行命令时显式传入 --manifest。"],
                ),
                stage,
                output_format,
            )
            return None, None
        return source, resolved_manifest

    def _finalize_source_command(source, command_argv: tuple[str, ...], stage: str, output_format: str):
        final_command = list(command_argv)
        if not final_command:
            if source.executable:
                final_command = [source.executable]
            else:
                fail(
                    click.get_current_context(),
                    RegistryError(
                        "command argv required when source.executable is not configured",
                        code="command_argv_required",
                    ),
                    stage,
                    output_format,
                )
                return None
        elif source.executable and final_command[0] != source.executable:
            final_command = [source.executable] + final_command
        return final_command

    @source_group.command("import-help")
    @click.argument("source_name")
    @click.argument("operation_id")
    @click.argument("command_argv", nargs=-1)
    @click.option("--manifest", "manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Override the manifest file to write.")
    @click.option("--help-flag", default="--help", show_default=True)
    @click.option("--title", default=None)
    @click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
    @click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def source_import_help(app, source_name: str, operation_id: str, command_argv: tuple[str, ...], manifest_path: Optional[Path], help_flag: str, title: Optional[str], risk: str, output_mode: str, output_format: str) -> None:
        source, resolved_manifest = _resolve_source_import_context(app, source_name, manifest_path, "source_import_help", output_format)
        if source is None:
            return
        final_command = _finalize_source_command(source, command_argv, "source_import_help", output_format)
        if final_command is None:
            return
        try:
            with progress_steps(output_format, f"Importing help for '{source_name}.{operation_id}'", ["Inspect help output", "Write manifest", "Rebuild catalog"]) as progress:
                progress.advance("Inspecting help output")
                result = import_cli_help(
                    operation_id=operation_id,
                    command_argv=final_command,
                    help_flag=help_flag,
                    risk=risk,
                    output_mode=output_mode,
                    title=title,
                )
                progress.advance("Writing manifest")
                manifest_payload = merge_operation_into_manifest(
                    resolved_manifest,
                    result.operation,
                    executable=source.executable or (final_command[0] if final_command else None),
                )
                progress.advance("Rebuilding catalog")
                next_app = build_app(app.explicit_config_path, profile=app.requested_profile)
                compiled_operation = next_app.source_operations.get(source_name, {}).get(operation_id)
            payload = {
                "ok": True,
                "action": "source_import_help",
                "source": source_name,
                "operation_id": operation_id,
                "manifest_path": str(resolved_manifest),
                "command_argv": final_command,
                "help_command": result.help_command,
                "manifest_operation_count": len(manifest_payload.get("operations", [])),
                "imported_operation": result.operation,
                "compiled_operation": compiled_operation.model_dump(mode="json") if compiled_operation else None,
            }
            emit_app_event(
                app,
                event="cli_help_import_complete",
                source=source_name,
                operation_id=operation_id,
                data={"manifest_path": str(resolved_manifest), "command_argv": final_command},
            )
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "source_import_help", output_format)

    @source_group.command("import-completion")
    @click.argument("source_name")
    @click.argument("operation_id")
    @click.argument("command_argv", nargs=-1)
    @click.option("--completion-command", default=None, help="Shell-escaped command that prints completion candidates.")
    @click.option("--completion-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
    @click.option("--completion-format", type=click.Choice(["lines", "fish", "json"]), default="lines", show_default=True)
    @click.option("--manifest", "manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Override the manifest file to write.")
    @click.option("--title", default=None)
    @click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
    @click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def source_import_completion(app, source_name: str, operation_id: str, command_argv: tuple[str, ...], completion_command: Optional[str], completion_file: Optional[Path], completion_format: str, manifest_path: Optional[Path], title: Optional[str], risk: str, output_mode: str, output_format: str) -> None:
        source, resolved_manifest = _resolve_source_import_context(app, source_name, manifest_path, "source_import_completion", output_format)
        if source is None:
            return
        if not completion_command and completion_file is None:
            fail(click.get_current_context(), RegistryError("completion source required", code="completion_source_required", suggestions=["传入 --completion-command 或 --completion-file。"]), "source_import_completion", output_format)
            return
        final_command = _finalize_source_command(source, command_argv, "source_import_completion", output_format)
        if final_command is None:
            return
        parsed_completion_command = shlex.split(completion_command) if completion_command else None
        try:
            with progress_steps(output_format, f"Importing completion for '{source_name}.{operation_id}'", ["Read completion source", "Write manifest", "Rebuild catalog"]) as progress:
                progress.advance("Reading completion source")
                result = import_cli_completion(
                    operation_id=operation_id,
                    command_argv=final_command,
                    completion_command=parsed_completion_command,
                    completion_file=completion_file,
                    completion_format=completion_format,
                    risk=risk,
                    output_mode=output_mode,
                    title=title,
                )
                progress.advance("Writing manifest")
                manifest_payload = merge_operation_into_manifest(
                    resolved_manifest,
                    result.operation,
                    executable=source.executable or (final_command[0] if final_command else None),
                )
                progress.advance("Rebuilding catalog")
                next_app = build_app(app.explicit_config_path, profile=app.requested_profile)
                compiled_operation = next_app.source_operations.get(source_name, {}).get(operation_id)
            payload = {
                "ok": True,
                "action": "source_import_completion",
                "source": source_name,
                "operation_id": operation_id,
                "manifest_path": str(resolved_manifest),
                "command_argv": final_command,
                "completion_command": parsed_completion_command,
                "completion_file": str(completion_file) if completion_file else None,
                "completion_format": completion_format,
                "manifest_operation_count": len(manifest_payload.get("operations", [])),
                "imported_operation": result.operation,
                "compiled_operation": compiled_operation.model_dump(mode="json") if compiled_operation else None,
            }
            emit_app_event(
                app,
                event="cli_completion_import_complete",
                source=source_name,
                operation_id=operation_id,
                data={
                    "manifest_path": str(resolved_manifest),
                    "command_argv": final_command,
                    "completion_command": parsed_completion_command,
                    "completion_file": str(completion_file) if completion_file else None,
                    "completion_format": completion_format,
                },
            )
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "source_import_completion", output_format)

    @source_group.command("import-manpage")
    @click.argument("source_name")
    @click.argument("operation_id")
    @click.argument("command_argv", nargs=-1)
    @click.option("--man-command", default=None, help="Shell-escaped command that prints a plain-text man page.")
    @click.option("--man-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
    @click.option("--manifest", "manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Override the manifest file to write.")
    @click.option("--title", default=None)
    @click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
    @click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def source_import_manpage(app, source_name: str, operation_id: str, command_argv: tuple[str, ...], man_command: Optional[str], man_file: Optional[Path], manifest_path: Optional[Path], title: Optional[str], risk: str, output_mode: str, output_format: str) -> None:
        source, resolved_manifest = _resolve_source_import_context(app, source_name, manifest_path, "source_import_manpage", output_format)
        if source is None:
            return
        if not man_command and man_file is None:
            fail(click.get_current_context(), RegistryError("man page source required", code="manpage_source_required", suggestions=["传入 --man-command 或 --man-file。"]), "source_import_manpage", output_format)
            return
        final_command = _finalize_source_command(source, command_argv, "source_import_manpage", output_format)
        if final_command is None:
            return
        parsed_man_command = shlex.split(man_command) if man_command else None
        try:
            with progress_steps(output_format, f"Importing man page for '{source_name}.{operation_id}'", ["Read man page", "Write manifest", "Rebuild catalog"]) as progress:
                progress.advance("Reading man page")
                result = import_cli_manpage(
                    operation_id=operation_id,
                    command_argv=final_command,
                    man_command=parsed_man_command,
                    man_file=man_file,
                    risk=risk,
                    output_mode=output_mode,
                    title=title,
                )
                progress.advance("Writing manifest")
                manifest_payload = merge_operation_into_manifest(
                    resolved_manifest,
                    result.operation,
                    executable=source.executable or (final_command[0] if final_command else None),
                )
                progress.advance("Rebuilding catalog")
                next_app = build_app(app.explicit_config_path, profile=app.requested_profile)
                compiled_operation = next_app.source_operations.get(source_name, {}).get(operation_id)
            payload = {
                "ok": True,
                "action": "source_import_manpage",
                "source": source_name,
                "operation_id": operation_id,
                "manifest_path": str(resolved_manifest),
                "command_argv": final_command,
                "man_command": result.man_command,
                "manifest_operation_count": len(manifest_payload.get("operations", [])),
                "imported_operation": result.operation,
                "compiled_operation": compiled_operation.model_dump(mode="json") if compiled_operation else None,
            }
            emit_app_event(
                app,
                event="cli_manpage_import_complete",
                source=source_name,
                operation_id=operation_id,
                data={"manifest_path": str(resolved_manifest), "command_argv": final_command},
            )
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "source_import_manpage", output_format)

    @source_group.command("import-schema")
    @click.argument("source_name")
    @click.argument("operation_id")
    @click.argument("command_argv", nargs=-1)
    @click.option("--schema-command", default=None, help="Shell-escaped command that prints a JSON schema payload.")
    @click.option("--schema-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
    @click.option("--schema-format", type=click.Choice(["auto", "operation", "bindings", "options"]), default="auto", show_default=True)
    @click.option("--manifest", "manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Override the manifest file to write.")
    @click.option("--title", default=None)
    @click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
    @click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def source_import_schema(app, source_name: str, operation_id: str, command_argv: tuple[str, ...], schema_command: Optional[str], schema_file: Optional[Path], schema_format: str, manifest_path: Optional[Path], title: Optional[str], risk: str, output_mode: str, output_format: str) -> None:
        source, resolved_manifest = _resolve_source_import_context(app, source_name, manifest_path, "source_import_schema", output_format)
        if source is None:
            return
        if not schema_command and schema_file is None:
            fail(click.get_current_context(), RegistryError("schema source required", code="schema_source_required", suggestions=["传入 --schema-command 或 --schema-file。"]), "source_import_schema", output_format)
            return
        final_command = _finalize_source_command(source, command_argv, "source_import_schema", output_format)
        if final_command is None:
            return
        parsed_schema_command = shlex.split(schema_command) if schema_command else None
        try:
            with progress_steps(output_format, f"Importing schema for '{source_name}.{operation_id}'", ["Read schema", "Write manifest", "Rebuild catalog"]) as progress:
                progress.advance("Reading schema")
                result = import_cli_schema(
                    operation_id=operation_id,
                    command_argv=final_command,
                    schema_command=parsed_schema_command,
                    schema_file=schema_file,
                    schema_format=schema_format,
                    risk=risk,
                    output_mode=output_mode,
                    title=title,
                )
                progress.advance("Writing manifest")
                manifest_payload = merge_operation_into_manifest(
                    resolved_manifest,
                    result.operation,
                    executable=source.executable or (final_command[0] if final_command else None),
                )
                progress.advance("Rebuilding catalog")
                next_app = build_app(app.explicit_config_path, profile=app.requested_profile)
                compiled_operation = next_app.source_operations.get(source_name, {}).get(operation_id)
            payload = {
                "ok": True,
                "action": "source_import_schema",
                "source": source_name,
                "operation_id": operation_id,
                "manifest_path": str(resolved_manifest),
                "command_argv": final_command,
                "schema_command": result.schema_command,
                "schema_payload": result.schema_payload,
                "manifest_operation_count": len(manifest_payload.get("operations", [])),
                "imported_operation": result.operation,
                "compiled_operation": compiled_operation.model_dump(mode="json") if compiled_operation else None,
            }
            emit_app_event(
                app,
                event="cli_schema_import_complete",
                source=source_name,
                operation_id=operation_id,
                data={"manifest_path": str(resolved_manifest), "command_argv": final_command, "schema_format": schema_format},
            )
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "source_import_schema", output_format)
