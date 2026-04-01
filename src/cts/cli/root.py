from __future__ import annotations

import json
import fnmatch
import re
import shlex
import sys
import time
from functools import update_wrapper
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import click

from cts.cli.registration import (
    load_alias_builtin_commands,
    load_import_builtin_commands,
    load_inspect_builtin_commands,
    load_manage_builtin_commands,
    load_mount_builtin_commands,
    load_source_builtin_commands,
)
from cts.cli.support import (
    ProgressSteps as _ProgressSteps,
    build_error_command as _support_build_error_command,
    build_param_payload as _support_build_param_payload,
    elapsed_status as _elapsed_status,
    error_output_format,
    fail as _fail,
    find_alias_payload as _support_find_alias_payload,
    find_mount_payload as _support_find_mount_payload,
    maybe_confirm as _maybe_confirm,
    parse_param_spec as _support_parse_param_spec,
    path_to_str as _support_path_to_str,
    serialize_error as _support_serialize_error,
    split_command_segments as _support_split_command_segments,
    status as _status,
    strip_internal_metadata as _strip_internal_metadata,
)
from cts.cli.lazy import (
    CTSApp,
    apply_update,
    conflict_signatures,
    parse_assignment,
    parse_string_map_item,
    prepare_edit_session,
    render_payload,
    create_http_server,
    default_ui_dist_dir,
)
from cts.cli.state import CLIState, get_app as _cli_get_app, get_state as _cli_get_state, parse_root_argv as _parse_root_argv


def _build_static_help_catalog(loaded):
    from cts.cli.static_catalog import build_static_help_catalog

    return build_static_help_catalog(loaded)


def _command_loading_label(ctx: click.Context, mode: str) -> str:
    command_path = ctx.command_path or "cts"
    action = "Loading"
    if mode == "invoke":
        action = "Preparing"
    return f"{action} {command_path}"


def pass_app(func):
    return _pass_app_mode("full", func)


def pass_help_app(func):
    return _pass_app_mode("help", func)


def pass_minimal_app(func):
    return _pass_app_mode("minimal", func)


def _pass_app_mode(mode: str, func):
    @click.pass_context
    def wrapper(ctx: click.Context, *args, **kwargs):
        output_format = _error_output_format(ctx, kwargs.get("output_format"))
        start_perf = time.perf_counter()
        ctx.meta["cts_app_load_started_at"] = start_perf
        try:
            with _elapsed_status(output_format, _command_loading_label(ctx, mode)) as status_handle:
                app = _get_app(
                    ctx,
                    mode=mode,
                    progress_callback=lambda message: status_handle.update(f"{_command_loading_label(ctx, mode)}: {message}"),
                )
        except Exception as exc:
            _fail(ctx, exc, "config_load", output_format)
            return None
        return ctx.invoke(func, app, *args, **kwargs)

    return update_wrapper(wrapper, func)


def pass_invoke_app(func):
    return _pass_app_mode("invoke", func)


