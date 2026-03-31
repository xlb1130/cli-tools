from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import click


def register_import_commands(
    import_group,
    *,
    get_state: Callable,
    progress_steps: Callable,
    fail: Callable,
    prepare_edit_session: Callable,
    app_factory: Callable,
    prepare_cli_import_plan: Callable,
    prepare_cli_import_tree_plan: Callable,
    apply_cli_import_plan: Callable,
    apply_cli_import_tree_plan: Callable,
    execute_import_shell: Callable,
    execute_import_mcp: Callable,
    render_payload: Callable,
    write_manifest_operations: Callable,
    merge_operation_into_manifest: Callable,
    apply_update: Callable,
    conflict_signatures: Callable,
    strip_internal_metadata: Callable,
    find_mount_payload: Callable,
    build_mount_details: Callable,
    derive_operation_id_from_command: Callable,
) -> None:
    @import_group.command("cli")
    @click.argument("source_name")
    @click.argument("command_argv", nargs=-1)
    @click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write into a specific loaded config file.")
    @click.option("--operation-id", default=None, help="Operation id. Defaults to a name derived from the command.")
    @click.option("--from", "import_strategy", type=click.Choice(["help", "completion", "manpage", "schema"]), default="help", show_default=True)
    @click.option("--bin", "executable", default=None, help="Executable to store on the source. Defaults to the first command token.")
    @click.option("--title", default=None)
    @click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
    @click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
    @click.option("--help-flag", default="--help", show_default=True)
    @click.option("--completion-command", default=None, help="Shell-escaped command that prints completion candidates.")
    @click.option("--completion-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
    @click.option("--completion-format", type=click.Choice(["lines", "fish", "json"]), default="lines", show_default=True)
    @click.option("--man-command", default=None, help="Shell-escaped command that prints a plain-text man page.")
    @click.option("--man-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
    @click.option("--schema-command", default=None, help="Shell-escaped command that prints a JSON schema payload.")
    @click.option("--schema-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
    @click.option("--schema-format", type=click.Choice(["auto", "operation", "bindings", "options"]), default="auto", show_default=True)
    @click.option("--all", "import_all", is_flag=True, help="Recursively import the full CLI command tree using nested help output.")
    @click.option("--apply", is_flag=True, help="Write the imported source operation and mount into config.")
    @click.option("--save-manifest", "save_manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Optional manifest file to write instead of storing the operation inline.")
    @click.option("--mount/--no-mount", "create_mount", default=True, show_default=True, help="Also create a mount for the imported operation.")
    @click.option("--mount-id", default=None, help="Mount id override. Defaults to an auto-generated stable id.")
    @click.option("--path", "command_path_value", default=None, help="Full mount command path. Defaults to '<source> <operation>'.")
    @click.option("--under", "under_values", multiple=True, help="Command path prefix used together with the operation tokens.")
    @click.option("--prefix", default=None, help="Mount id prefix. Defaults to the source name.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def import_cli_command(
        ctx: click.Context,
        source_name: str,
        command_argv: tuple[str, ...],
        target_file: Optional[Path],
        operation_id: Optional[str],
        import_strategy: str,
        executable: Optional[str],
        title: Optional[str],
        risk: str,
        output_mode: str,
        help_flag: str,
        completion_command: Optional[str],
        completion_file: Optional[Path],
        completion_format: str,
        man_command: Optional[str],
        man_file: Optional[Path],
        schema_command: Optional[str],
        schema_file: Optional[Path],
        schema_format: str,
        import_all: bool,
        apply: bool,
        save_manifest_path: Optional[Path],
        create_mount: bool,
        mount_id: Optional[str],
        command_path_value: Optional[str],
        under_values: tuple[str, ...],
        prefix: Optional[str],
        output_format: str,
    ) -> None:
        state = get_state(ctx)
        try:
            session = prepare_edit_session(state.config_path, target_file=target_file)
            app = app_factory(session.loaded, state.profile, state.config_path)
            if import_all:
                if import_strategy != "help":
                    raise ValueError("--all currently supports --from help only")
                if operation_id is not None or mount_id is not None or command_path_value is not None or title is not None:
                    raise ValueError("--all cannot be combined with per-command identity overrides")
                tree_steps = ["Inspect root command", "Discover subcommands", "Import leaf operations"]
                if create_mount:
                    tree_steps.append("Prepare mounts")
                if apply:
                    tree_steps.extend(["Write manifest", "Compile config"])
                with progress_steps(output_format, f"Importing CLI tree '{source_name}'", tree_steps) as progress:
                    phase_state = {"discovering": False, "importing": False}

                    def report_tree_progress(stage: str, details: Dict[str, Any]) -> None:
                        if stage == "inspect_root":
                            progress.advance("Inspecting root command")
                            return
                        if stage == "discover_subcommands":
                            if not phase_state["discovering"]:
                                progress.advance("Discovering subcommands")
                                phase_state["discovering"] = True
                            progress.update_current(
                                "Discovering subcommands"
                                f" ({details.get('visited', 0)} visited, {details.get('queued', 0)} queued, {details.get('leaves', 0)} leaves)"
                            )
                            return
                        if stage == "import_leaf_operations":
                            if not phase_state["importing"]:
                                progress.advance("Importing leaf operations")
                                phase_state["importing"] = True
                            progress.update_current(
                                "Importing leaf operations"
                                f" ({details.get('current', 0)}/{details.get('total', 0)}: {details.get('operation_id', '-')})"
                            )
                            return
                        if stage == "prepare_mounts":
                            if not phase_state.get("preparing_mounts"):
                                progress.advance("Preparing mounts")
                                phase_state["preparing_mounts"] = True
                            progress.update_current(
                                "Preparing mounts"
                                f" ({details.get('current', 0)}/{details.get('total', 0)}: {details.get('operation_id', '-')})"
                            )

                    plan = prepare_cli_import_tree_plan(
                        app,
                        source_name=source_name,
                        command_argv=list(command_argv),
                        executable=executable,
                        risk=risk,
                        output_mode=output_mode,
                        help_flag=help_flag,
                        create_mount=create_mount,
                        under_values=under_values,
                        prefix=prefix,
                        save_manifest_path=save_manifest_path,
                        progress_callback=report_tree_progress,
                    )
                    if not apply:
                        click.echo(render_payload({"ok": True, "action": "import_cli_tree_preview", **plan}, output_format))
                        return

                    progress.advance("Writing manifest")
                    manifest_write = dict(plan["manifest_write"])
                    write_manifest_operations(
                        Path(manifest_write["resolved_path"]),
                        list(manifest_write["operations"]),
                        executable=manifest_write.get("executable"),
                    )

                    progress.advance("Compiling config")
                    baseline_conflicts = conflict_signatures(app.catalog.conflicts)

                    def mutator(payload: Dict[str, Any]) -> None:
                        apply_cli_import_tree_plan(payload, plan)

                    updated, _compiled_app = apply_update(
                        session,
                        mutator,
                        compile_runtime=True,
                        profile=state.profile,
                        baseline_conflicts=baseline_conflicts,
                    )

                click.echo(
                    render_payload(
                        {
                            "ok": True,
                            "action": "import_cli_tree_apply",
                            "file": str(session.target_path),
                            "created_file": session.created,
                            "warnings": list(session.warnings),
                            **plan,
                            "source_config": strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
                            "mount_count": len(plan.get("mounts") or []),
                            "operation_count": len(plan.get("operations") or []),
                        },
                        output_format,
                    )
                )
                return

            plan = prepare_cli_import_plan(
                app,
                source_name=source_name,
                command_argv=list(command_argv),
                operation_id=operation_id,
                import_strategy=import_strategy,
                executable=executable,
                title=title,
                risk=risk,
                output_mode=output_mode,
                help_flag=help_flag,
                completion_command=completion_command,
                completion_file=completion_file,
                completion_format=completion_format,
                man_command=man_command,
                man_file=man_file,
                schema_command=schema_command,
                schema_file=schema_file,
                schema_format=schema_format,
                create_mount=create_mount,
                mount_id=mount_id,
                command_path_value=command_path_value,
                under_values=under_values,
                prefix=prefix,
                save_manifest_path=save_manifest_path,
            )

            if not apply:
                click.echo(render_payload({"ok": True, "action": "import_cli_preview", **plan}, output_format))
                return

            cli_steps = ["Compile config"]
            if plan.get("manifest_write"):
                cli_steps.insert(0, "Write manifest")
            with progress_steps(output_format, f"Importing CLI command '{source_name}'", cli_steps) as progress:
                if plan.get("manifest_write"):
                    progress.advance("Writing manifest")
                    manifest_write = dict(plan["manifest_write"])
                    merge_operation_into_manifest(
                        Path(manifest_write["resolved_path"]),
                        dict(manifest_write["operation"]),
                        executable=manifest_write.get("executable"),
                    )

                progress.advance("Compiling config")
                baseline_conflicts = conflict_signatures(app.catalog.conflicts)

                def mutator(payload: Dict[str, Any]) -> None:
                    apply_cli_import_plan(payload, plan)

                updated, compiled_app = apply_update(
                    session,
                    mutator,
                    compile_runtime=True,
                    profile=state.profile,
                    baseline_conflicts=baseline_conflicts,
                )

            compiled_mount = None
            if compiled_app and plan.get("mount"):
                compiled_mount = compiled_app.catalog.find_by_id(plan["mount"]["id"])
            payload = {
                "ok": True,
                "action": "import_cli_apply",
                "file": str(session.target_path),
                "created_file": session.created,
                "warnings": list(session.warnings),
                **plan,
                "source_config": strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
                "mount_config": find_mount_payload(updated.get("mounts", []), plan["mount"]["id"]) if plan.get("mount") else None,
                "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "import_cli", output_format)

    @import_group.command("shell")
    @click.argument("source_name")
    @click.option("--exec", "exec_command", default=None, help="Shell command string to execute.")
    @click.option("--script-file", type=click.Path(path_type=Path, exists=True, dir_okay=False), default=None, help="Path to a shell script file to execute.")
    @click.option("--shell-bin", default="/bin/sh", show_default=True, help="Shell executable used to run the command.")
    @click.option("--under", "under_values", multiple=True, help="Command path prefix for the generated mount.")
    @click.option("--title", default=None, help="Optional operation title.")
    @click.option("--description", default=None, help="Optional operation description.")
    @click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
    @click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
    @click.option("--apply", is_flag=True, help="Write the shell source and mount into config.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def import_shell_command(
        ctx: click.Context,
        source_name: str,
        exec_command: Optional[str],
        script_file: Optional[Path],
        shell_bin: str,
        under_values: tuple[str, ...],
        title: Optional[str],
        description: Optional[str],
        risk: str,
        output_mode: str,
        apply: bool,
        output_format: str,
    ) -> None:
        try:
            if bool(exec_command) == bool(script_file):
                raise ValueError("exactly one of --exec or --script-file is required")
            with progress_steps(
                output_format,
                f"Importing shell source '{source_name}'",
                ["Prepare import plan", "Apply config"] if apply else ["Prepare import plan"],
            ) as progress:
                progress.advance("Preparing import plan")
                payload = execute_import_shell(
                    ctx,
                    source_name=source_name,
                    exec_command=exec_command,
                    script_file=script_file,
                    shell_bin=shell_bin,
                    under_values=under_values,
                    title=title,
                    description=description,
                    risk=risk,
                    output_mode=output_mode,
                    apply=apply,
                )
                if apply:
                    progress.advance("Applying config")
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "import_shell", output_format)

    @import_group.command("mcp")
    @click.argument("source_name")
    @click.option("--server-config", type=str, help="MCP server configuration as JSON string.")
    @click.option("--server-name", type=str, help="Server name in the servers.json file.")
    @click.option("--config-file", type=click.Path(path_type=Path), default=None, help="Path to servers.json. Defaults to ./servers.json.")
    @click.option("--under", "under_values", multiple=True, help="Command path prefix for all imported mounts.")
    @click.option("--apply", is_flag=True, help="Apply the MCP source and import all tools as mounts.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def import_mcp_command(
        ctx: click.Context,
        source_name: str,
        server_config: Optional[str],
        server_name: Optional[str],
        config_file: Optional[Path],
        under_values: tuple[str, ...],
        apply: bool,
        output_format: str,
    ) -> None:
        try:
            with progress_steps(
                output_format,
                f"Importing MCP source '{source_name}'",
                ["Prepare import plan", "Write server config", "Compile source config", "Discover tools", "Create mounts"] if apply else ["Prepare import plan"],
            ) as progress:
                progress.advance("Preparing import plan")
                payload = execute_import_mcp(
                    ctx,
                    source_name=source_name,
                    server_config=server_config,
                    server_name=server_name,
                    config_file=config_file,
                    under_values=under_values,
                    apply=apply,
                    progress=progress if apply else None,
                )
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "import_mcp", output_format)

    @import_group.command("wizard")
    @click.option("--apply", is_flag=True, help="Write the imported source operation and mount into config after the wizard.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def import_wizard(ctx: click.Context, apply: bool, output_format: str) -> None:
        """Interactive wizard for simplified imports."""
        import_type = click.prompt("Import type", type=click.Choice(["cli", "mcp"]), default="cli", show_choices=False)
        if import_type == "mcp":
            source_name = click.prompt("Source name")
            server_config = click.prompt("Server config JSON (optional)", default="", show_default=False).strip() or None
            server_name = click.prompt("Server name (optional)", default="", show_default=False).strip() or None
            config_file_raw = click.prompt("servers.json path (optional)", default="", show_default=False).strip()
            under_raw = click.prompt("Command prefix (optional)", default="", show_default=False).strip()
            should_apply = apply or click.confirm("Apply changes now?", default=False)
            with progress_steps(
                output_format,
                f"Wizard import for MCP source '{source_name}'",
                ["Prepare import plan", "Write server config", "Compile source config", "Discover tools", "Create mounts"] if should_apply else ["Prepare import plan"],
            ) as progress:
                progress.advance("Preparing import plan")
                payload = execute_import_mcp(
                    ctx,
                    source_name=source_name,
                    server_config=server_config,
                    server_name=server_name,
                    config_file=Path(config_file_raw) if config_file_raw else None,
                    under_values=tuple(shlex.split(under_raw)) if under_raw else (),
                    apply=should_apply,
                    progress=progress if should_apply else None,
                )
            click.echo(render_payload(payload, output_format))
            return

        source_name = click.prompt("Source name")
        command_text = click.prompt("Command argv", prompt_suffix=": ")
        import_strategy = click.prompt("Import strategy", type=click.Choice(["help", "completion", "manpage", "schema"]), default="help", show_choices=False)
        operation_id = click.prompt("Operation id", default=derive_operation_id_from_command(shlex.split(command_text)))
        title = click.prompt("Title", default="", show_default=False)
        risk = click.prompt("Risk level", type=click.Choice(["read", "write", "destructive"]), default="read", show_choices=False)
        output_mode = click.prompt("Output mode", type=click.Choice(["text", "json"]), default="text", show_choices=False)
        save_manifest_raw = click.prompt("Save manifest path (optional)", default="", show_default=False)

        extra_args: List[str] = []
        if import_strategy == "help":
            help_flag = click.prompt("Help flag", default="--help")
            extra_args.extend(["--help-flag", help_flag])
        elif import_strategy == "completion":
            completion_command = click.prompt("Completion command", default="", show_default=False)
            completion_file = click.prompt("Completion file (optional)", default="", show_default=False)
            if completion_command:
                extra_args.extend(["--completion-command", completion_command])
            if completion_file:
                extra_args.extend(["--completion-file", completion_file])
        elif import_strategy == "manpage":
            man_command = click.prompt("Manpage command", default="", show_default=False)
            man_file = click.prompt("Manpage file (optional)", default="", show_default=False)
            if man_command:
                extra_args.extend(["--man-command", man_command])
            if man_file:
                extra_args.extend(["--man-file", man_file])
        else:
            schema_command = click.prompt("Schema command", default="", show_default=False)
            schema_file = click.prompt("Schema file (optional)", default="", show_default=False)
            if schema_command:
                extra_args.extend(["--schema-command", schema_command])
            if schema_file:
                extra_args.extend(["--schema-file", schema_file])

        should_apply = apply or click.confirm("Apply changes now?", default=False)
        state = get_state(ctx)
        session = prepare_edit_session(state.config_path)
        app = app_factory(session.loaded, state.profile, state.config_path)
        extra: Dict[str, Any] = {
            "help_flag": "--help",
            "completion_command": None,
            "completion_file": None,
            "completion_format": "lines",
            "man_command": None,
            "man_file": None,
            "schema_command": None,
            "schema_file": None,
            "schema_format": "auto",
        }
        for index in range(0, len(extra_args), 2):
            key = extra_args[index].lstrip("-").replace("-", "_")
            value = extra_args[index + 1]
            extra[key] = Path(value) if key.endswith("_file") else value

        plan = prepare_cli_import_plan(
            app,
            source_name=source_name,
            command_argv=shlex.split(command_text),
            operation_id=operation_id,
            import_strategy=import_strategy,
            executable=None,
            title=title or None,
            risk=risk,
            output_mode=output_mode,
            help_flag=str(extra["help_flag"]),
            completion_command=extra["completion_command"],
            completion_file=extra["completion_file"],
            completion_format=str(extra["completion_format"]),
            man_command=extra["man_command"],
            man_file=extra["man_file"],
            schema_command=extra["schema_command"],
            schema_file=extra["schema_file"],
            schema_format=str(extra["schema_format"]),
            create_mount=True,
            mount_id=None,
            command_path_value=None,
            under_values=(),
            prefix=None,
            save_manifest_path=Path(save_manifest_raw) if save_manifest_raw else None,
        )
        if not should_apply:
            click.echo(render_payload({"ok": True, "action": "import_cli_preview", **plan}, output_format))
            return

        wizard_steps = ["Compile config"]
        if plan.get("manifest_write"):
            wizard_steps.insert(0, "Write manifest")
        with progress_steps(output_format, f"Applying wizard import for '{source_name}'", wizard_steps) as progress:
            if plan.get("manifest_write"):
                progress.advance("Writing manifest")
                manifest_write = dict(plan["manifest_write"])
                merge_operation_into_manifest(
                    Path(manifest_write["resolved_path"]),
                    dict(manifest_write["operation"]),
                    executable=manifest_write.get("executable"),
                )

            baseline_conflicts = conflict_signatures(app.catalog.conflicts)

            def mutator(payload: Dict[str, Any]) -> None:
                apply_cli_import_plan(payload, plan)

            progress.advance("Compiling config")
            updated, compiled_app = apply_update(
                session,
                mutator,
                compile_runtime=True,
                profile=state.profile,
                baseline_conflicts=baseline_conflicts,
            )
        compiled_mount = None
        if compiled_app and plan.get("mount"):
            compiled_mount = compiled_app.catalog.find_by_id(plan["mount"]["id"])
        click.echo(
            render_payload(
                {
                    "ok": True,
                    "action": "import_cli_apply",
                    "file": str(session.target_path),
                    "created_file": session.created,
                    "warnings": list(session.warnings),
                    **plan,
                    "source_config": strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
                    "mount_config": find_mount_payload(updated.get("mounts", []), plan["mount"]["id"]) if plan.get("mount") else None,
                    "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
                },
                output_format,
            )
        )
