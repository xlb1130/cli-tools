from __future__ import annotations

import json
import fnmatch
import re
import shlex
import sys
import threading
import time
from contextlib import contextmanager
from functools import update_wrapper
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import click

from cts import __version__
from cts.cli.builtins.alias import register_alias_commands
from cts.cli.builtins.catalog_workflow import register_catalog_workflow_commands
from cts.cli.builtins.completion import register_completion_commands
from cts.cli.builtins.config import register_config_group
from cts.cli.builtins.execution_ops import register_execution_ops_commands
from cts.cli.builtins.imports import register_import_commands
from cts.cli.builtins.inspect import register_inspect_commands
from cts.cli.builtins.mount import register_mount_commands
from cts.cli.builtins.runtime_admin import register_runtime_admin_commands
from cts.cli.builtins.source import register_source_commands
from cts.cli.builtins.surfaces import register_surface_commands
from cts.cli.dynamic import DirectPathGroup, GroupedOptionCommand, build_dynamic_command, build_static_help_command
from cts.cli.execution_runtime import build_dynamic_callback, run_mount_command
from cts.cli.import_planning import (
    apply_cli_import_plan as imported_apply_cli_import_plan,
    apply_cli_import_tree_plan as imported_apply_cli_import_tree_plan,
    derive_operation_id_from_command as imported_derive_operation_id_from_command,
    prepare_cli_import_plan as imported_prepare_cli_import_plan,
    prepare_cli_import_tree_plan as imported_prepare_cli_import_tree_plan,
)
from cts.cli.import_runtime import execute_import_mcp, execute_import_shell
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
)
from cts.cli.state import CLIState, get_app as _cli_get_app, get_state as _cli_get_state, parse_root_argv
from cts.cli.static_catalog import StaticHelpCatalog, build_static_help_catalog
from cts.execution.errors import RegistryError, exit_code_for_exception
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
            return _build_error_command(cmd_name, exc)

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
    raw = parse_root_argv(sys.argv[1:])
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


register_config_group(
    manage,
    pass_app=pass_app,
    get_state=lambda ctx: _get_state(ctx),
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    serialize_error=lambda exc, stage: _serialize_error(exc, stage),
    strip_internal_metadata=lambda value: _strip_internal_metadata(value),
)


@manage.group()
def source() -> None:
    """Source registry operations."""


register_source_commands(
    source,
    pass_app=pass_app,
    get_state=lambda ctx: _get_state(ctx),
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    maybe_confirm=lambda message, assume_yes, output_format: _maybe_confirm(message, assume_yes=assume_yes, output_format=output_format),
    progress_steps=lambda *args, **kwargs: _ProgressSteps(*args, **kwargs),
    status=lambda output_format, message: _status(output_format, message),
    strip_internal_metadata=lambda value: _strip_internal_metadata(value),
    parse_assignment_value=lambda raw: _parse_assignment(raw),
    parse_string_pair=lambda raw, field_name: _parse_string_pair(raw, field_name=field_name),
    emit_app_event=lambda *args, **kwargs: emit_app_event(*args, **kwargs),
)


@main.group("import")
def import_group() -> None:
    """Simplified import flows for common onboarding tasks."""