class DeferredLoadGroup(click.Group):
    def __init__(self, *args, loader: Optional[Callable[[click.Group], None]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._loader = loader
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded or self._loader is None:
            return
        self._loader(self)
        self._loaded = True

    def list_commands(self, ctx):
        self._ensure_loaded()
        return super().list_commands(ctx)

    def get_command(self, ctx, cmd_name):
        self._ensure_loaded()
        return super().get_command(ctx, cmd_name)

    def invoke(self, ctx):
        self._ensure_loaded()
        return super().invoke(ctx)


class CatalogBackedGroup(click.Group):
    def __init__(self, *args, path_prefix=None, dynamic_only: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.path_prefix = tuple(path_prefix or ())
        self.dynamic_only = dynamic_only

    def list_commands(self, ctx):
        commands = [] if self.dynamic_only else list(super().list_commands(ctx))
        state = _get_state(ctx)
        catalog = state.get_static_help_catalog() if state.help_requested else state.get_static_catalog()
        if catalog is not None:
            commands.extend(catalog.child_tokens(self.path_prefix))
            return sorted(set(commands))
        try:
            app = _get_app(ctx)
        except Exception:
            return sorted(set(commands))
        commands.extend(app.catalog.child_tokens(self.path_prefix))
        return sorted(set(commands))

    def get_command(self, ctx, cmd_name):
        state = _get_state(ctx)
        direct_mount = state.get_direct_help_mount()
        if direct_mount is not None:
            next_prefix = self.path_prefix + (cmd_name,)
            target_path = tuple(direct_mount.command_path)
            if next_prefix == target_path[: len(next_prefix)]:
                if len(next_prefix) < len(target_path):
                    from cts.cli.dynamic import DirectPathGroup

                    return DirectPathGroup(
                        name=cmd_name,
                        path_prefix=next_prefix,
                        target_mount=direct_mount,
                        callback_factory=_dynamic_callback,
                        runtime_command_factory=_build_runtime_help_command,
                        help="Dynamic command group for " + " ".join(next_prefix),
                        no_args_is_help=True,
                    )
                runtime_command = _build_runtime_help_command(ctx, next_prefix, direct_mount)
                if runtime_command is not None:
                    return runtime_command
                from cts.cli.dynamic import build_static_help_command

                return build_static_help_command(direct_mount, callback=_dynamic_callback(direct_mount))

        if not self.dynamic_only:
            builtin = super().get_command(ctx, cmd_name)
            if builtin is not None:
                return builtin

        catalog = state.get_static_help_catalog() if state.help_requested else state.get_static_catalog()
        if catalog is not None:
            next_prefix = self.path_prefix + (cmd_name,)
            mount = catalog.find_by_path(next_prefix)
            if mount:
                if state.help_requested and _static_help_needs_runtime_fallback(mount):
                    runtime_command = _build_runtime_help_command(ctx, next_prefix, mount)
                    if runtime_command is not None:
                        return runtime_command
                from cts.cli.dynamic import build_static_help_command

                return build_static_help_command(mount, callback=_dynamic_callback(mount))
            if catalog.has_group(next_prefix):
                group_summary = catalog.group_summary(next_prefix)
                return CatalogBackedGroup(
                    name=cmd_name,
                    path_prefix=next_prefix,
                    dynamic_only=True,
                    short_help=group_summary,
                    help=catalog.group_description(next_prefix),
                    no_args_is_help=True,
                )
            if state.help_requested:
                return None

        try:
            app = _get_app(ctx)
        except Exception as exc:
            return _support_build_error_command(cmd_name, exc, fail=lambda inner_ctx, inner_exc, stage, output_format: _fail(inner_ctx, inner_exc, stage, output_format))

        next_prefix = self.path_prefix + (cmd_name,)
        mount = app.catalog.find_by_path(next_prefix)
        if mount:
            from cts.cli.dynamic import build_dynamic_command

            return build_dynamic_command(app, mount, callback=_dynamic_callback(mount))
        if app.catalog.has_group(next_prefix):
            group_summary = app.catalog.group_summary(next_prefix)
            return CatalogBackedGroup(
                name=cmd_name,
                path_prefix=next_prefix,
                dynamic_only=True,
                short_help=group_summary,
                help=app.catalog.group_description(next_prefix),
                no_args_is_help=True,
            )
        return None


def _static_help_needs_runtime_fallback(mount: Any) -> bool:
    input_schema = getattr(getattr(mount, "operation", None), "input_schema", None) or {}
    properties = input_schema.get("properties") if isinstance(input_schema, dict) else None
    return not bool(properties)


def _build_runtime_help_command(ctx: click.Context, command_path: tuple[str, ...], mount: Any):
    if not _static_help_needs_runtime_fallback(mount):
        return None
    try:
        app = _get_app(ctx, mode="full")
    except Exception as exc:
        return _support_build_error_command(command_path[-1], exc, fail=lambda inner_ctx, inner_exc, stage, output_format: _fail(inner_ctx, inner_exc, stage, output_format))
    runtime_mount = app.catalog.find_by_path(list(command_path))
    if runtime_mount is None:
        return None
    from cts.cli.dynamic import build_dynamic_command

    return build_dynamic_command(app, runtime_mount, callback=_dynamic_callback(runtime_mount))


def _show_version(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return

    from cts import __version__

    click.echo(f"cts, version {__version__}")
    ctx.exit()


@click.group(
    name="cts",
    cls=CatalogBackedGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--config", "config_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--profile", default=None, help="Active profile override.")
@click.option(
    "--format",
    "--output",
    "global_output",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Default output mode for top-level commands.",
)
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_show_version,
    help="Show the version and exit.",
)
@click.pass_context
def main(ctx: click.Context, config_path: Optional[Path], profile: Optional[str], global_output: str) -> None:
    raw = _parse_root_argv(sys.argv[1:])
    ctx.obj = CLIState(
        config_path=config_path or raw.get("config_path"),
        profile=profile or raw.get("profile"),
        global_output=global_output or raw.get("global_output", "text"),
        help_requested=bool(raw.get("help_requested")),
        requested_command_path=tuple(raw.get("command_path", [])),
        static_catalog_builder=_build_static_help_catalog,
    )


@main.group(cls=DeferredLoadGroup, loader=lambda group: _load_manage_builtin_commands())
def manage() -> None:
    """CTS administration and maintenance commands."""


@manage.group(cls=DeferredLoadGroup, loader=lambda group: _load_source_builtin_commands())
def source() -> None:
    """Source registry operations."""


@main.group("import", cls=DeferredLoadGroup, loader=lambda group: _load_import_builtin_commands())
def import_group() -> None:
    """Provider-driven import entrypoint for sources, mounts, and wizard flows."""


@manage.group(cls=DeferredLoadGroup, loader=lambda group: _load_mount_builtin_commands())
def mount() -> None:
    """Mount registry operations."""


@manage.group("alias", cls=DeferredLoadGroup, loader=lambda group: _load_alias_builtin_commands())
def alias_group() -> None:
    """Top-level alias operations."""


@manage.group(cls=DeferredLoadGroup, loader=lambda group: _load_inspect_builtin_commands())
def inspect() -> None:
    """Inspect compiled sources, mounts, and operations."""


def _builtin_deps() -> Dict[str, Any]:
    return {
        "pass_app": pass_app,
        "pass_help_app": pass_help_app,
        "pass_minimal_app": pass_minimal_app,
        "pass_invoke_app": pass_invoke_app,
        "get_state": lambda ctx: _get_state(ctx),
        "fail": lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
        "serialize_error": lambda exc, stage: _serialize_error(exc, stage),
        "strip_internal_metadata": lambda value: _strip_internal_metadata(value),
        "maybe_confirm": lambda message, assume_yes, output_format: _maybe_confirm(message, assume_yes=assume_yes, output_format=output_format),
        "progress_steps": lambda *args, **kwargs: _ProgressSteps(*args, **kwargs),
        "status": lambda output_format, message: _status(output_format, message),
        "parse_assignment_value": lambda raw: _parse_assignment(raw),
        "parse_string_pair": lambda raw, field_name: _parse_string_pair(raw, field_name=field_name),
        "emit_app_event": lambda *args, **kwargs: _emit_app_event(*args, **kwargs),
        "prepare_edit_session": lambda config_path, target_file=None: prepare_edit_session(config_path, target_file=target_file),
        "app_factory": lambda loaded, profile, config_path: CTSApp(
            loaded,
            active_profile=profile,
            explicit_config_path=str(config_path) if config_path else None,
            requested_profile=profile,
        ),
        "render_payload": lambda payload, output_format: render_payload(payload, output_format),
        "apply_update": lambda *args, **kwargs: apply_update(*args, **kwargs),
        "conflict_signatures": lambda conflicts: conflict_signatures(conflicts),
        "find_mount_payload": lambda items, mount_id: _find_mount_payload(items, mount_id),
        "split_command_segments": lambda values: _split_command_segments(values),
        "build_param_payload": lambda **kwargs: _build_param_payload(**kwargs),
        "find_alias_payload": lambda items, from_tokens: _find_alias_payload(items, from_tokens),
        "path_to_str": lambda path: _path_to_str(path),
        "run_mount_command": lambda app, mount, kwargs, mode, **extra: _run_mount_command(app, mount, kwargs, mode, **extra),
        "create_http_server": lambda *args, **kwargs: create_http_server(*args, **kwargs),
        "default_ui_dist_dir": lambda: default_ui_dist_dir(),
    }


def _load_manage_builtin_commands() -> None:
    load_manage_builtin_commands(main=main, manage=manage, deps=_builtin_deps())


def _load_source_builtin_commands() -> None:
    load_source_builtin_commands(source=source, deps=_builtin_deps())


def _load_import_builtin_commands() -> None:
    load_import_builtin_commands(import_group=import_group, deps=_builtin_deps())


def _load_mount_builtin_commands() -> None:
    load_mount_builtin_commands(mount=mount, deps=_builtin_deps())


def _load_alias_builtin_commands() -> None:
    load_alias_builtin_commands(alias_group=alias_group, deps=_builtin_deps())


def _load_inspect_builtin_commands() -> None:
    load_inspect_builtin_commands(inspect=inspect, deps=_builtin_deps())


def _emit_app_event(*args: Any, **kwargs: Any) -> None:
    from cts.execution.logging import emit_app_event

    emit_app_event(*args, **kwargs)


def _dynamic_callback(mount):
    from cts.cli.execution_runtime import build_dynamic_callback

    return build_dynamic_callback(
        mount,
        get_app=lambda ctx, mode="full", progress_callback=None: _get_app(ctx, mode=mode, progress_callback=progress_callback),
        fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
        error_output_format=lambda ctx, output_format: _error_output_format(ctx, output_format),
        elapsed_status=lambda output_format, label: _elapsed_status(output_format, label),
        run_mount_command=lambda app, runtime_mount, kwargs, mode, **extra: _run_mount_command(app, runtime_mount, kwargs, mode, **extra),
    )


def _run_mount_command(app: CTSApp, mount, kwargs: Dict[str, Any], mode: str, **extra: Any) -> None:
    from cts.cli.execution_runtime import run_mount_command

    run_mount_command(
        app,
        mount,
        kwargs,
        mode,
        fail=lambda ctx, exc, stage, output_format, **extra: _fail(ctx, exc, stage, output_format, **extra),
        elapsed_status=lambda output_format, label: _elapsed_status(output_format, label),
        **extra,
    )


def _get_app(ctx: click.Context, mode: str = "auto", progress_callback=None) -> CTSApp:
    return _cli_get_app(ctx, _build_static_help_catalog, mode=mode, progress_callback=progress_callback)


def _get_state(ctx: click.Context) -> CLIState:
    return _cli_get_state(ctx, _build_static_help_catalog)


def _resolve_static_mount_for_path(loaded, command_path: tuple[str, ...]):
    catalog = _build_static_help_catalog(loaded)
    return catalog.find_by_path(command_path)


def _parse_assignment(raw: str) -> tuple[str, Any]:
    return parse_assignment(raw)


def _parse_string_pair(raw: str, *, field_name: str) -> tuple[str, str]:
    return parse_string_map_item(raw, field_name=field_name)


def _split_command_segments(values: tuple[str, ...] | list[str]) -> List[str]:
    return _support_split_command_segments(values)


def _build_param_payload(
    *,
    param_specs: tuple[str, ...],
    required_params: tuple[str, ...],
    param_help_items: tuple[str, ...],
    param_default_items: tuple[str, ...],
    param_flag_items: tuple[str, ...],
) -> Dict[str, Any]:
    return _support_build_param_payload(
        parse_assignment=_parse_assignment,
        parse_string_pair=_parse_string_pair,
        param_specs=param_specs,
        required_params=required_params,
        param_help_items=param_help_items,
        param_default_items=param_default_items,
        param_flag_items=param_flag_items,
    )
    


def _parse_param_spec(spec: str) -> tuple[str, str]:
    return _support_parse_param_spec(spec)


def _find_mount_payload(items: List[Dict[str, Any]], mount_id: str) -> Optional[Dict[str, Any]]:
    return _support_find_mount_payload(items, mount_id)


def _find_alias_payload(items: List[Dict[str, Any]], from_tokens: List[str]) -> Optional[Dict[str, Any]]:
    return _support_find_alias_payload(items, from_tokens)


def _path_to_str(path: Optional[Path]) -> Optional[str]:
    return _support_path_to_str(path)


def _serialize_error(exc: Exception, stage: str) -> Dict[str, Any]:
    return _support_serialize_error(exc, stage)


def _error_output_format(ctx: click.Context, requested_output: Optional[str]) -> str:
    return error_output_format(_get_state(ctx).global_output, requested_output)
