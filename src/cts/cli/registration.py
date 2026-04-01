from __future__ import annotations

def load_manage_builtin_commands(*, main, manage, deps) -> None:
    import webbrowser

    from cts.cli.builtins.catalog_workflow import register_catalog_workflow_commands
    from cts.cli.builtins.completion import register_completion_commands
    from cts.cli.builtins.config import register_config_group
    from cts.cli.builtins.execution_ops import register_execution_ops_commands
    from cts.cli.builtins.runtime_admin import register_runtime_admin_commands
    from cts.cli.builtins.surfaces import register_surface_commands

    register_config_group(
        manage,
        pass_app=deps["pass_app"],
        pass_help_app=deps["pass_help_app"],
        get_state=deps["get_state"],
        fail=deps["fail"],
        serialize_error=deps["serialize_error"],
        strip_internal_metadata=deps["strip_internal_metadata"],
    )

    register_catalog_workflow_commands(
        manage,
        pass_app=deps["pass_app"],
        pass_help_app=deps["pass_help_app"],
        get_state=deps["get_state"],
        fail=deps["fail"],
    )

    register_runtime_admin_commands(
        manage,
        pass_app=deps["pass_app"],
        pass_help_app=deps["pass_help_app"],
        pass_minimal_app=deps["pass_minimal_app"],
        fail=deps["fail"],
        maybe_confirm=deps["maybe_confirm"],
    )

    register_execution_ops_commands(
        manage,
        pass_app=deps["pass_app"],
        pass_invoke_app=deps["pass_invoke_app"],
        fail=deps["fail"],
        maybe_confirm=deps["maybe_confirm"],
        progress_steps=deps["progress_steps"],
        status=deps["status"],
        emit_app_event=deps["emit_app_event"],
        run_mount_command=deps["run_mount_command"],
    )

    register_completion_commands(
        manage,
        main_group=main,
    )

    register_surface_commands(
        manage,
        pass_app=deps["pass_app"],
        fail=deps["fail"],
        progress_steps=deps["progress_steps"],
        create_http_server=deps["create_http_server"],
        default_ui_dist_dir=deps["default_ui_dist_dir"],
        render_payload=deps["render_payload"],
        browser_opener=lambda url: webbrowser.open(url),
    )


def load_source_builtin_commands(*, source, deps) -> None:
    from cts.cli.builtins.source import register_source_commands

    register_source_commands(
        source,
        pass_app=deps["pass_app"],
        pass_help_app=deps["pass_help_app"],
        get_state=deps["get_state"],
        fail=deps["fail"],
        maybe_confirm=deps["maybe_confirm"],
        progress_steps=deps["progress_steps"],
        status=deps["status"],
        strip_internal_metadata=deps["strip_internal_metadata"],
        parse_assignment_value=deps["parse_assignment_value"],
        parse_string_pair=deps["parse_string_pair"],
        emit_app_event=deps["emit_app_event"],
    )


def load_import_builtin_commands(*, import_group, deps) -> None:
    from cts.cli.builtins.imports import register_import_commands

    register_import_commands(
        import_group,
        get_state=deps["get_state"],
        progress_steps=deps["progress_steps"],
        fail=deps["fail"],
        prepare_edit_session=deps["prepare_edit_session"],
        app_factory=deps["app_factory"],
        render_payload=deps["render_payload"],
        apply_update=deps["apply_update"],
    )


def load_mount_builtin_commands(*, mount, deps) -> None:
    from cts.cli.builtins.mount import register_mount_commands

    register_mount_commands(
        mount,
        pass_app=deps["pass_app"],
        pass_help_app=deps["pass_help_app"],
        get_state=deps["get_state"],
        fail=deps["fail"],
        maybe_confirm=deps["maybe_confirm"],
        progress_steps=deps["progress_steps"],
        status=deps["status"],
        conflict_signatures=deps["conflict_signatures"],
        split_command_segments=deps["split_command_segments"],
        build_param_payload=deps["build_param_payload"],
        parse_assignment_value=deps["parse_assignment_value"],
        find_mount_payload=deps["find_mount_payload"],
    )


def load_alias_builtin_commands(*, alias_group, deps) -> None:
    from cts.cli.builtins.alias import register_alias_commands

    register_alias_commands(
        alias_group,
        pass_app=deps["pass_app"],
        pass_help_app=deps["pass_help_app"],
        get_state=deps["get_state"],
        fail=deps["fail"],
        maybe_confirm=deps["maybe_confirm"],
        progress_steps=deps["progress_steps"],
        conflict_signatures=deps["conflict_signatures"],
        split_command_segments=deps["split_command_segments"],
        find_alias_payload=deps["find_alias_payload"],
    )


def load_inspect_builtin_commands(*, inspect, deps) -> None:
    from cts.cli.builtins.inspect import register_inspect_commands

    register_inspect_commands(
        inspect,
        pass_app=deps["pass_app"],
        fail=deps["fail"],
        path_to_str=deps["path_to_str"],
    )


def register_builtin_commands(*, main, manage, source, import_group, mount, alias_group, inspect, deps) -> None:
    load_manage_builtin_commands(main=main, manage=manage, deps=deps)
    load_source_builtin_commands(source=source, deps=deps)
    load_import_builtin_commands(import_group=import_group, deps=deps)
    load_mount_builtin_commands(mount=mount, deps=deps)
    load_alias_builtin_commands(alias_group=alias_group, deps=deps)
    load_inspect_builtin_commands(inspect=inspect, deps=deps)