register_import_commands(
    import_group,
    get_state=lambda ctx: _get_state(ctx),
    progress_steps=lambda *args, **kwargs: _ProgressSteps(*args, **kwargs),
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    prepare_edit_session=lambda config_path, target_file=None: prepare_edit_session(config_path, target_file=target_file),
    app_factory=lambda loaded, profile, config_path: CTSApp(
        loaded,
        active_profile=profile,
        explicit_config_path=str(config_path) if config_path else None,
        requested_profile=profile,
    ),
    prepare_cli_import_plan=lambda app, **kwargs: imported_prepare_cli_import_plan(app, **kwargs),
    prepare_cli_import_tree_plan=lambda app, **kwargs: imported_prepare_cli_import_tree_plan(app, **kwargs),
    apply_cli_import_plan=lambda payload, plan: imported_apply_cli_import_plan(
        payload,
        plan,
        ensure_mapping=lambda value, key: ensure_mapping(value, key),
        ensure_list=lambda value, key: ensure_list(value, key),
        config_edit_error=lambda message: _config_edit_error(message),
    ),
    apply_cli_import_tree_plan=lambda payload, plan: imported_apply_cli_import_tree_plan(
        payload,
        plan,
        ensure_mapping=lambda value, key: ensure_mapping(value, key),
        ensure_list=lambda value, key: ensure_list(value, key),
        config_edit_error=lambda message: _config_edit_error(message),
    ),
    execute_import_shell=lambda ctx, **kwargs: execute_import_shell(
        ctx,
        get_state=lambda inner_ctx: _get_state(inner_ctx),
        prepare_edit_session=lambda config_path, target_file=None: prepare_edit_session(config_path, target_file=target_file),
        app_factory=lambda loaded, profile, config_path: CTSApp(
            loaded,
            active_profile=profile,
            explicit_config_path=str(config_path) if config_path else None,
            requested_profile=profile,
        ),
        conflict_signatures=lambda conflicts: conflict_signatures(conflicts),
        ensure_mapping=lambda payload, key: ensure_mapping(payload, key),
        ensure_list=lambda payload, key: ensure_list(payload, key),
        apply_update=lambda *args, **kw: apply_update(*args, **kw),
        strip_internal_metadata=lambda value: _strip_internal_metadata(value),
        find_mount_payload=lambda items, mount_id: _find_mount_payload(items, mount_id),
        build_mount_details=lambda app, mount: build_mount_details(app, mount),
        registry_error=lambda message, **extra: RegistryError(message, **extra),
        split_command_segments=lambda values: _split_command_segments(values),
        **kwargs,
    ),
    execute_import_mcp=lambda ctx, **kwargs: execute_import_mcp(
        ctx,
        get_state=lambda inner_ctx: _get_state(inner_ctx),
        prepare_edit_session=lambda config_path, target_file=None: prepare_edit_session(config_path, target_file=target_file),
        apply_update=lambda *args, **kw: apply_update(*args, **kw),
        **kwargs,
    ),
    render_payload=lambda payload, output_format: render_payload(payload, output_format),
    write_manifest_operations=lambda path, operations, executable=None: write_manifest_operations(path, operations, executable=executable),
    merge_operation_into_manifest=lambda path, operation, executable=None: merge_operation_into_manifest(path, operation, executable=executable),
    apply_update=lambda *args, **kwargs: apply_update(*args, **kwargs),
    conflict_signatures=lambda conflicts: conflict_signatures(conflicts),
    strip_internal_metadata=lambda value: _strip_internal_metadata(value),
    find_mount_payload=lambda items, mount_id: _find_mount_payload(items, mount_id),
    build_mount_details=lambda app, mount: build_mount_details(app, mount),
    derive_operation_id_from_command=lambda command_argv: imported_derive_operation_id_from_command(command_argv),
)


@manage.group()
def mount() -> None:
    """Mount registry operations."""


register_mount_commands(
    mount,
    pass_app=pass_app,
    get_state=lambda ctx: _get_state(ctx),
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    maybe_confirm=lambda message, assume_yes, output_format: _maybe_confirm(message, assume_yes=assume_yes, output_format=output_format),
    progress_steps=lambda *args, **kwargs: _ProgressSteps(*args, **kwargs),
    status=lambda output_format, message: _status(output_format, message),
    conflict_signatures=lambda conflicts: conflict_signatures(conflicts),
    split_command_segments=lambda values: _split_command_segments(values),
    build_param_payload=lambda **kwargs: _build_param_payload(**kwargs),
    parse_assignment_value=lambda raw: _parse_assignment(raw),
    find_mount_payload=lambda items, mount_id: _find_mount_payload(items, mount_id),
)


@manage.group("alias")
def alias_group() -> None:
    """Top-level alias operations."""


