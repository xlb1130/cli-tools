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

from cts import __version__
from cts.cli.dynamic import DirectPathGroup, GroupedOptionCommand, build_dynamic_command, build_static_help_command
from cts.cli.execution_runtime import build_dynamic_callback, run_mount_command
from cts.cli.registration import register_builtin_commands
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
    _config_edit_error,
    apply_assignment,
    apply_update,
    build_app,
    build_error_envelope,
    build_generated_mount,
    build_mount_details,
    build_mount_record,
    build_source_details,
    build_source_summary,
    conflict_signatures,
    ensure_list,
    ensure_mapping,
    lint_loaded_config,
    load_manifest,
    manifest_operations_from_data,
    merge_operation_into_manifest,
    operation_from_config,
    operation_matches_select,
    parse_assignment,
    parse_string_map_item,
    prepare_edit_session,
    render_payload,
    summarize_help_text,
    synthesize_operation,
    write_manifest_operations,
    create_http_server,
    default_ui_dist_dir,
)
from cts.cli.state import CLIState, get_app as _cli_get_app, get_state as _cli_get_state, parse_root_argv as _parse_root_argv
from cts.cli.static_catalog import StaticHelpCatalog, build_static_help_catalog
from cts.execution.errors import RegistryError
from cts.execution.logging import (
    emit_app_event,
)


def _build_static_help_catalog(loaded):
    return build_static_help_catalog(loaded)


def pass_app(func):
    return _pass_app_mode("full", func)


def _pass_app_mode(mode: str, func):
    @click.pass_context
    def wrapper(ctx: click.Context, *args, **kwargs):
        try:
            app = _get_app(ctx, mode=mode)
        except Exception as exc:
            _fail(ctx, exc, "config_load", _error_output_format(ctx, kwargs.get("output_format")))
            return None
        return ctx.invoke(func, app, *args, **kwargs)

    return update_wrapper(wrapper, func)


def pass_invoke_app(func):
    return _pass_app_mode("invoke", func)


class CatalogBackedGroup(click.Group):
    def __init__(self, *args, path_prefix=None, dynamic_only: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.path_prefix = tuple(path_prefix or ())
        self.dynamic_only = dynamic_only

    def list_commands(self, ctx):
        commands = [] if self.dynamic_only else list(super().list_commands(ctx))
        state = _get_state(ctx)
        if state.help_requested:
            catalog = state.get_static_help_catalog()
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
                    return DirectPathGroup(
                        name=cmd_name,
                        path_prefix=next_prefix,
                        target_mount=direct_mount,
                        callback_factory=_dynamic_callback,
                        help="Dynamic command group for " + " ".join(next_prefix),
                        no_args_is_help=True,
                    )
                return build_static_help_command(direct_mount, callback=_dynamic_callback(direct_mount))

        if not self.dynamic_only:
            builtin = super().get_command(ctx, cmd_name)
            if builtin is not None:
                return builtin

        if state.help_requested:
            catalog = state.get_static_help_catalog()
            if catalog is not None:
                next_prefix = self.path_prefix + (cmd_name,)
                mount = catalog.find_by_path(next_prefix)
                if mount:
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
                return None

        try:
            app = _get_app(ctx)
        except Exception as exc:
            return _support_build_error_command(cmd_name, exc, fail=lambda inner_ctx, inner_exc, stage, output_format: _fail(inner_ctx, inner_exc, stage, output_format))

        next_prefix = self.path_prefix + (cmd_name,)
        mount = app.catalog.find_by_path(next_prefix)
        if mount:
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
@click.version_option(__version__, prog_name="cts")
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


@main.group()
def manage() -> None:
    """CTS administration and maintenance commands."""


@manage.group()
def source() -> None:
    """Source registry operations."""


@main.group("import")
def import_group() -> None:
    """Provider-driven import entrypoint for sources, mounts, and wizard flows."""


@manage.group()
def mount() -> None:
    """Mount registry operations."""


@manage.group("alias")
def alias_group() -> None:
    """Top-level alias operations."""


@manage.group()
def inspect() -> None:
    """Inspect compiled sources, mounts, and operations."""


register_builtin_commands(
    main=main,
    manage=manage,
    source=source,
    import_group=import_group,
    mount=mount,
    alias_group=alias_group,
    inspect=inspect,
    deps={
        "pass_app": pass_app,
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
        "emit_app_event": lambda *args, **kwargs: emit_app_event(*args, **kwargs),
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
        "run_mount_command": lambda app, mount, kwargs, mode: _run_mount_command(app, mount, kwargs, mode),
        "create_http_server": lambda *args, **kwargs: create_http_server(*args, **kwargs),
        "default_ui_dist_dir": lambda: default_ui_dist_dir(),
    },
)


def _dynamic_callback(mount):
    return build_dynamic_callback(
        mount,
        get_app=lambda ctx, mode="full": _get_app(ctx, mode=mode),
        fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
        error_output_format=lambda ctx, output_format: _error_output_format(ctx, output_format),
        run_mount_command=lambda app, runtime_mount, kwargs, mode: _run_mount_command(app, runtime_mount, kwargs, mode),
    )


def _run_mount_command(app: CTSApp, mount, kwargs: Dict[str, Any], mode: str) -> None:
    run_mount_command(
        app,
        mount,
        kwargs,
        mode,
        fail=lambda ctx, exc, stage, output_format, **extra: _fail(ctx, exc, stage, output_format, **extra),
        elapsed_status=lambda output_format, label: _elapsed_status(output_format, label),
    )


def _get_app(ctx: click.Context, mode: str = "auto") -> CTSApp:
    return _cli_get_app(ctx, _build_static_help_catalog, mode=mode)


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
