from __future__ import annotations

import time
import uuid
from contextlib import nullcontext
from typing import Any, Callable, Dict

import click

from cts.cli.lazy import build_error_envelope, explain_mount, extract_request_args, invoke_mount, render_payload
from cts.execution.errors import exit_code_for_exception
from cts.execution.logging import emit_app_event, emit_audit_event, record_run, summarize_result, utc_now_iso


def build_dynamic_callback(
    mount,
    *,
    get_app: Callable,
    fail: Callable,
    error_output_format: Callable,
    elapsed_status: Callable,
    run_mount_command: Callable,
):
    @click.pass_context
    def callback(ctx, **kwargs):
        output_format = error_output_format(ctx, kwargs.get("output_format"))
        status_label = f"Invoke {mount.mount_id}"
        start_perf = time.perf_counter()
        try:
            with elapsed_status(output_format, status_label):
                app = get_app(ctx, mode="invoke")
                runtime_mount = app.catalog.find_by_id(mount.mount_id) or mount
                run_mount_command(
                    app,
                    runtime_mount,
                    kwargs,
                    mode="invoke",
                    start_perf=start_perf,
                    show_elapsed_status=False,
                )
        except Exception as exc:
            fail(ctx, exc, "config_load", output_format)
            return

    return callback


def run_mount_command(
    app,
    mount,
    kwargs: Dict[str, Any],
    mode: str,
    *,
    fail: Callable,
    elapsed_status: Callable,
    start_perf: float | None = None,
    show_elapsed_status: bool = True,
) -> None:
    output_format = kwargs.get("output_format") or getattr(app, "global_output", "text")
    run_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    started_at = utc_now_iso()
    if start_perf is None:
        start_perf = time.perf_counter()

    try:
        payload, runtime = extract_request_args(kwargs)
        runtime["run_id"] = run_id
        runtime["trace_id"] = trace_id
        app.ensure_mount_execution_allowed(mount, mode=mode, run_id=run_id, trace_id=trace_id)
        emit_app_event(
            app,
            event=f"{mode}_start",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"args": payload, "provider_type": mount.provider_type},
        )
        status_label = f"{mode.title()} {mount.mount_id}"
        execution_context = elapsed_status(output_format, status_label) if show_elapsed_status else nullcontext()
        with execution_context:
            if mode == "explain":
                result = explain_mount(app, mount, payload, runtime)
            else:
                result = invoke_mount(app, mount, payload, runtime)
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        if isinstance(result, dict):
            result.setdefault("mode", mode)
            result.setdefault("risk", mount.operation.risk)
            result.setdefault("summary", mount.summary or mount.operation.title)
            result.setdefault("command_path", list(mount.command_path))
            result.setdefault("started_at", started_at)
            result.setdefault("finished_at", utc_now_iso())
            result.setdefault("duration_ms", duration_ms)
        emit_app_event(
            app,
            event=f"{mode}_complete",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"result": summarize_result(result)},
        )
        emit_audit_event(
            app,
            event=f"{mode}_complete",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"ok": result.get("ok"), "risk": mount.operation.risk, "provider_type": mount.provider_type},
        )
        record_run(
            app,
            {
                "run_id": run_id,
                "trace_id": trace_id,
                "ts_start": started_at,
                "ts_end": result.get("finished_at") if isinstance(result, dict) else utc_now_iso(),
                "surface": "cli",
                "mode": mode,
                "ok": result.get("ok", False),
                "exit_code": 0 if result.get("ok") else 6,
                "profile": app.active_profile,
                "mount_id": mount.mount_id,
                "stable_name": mount.stable_name,
                "source": mount.source_name,
                "operation_id": mount.operation.id,
                "provider_type": mount.provider_type,
                "summary": mount.summary or mount.operation.title,
                "metadata": {"result": summarize_result(result), "duration_ms": result.get("duration_ms") if isinstance(result, dict) else None},
            },
        )
        click.echo(render_payload(result, output_format))
    except Exception as exc:
        exit_code = exit_code_for_exception(exc, mode)
        error_payload = build_error_envelope(exc, mode, mount=mount, run_id=run_id, trace_id=trace_id)
        emit_app_event(
            app,
            event=f"{mode}_failed",
            level="ERROR",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"error": error_payload["error"], "exit_code": exit_code},
        )
        emit_audit_event(
            app,
            event=f"{mode}_failed",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"error_type": error_payload["error"]["type"], "error_code": error_payload["error"]["code"]},
        )
        record_run(
            app,
            {
                "run_id": run_id,
                "trace_id": trace_id,
                "ts_start": started_at,
                "ts_end": utc_now_iso(),
                "surface": "cli",
                "mode": mode,
                "ok": False,
                "exit_code": exit_code,
                "profile": app.active_profile,
                "mount_id": mount.mount_id,
                "stable_name": mount.stable_name,
                "source": mount.source_name,
                "operation_id": mount.operation.id,
                "provider_type": mount.provider_type,
                "summary": mount.summary or mount.operation.title,
                "error_type": error_payload["error"]["type"],
                "error_code": error_payload["error"]["code"],
                "metadata": {"error": error_payload["error"]},
            },
        )
        fail(click.get_current_context(), exc, mode, output_format, mount=mount, run_id=run_id, trace_id=trace_id)