register_alias_commands(
    alias_group,
    pass_app=pass_app,
    get_state=lambda ctx: _get_state(ctx),
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    maybe_confirm=lambda message, assume_yes, output_format: _maybe_confirm(message, assume_yes=assume_yes, output_format=output_format),
    progress_steps=lambda *args, **kwargs: _ProgressSteps(*args, **kwargs),
    conflict_signatures=lambda conflicts: conflict_signatures(conflicts),
    split_command_segments=lambda values: _split_command_segments(values),
    find_alias_payload=lambda items, from_tokens: _find_alias_payload(items, from_tokens),
)


register_catalog_workflow_commands(
    manage,
    pass_app=pass_app,
    get_state=lambda ctx: _get_state(ctx),
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
)


@manage.group()
def inspect() -> None:
    """Inspect compiled sources, mounts, and operations."""


register_inspect_commands(
    inspect,
    pass_app=pass_app,
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    path_to_str=lambda path: _path_to_str(path),
)

register_runtime_admin_commands(
    manage,
    pass_app=pass_app,
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    maybe_confirm=lambda message, assume_yes, output_format: _maybe_confirm(
        message,
        assume_yes=assume_yes,
        output_format=output_format,
    ),
)

register_execution_ops_commands(
    manage,
    pass_app=pass_app,
    pass_invoke_app=pass_invoke_app,
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    maybe_confirm=lambda message, assume_yes, output_format: _maybe_confirm(
        message,
        assume_yes=assume_yes,
        output_format=output_format,
    ),
    progress_steps=lambda *args, **kwargs: _ProgressSteps(*args, **kwargs),
    status=lambda output_format, message: _status(output_format, message),
    emit_app_event=lambda *args, **kwargs: emit_app_event(*args, **kwargs),
    run_mount_command=lambda app, mount, kwargs, mode: _run_mount_command(app, mount, kwargs, mode),
)

register_completion_commands(
    manage,
    main_group=main,
)

