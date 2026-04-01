from __future__ import annotations

import shlex
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import click


def split_command_segments(values: tuple[str, ...] | list[str]) -> List[str]:
    tokens: List[str] = []
    for value in values:
        tokens.extend(shlex.split(value))
    return tokens


def build_param_payload(
    *,
    param_specs: tuple[str, ...],
    required_params: tuple[str, ...],
    param_help_items: tuple[str, ...],
    param_default_items: tuple[str, ...],
    param_flag_items: tuple[str, ...],
    parse_assignment: Any,
    parse_string_pair: Any,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for spec in param_specs:
        name, param_type = parse_param_spec(spec)
        params[name] = {"type": param_type}

    for name in required_params:
        params.setdefault(name, {"type": "string"})
        params[name]["required"] = True

    for item in param_help_items:
        name, text = parse_string_pair(item, field_name="param-help")
        params.setdefault(name, {"type": "string"})
        params[name]["help"] = text

    for item in param_default_items:
        name, raw_value = parse_assignment(item)
        params.setdefault(name, {"type": "string"})
        params[name]["default"] = raw_value

    for item in param_flag_items:
        name, flag = parse_string_pair(item, field_name="param-flag")
        params.setdefault(name, {"type": "string"})
        params[name]["flag"] = flag

    return params


def parse_param_spec(spec: str) -> tuple[str, str]:
    if ":" in spec:
        name, param_type = spec.split(":", 1)
    else:
        name, param_type = spec, "string"
    name = name.strip()
    param_type = param_type.strip() or "string"
    if not name:
        raise click.BadParameter("parameter name must not be empty")
    return name, param_type


def find_mount_payload(items: List[Dict[str, Any]], mount_id: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and item.get("id") == mount_id:
            return strip_internal_metadata(item)
    return None


def find_alias_payload(items: List[Dict[str, Any]], from_tokens: List[str]) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and item.get("from") == from_tokens:
            return strip_internal_metadata(item)
    return None


def path_to_str(path: Optional[Path]) -> Optional[str]:
    return str(path) if path else None


def serialize_error(exc: Exception, stage: str) -> Dict[str, Any]:
    from cts.cli.lazy import build_error_envelope

    return build_error_envelope(exc, stage)["error"]


def error_output_format(global_output: str, requested_output: Optional[str]) -> str:
    if requested_output == "json":
        return "json"
    return global_output


class ProgressSteps:
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
        self._last_rendered_width = 0

    def __enter__(self):
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

    def _clear_transient_line(self) -> None:
        if not self.enabled or self._last_rendered_width <= 0:
            return
        sys.stderr.write("\r" + (" " * self._last_rendered_width) + "\r")
        sys.stderr.flush()
        self._last_rendered_width = 0

    def _emit_status_line(self, message: str) -> None:
        self._clear_transient_line()
        click.echo(message, err=True)

    def _render_current_step(self, label: str) -> None:
        if not self.enabled:
            return
        message = f"[{self.index}/{len(self.steps)}] {label}"
        padding = max(self._last_rendered_width - len(message), 0)
        sys.stderr.write("\r" + message + (" " * padding))
        sys.stderr.flush()
        self._last_rendered_width = len(message)

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
        self._render_current_step(description)

    def update_current(self, label: str) -> None:
        if not self.enabled or self.current_step is None:
            return
        self.current_step = label
        self._render_current_step(label)

    def __exit__(self, exc_type, exc, tb):
        failed_duration = None
        if exc_type is not None:
            self.failed_step = self.current_step or self.failed_step
            if self.current_step_started_at is not None:
                failed_duration = max(time.perf_counter() - self.current_step_started_at, 0.0)
                self.failed_step_duration = failed_duration
        self._close_current_step(duration_override=failed_duration)
        if exc_type is not None and self.enabled:
            self._emit_failure()
            self._emit_summary(failed=True)
        elif self.enabled and self.step_durations:
            self._emit_summary(failed=False)
        return False


class ElapsedStatusHandle:
    def __init__(self, initial_message: str) -> None:
        self._message = initial_message

    def update(self, message: str) -> None:
        self._message = message

    @property
    def message(self) -> str:
        return self._message


@contextmanager
def status(output_format: str, message: str):
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
def elapsed_status(output_format: str, message: str, *, interval: float = 0.1):
    handle = ElapsedStatusHandle(message)
    if output_format == "json" or not bool(getattr(sys.stderr, "isatty", lambda: False)()):
        yield handle
        return
    try:
        from rich.console import Console
    except ModuleNotFoundError:
        click.echo(message, err=True)
        yield handle
        return

    console = Console(stderr=True)
    stop_event = threading.Event()
    start_time = time.perf_counter()

    def _format_message() -> str:
        elapsed = time.perf_counter() - start_time
        return f"{handle.message}  elapsed {elapsed:.1f}s"

    with console.status(_format_message()) as rich_status:
        def _ticker() -> None:
            while not stop_event.wait(interval):
                rich_status.update(_format_message())

        worker = threading.Thread(target=_ticker, name="cts-elapsed-status", daemon=True)
        worker.start()
        try:
            yield handle
        finally:
            stop_event.set()
            worker.join(timeout=max(interval * 2, 0.2))


def maybe_confirm(message: str, *, assume_yes: bool, output_format: str) -> None:
    if assume_yes or output_format == "json":
        return
    if not bool(getattr(sys.stdin, "isatty", lambda: False)()):
        return
    if not click.confirm(message, default=False):
        raise click.Abort()


def build_error_command(name: str, exc: Exception, *, fail: Any) -> click.Command:
    @click.pass_context
    def callback(ctx: click.Context) -> None:
        fail(ctx, exc, "config_load", "json")

    return click.Command(name=name, callback=callback, help="Configuration failed to load.")


def strip_internal_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_internal_metadata(item) for key, item in value.items() if not key.startswith("__")}
    if isinstance(value, list):
        return [strip_internal_metadata(item) for item in value]
    return value


def fail(
    ctx: click.Context,
    exc: Exception,
    stage: str,
    output_format: str,
    mount=None,
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> None:
    from cts.cli.lazy import build_error_envelope, render_payload
    from cts.execution.errors import exit_code_for_exception

    payload = build_error_envelope(exc, stage, mount=mount, run_id=run_id, trace_id=trace_id)
    click.echo(render_payload(payload, output_format))
    ctx.exit(exit_code_for_exception(exc, stage))