register_surface_commands(
    manage,
    pass_app=pass_app,
    fail=lambda ctx, exc, stage, output_format: _fail(ctx, exc, stage, output_format),
    progress_steps=lambda *args, **kwargs: _ProgressSteps(*args, **kwargs),
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
    tokens: List[str] = []
    for value in values:
        tokens.extend(shlex.split(value))
    return tokens


def _build_param_payload(
    *,
    param_specs: tuple[str, ...],
    required_params: tuple[str, ...],
    param_help_items: tuple[str, ...],
    param_default_items: tuple[str, ...],
    param_flag_items: tuple[str, ...],
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for spec in param_specs:
        name, param_type = _parse_param_spec(spec)
        params[name] = {"type": param_type}

    for name in required_params:
        params.setdefault(name, {"type": "string"})
        params[name]["required"] = True

    for item in param_help_items:
        name, text = _parse_string_pair(item, field_name="param-help")
        params.setdefault(name, {"type": "string"})
        params[name]["help"] = text

    for item in param_default_items:
        name, raw_value = _parse_assignment(item)
        params.setdefault(name, {"type": "string"})
        params[name]["default"] = raw_value

    for item in param_flag_items:
        name, flag = _parse_string_pair(item, field_name="param-flag")
        params.setdefault(name, {"type": "string"})
        params[name]["flag"] = flag

    return params


def _parse_param_spec(spec: str) -> tuple[str, str]:
    if ":" in spec:
        name, param_type = spec.split(":", 1)
    else:
        name, param_type = spec, "string"
    name = name.strip()
    param_type = param_type.strip() or "string"
    if not name:
        raise _config_edit_error(f"param 不能为空: {spec}")
    return name, param_type


def _find_mount_payload(items: List[Dict[str, Any]], mount_id: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and item.get("id") == mount_id:
            return _strip_internal_metadata(item)
    return None


def _find_alias_payload(items: List[Dict[str, Any]], from_tokens: List[str]) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and item.get("from") == from_tokens:
            return _strip_internal_metadata(item)
    return None


def _path_to_str(path: Optional[Path]) -> Optional[str]:
    return str(path) if path else None


def _serialize_error(exc: Exception, stage: str) -> Dict[str, Any]:
    return build_error_envelope(exc, stage)["error"]


def _error_output_format(ctx: click.Context, requested_output: Optional[str]) -> str:
    if requested_output == "json":
        return "json"
    return _get_state(ctx).global_output


class _ProgressSteps:
    def __init__(self, output_format: str, title: str, steps: List[str]) -> None:
        self.output_format = output_format
        self.title = title
        self.steps = steps
        self.index = 0
        self.enabled = output_format != "json" and bool(getattr(sys.stderr, "isatty", lambda: False)())
        self.started_at = time.perf_counter()
        self.current_step: Optional[str] = None
        self.current_step_started_at: Optional[float] = None
        self.failed_step: Optional[str] = None
        self.failed_step_duration: Optional[float] = None
        self.step_durations: List[tuple[str, float]] = []
        self._console = None
        self._progress = None
        self._task_id = None
        self._ticker_stop = threading.Event()
        self._ticker_thread: Optional[threading.Thread] = None
        self._status_interval = 0.1

    def __enter__(self):
        if not self.enabled:
            return self
        try:
            from rich.console import Console
            from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
        except ModuleNotFoundError:
            click.echo(f"{self.title}", err=True)
            return self
        self._console = Console(stderr=True)
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=self._console,
            transient=True,
        )
        self._progress.__enter__()
        self._task_id = self._progress.add_task(self.title, total=max(len(self.steps), 1), completed=0)
        self._start_live_updates()
        return self

    def _elapsed_total(self) -> float:
        return max(time.perf_counter() - self.started_at, 0.0)

    def _close_current_step(self, *, duration_override: Optional[float] = None) -> None:
        if self.current_step is None or self.current_step_started_at is None:
            return
        duration = duration_override
        if duration is None:
            duration = max(time.perf_counter() - self.current_step_started_at, 0.0)
        self.step_durations.append((self.current_step, duration))
        self.current_step = None
        self.current_step_started_at = None

    def _emit_status_line(self, message: str) -> None:
        if self._console is not None:
            self._console.print(message)
            return
        click.echo(message, err=True)

    def _current_step_elapsed(self) -> float:
        if self.current_step_started_at is None:
            return 0.0
        return max(time.perf_counter() - self.current_step_started_at, 0.0)

    def _format_current_description(self) -> str:
        label = self.current_step or self.title
        if not self.current_step:
            return label
        return f"[{self.index}/{len(self.steps)}] {label}  elapsed {self._current_step_elapsed():.1f}s"

    def _refresh_live_description(self) -> None:
        if self._progress is None or self._task_id is None or self.current_step is None:
            return
        self._progress.update(self._task_id, description=self._format_current_description())

    def _start_live_updates(self) -> None:
        if self._progress is None or self._task_id is None:
            return
        self._ticker_stop.clear()

        def _ticker() -> None:
            while not self._ticker_stop.wait(self._status_interval):
                self._refresh_live_description()

        self._ticker_thread = threading.Thread(target=_ticker, name="cts-progress-steps", daemon=True)
        self._ticker_thread.start()

    def _emit_failure(self) -> None:
        step_label = self.failed_step or self.current_step or (self.steps[self.index] if self.index < len(self.steps) else self.title)
        current_step_elapsed = self.failed_step_duration or 0.0
        if current_step_elapsed <= 0.0 and self.current_step_started_at is not None:
            current_step_elapsed = max(time.perf_counter() - self.current_step_started_at, 0.0)
        self._emit_status_line(
            f"Failed at step {min(self.index + (1 if self.current_step else 0), len(self.steps))}/{len(self.steps)}: "
            f"{step_label} (step {current_step_elapsed:.2f}s, total {self._elapsed_total():.2f}s)"
        )

    def _emit_summary(self, *, failed: bool) -> None:
        status = "Failed" if failed else "Completed"
        self._emit_status_line(f"{status} {self.title} in {self._elapsed_total():.2f}s")
        for idx, (label, duration) in enumerate(self.step_durations, start=1):
            self._emit_status_line(f"  {idx}. {label}: {duration:.2f}s")

    def advance(self, label: Optional[str] = None) -> None:
        if not self.enabled:
            return
        self._close_current_step()
        self.index += 1
        description = label or (self.steps[self.index - 1] if self.index - 1 < len(self.steps) else self.title)
        self.current_step = description
        self.current_step_started_at = time.perf_counter()
        if self._progress is not None and self._task_id is not None:
            self._progress.update(
                self._task_id,
                completed=min(self.index, len(self.steps)),
                description=self._format_current_description(),
            )
        else:
            click.echo(f"[{self.index}/{len(self.steps)}] {description}", err=True)

    def update_current(self, label: str) -> None:
        if not self.enabled or self.current_step is None:
            return
        self.current_step = label
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, description=self._format_current_description())
        else:
            click.echo(f"[{self.index}/{len(self.steps)}] {label}", err=True)

    def __exit__(self, exc_type, exc, tb):
        failed_duration = None
        if exc_type is not None:
            self.failed_step = self.current_step or self.failed_step
            if self.current_step_started_at is not None:
                failed_duration = max(time.perf_counter() - self.current_step_started_at, 0.0)
                self.failed_step_duration = failed_duration
        self._close_current_step(duration_override=failed_duration)
        self._ticker_stop.set()
        if self._ticker_thread is not None:
            self._ticker_thread.join(timeout=max(self._status_interval * 2, 0.2))
        if self._progress is not None:
            self._progress.__exit__(exc_type, exc, tb)
        if exc_type is not None and self.enabled:
            self._emit_failure()
            self._emit_summary(failed=True)
        elif self.enabled and self.step_durations:
            self._emit_summary(failed=False)
        return False


@contextmanager
def _status(output_format: str, message: str):
    if output_format == "json" or not bool(getattr(sys.stderr, "isatty", lambda: False)()):
        yield
        return
    try:
        from rich.console import Console
    except ModuleNotFoundError:
        click.echo(message, err=True)
        yield
        return
    console = Console(stderr=True)
    with console.status(message):
        yield


@contextmanager
def _elapsed_status(output_format: str, message: str, *, interval: float = 0.1):
    if output_format == "json" or not bool(getattr(sys.stderr, "isatty", lambda: False)()):
        yield
        return
    try:
        from rich.console import Console
    except ModuleNotFoundError:
        click.echo(message, err=True)
        yield
        return

    console = Console(stderr=True)
    stop_event = threading.Event()
    start_time = time.perf_counter()

    def _format_message() -> str:
        elapsed = time.perf_counter() - start_time
        return f"{message}  elapsed {elapsed:.1f}s"

    with console.status(_format_message()) as status:
        def _ticker() -> None:
            while not stop_event.wait(interval):
                status.update(_format_message())

        worker = threading.Thread(target=_ticker, name="cts-elapsed-status", daemon=True)
        worker.start()
        try:
            yield
        finally:
            stop_event.set()
            worker.join(timeout=max(interval * 2, 0.2))


def _maybe_confirm(message: str, *, assume_yes: bool, output_format: str) -> None:
    if assume_yes or output_format == "json":
        return
    if not bool(getattr(sys.stdin, "isatty", lambda: False)()):
        return
    if not click.confirm(message, default=False):
        raise click.Abort()


def _build_error_command(name: str, exc: Exception) -> click.Command:
    @click.pass_context
    def callback(ctx: click.Context) -> None:
        _fail(ctx, exc, "config_load", _error_output_format(ctx, None))

    return click.Command(name=name, callback=callback, help="Configuration failed to load.")


def _strip_internal_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_internal_metadata(item) for key, item in value.items() if not key.startswith("__")}
    if isinstance(value, list):
        return [_strip_internal_metadata(item) for item in value]
    return value


def _fail(
    ctx: click.Context,
    exc: Exception,
    stage: str,
    output_format: str,
    mount=None,
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> None:
    payload = build_error_envelope(exc, stage, mount=mount, run_id=run_id, trace_id=trace_id)
    click.echo(render_payload(payload, output_format))
    ctx.exit(exit_code_for_exception(exc, stage))


for _command_name, _command in manage.commands.items():
    if _command_name not in main.commands:
        main.add_command(_command, name=_command_name)
