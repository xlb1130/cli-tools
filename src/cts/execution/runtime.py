from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from cts.execution.formatter import render_text_payload

from jsonschema import Draft202012Validator

from cts.execution.errors import classify_exception
from cts.execution.help_compiler import compile_input_schema
from cts.execution.logging import redact_value
from cts.models import ErrorEnvelope, ErrorInfo, MountRecord
from cts.providers.base import ProviderError


def validate_args(schema: Dict[str, Any], args: Dict[str, Any]) -> None:
    if not schema:
        return
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(args), key=lambda error: list(error.path))
    if not errors:
        return
    messages = []
    for error in errors:
        location = ".".join(str(part) for part in error.path) or "<root>"
        messages.append(f"{location}: {error.message}")
    raise ProviderError("input validation failed: " + "; ".join(messages))


def explain_mount(app: "CTSApp", mount: MountRecord, args: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    schema = compile_input_schema(mount)
    normalized_args = apply_schema_defaults(schema, args)
    hook_payload = app.dispatch_hooks(
        "explain.before",
        {"mount": mount, "args": normalized_args, "runtime": dict(runtime)},
    )
    normalized_args = dict(hook_payload.get("args", normalized_args))
    runtime = dict(hook_payload.get("runtime", runtime))
    try:
        validate_args(schema, normalized_args)
        provider = app.get_provider(mount.source_config)
        request = _build_request(mount, normalized_args, runtime)
        plan = provider.plan(mount.source_name, mount.source_config, request, app)
        redacted_plan = app.secret_manager.redact_resolved_values(plan.model_dump(mode="json"))
        payload = {
            "ok": True,
            "mount_id": mount.mount_id,
            "stable_name": mount.stable_name,
            "source": mount.source_name,
            "provider_type": mount.provider_type,
            "operation_id": mount.operation.id,
            "risk": mount.operation.risk,
            "plan": redact_value(app, redacted_plan),
            "run_id": runtime.get("run_id") or str(uuid.uuid4()),
            "trace_id": runtime.get("trace_id"),
        }
    except Exception as exc:
        app.dispatch_hooks(
            "explain.error",
            {"mount": mount, "args": normalized_args, "runtime": runtime, "error": exc},
        )
        raise
    updated_payload = app.dispatch_hooks(
        "explain.after",
        {"mount": mount, "args": normalized_args, "runtime": runtime, "result": payload},
    )
    return dict(updated_payload.get("result", payload))


def invoke_mount(app: "CTSApp", mount: MountRecord, args: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    schema = compile_input_schema(mount)
    normalized_args = apply_schema_defaults(schema, args)
    hook_payload = app.dispatch_hooks(
        "invoke.before",
        {"mount": mount, "args": normalized_args, "runtime": dict(runtime)},
    )
    normalized_args = dict(hook_payload.get("args", normalized_args))
    runtime = dict(hook_payload.get("runtime", runtime))
    validate_args(schema, normalized_args)
    provider = app.get_provider(mount.source_config)
    request = _build_request(mount, normalized_args, runtime)
    
    # For dry_run or non-invoke scenarios, skip reliability layer for simplicity
    if request.dry_run:
        result = provider.invoke(mount.source_name, mount.source_config, request, app)
        payload = {
            "ok": result.ok,
            "mount_id": mount.mount_id,
            "stable_name": mount.stable_name,
            "source": mount.source_name,
            "provider_type": mount.provider_type,
            "operation_id": mount.operation.id,
            "data": result.data,
            "text": result.text,
            "stderr": result.stderr,
            "status_code": result.status_code,
            "metadata": result.metadata,
            "run_id": runtime.get("run_id") or str(uuid.uuid4()),
            "trace_id": runtime.get("trace_id"),
        }
        updated_payload = app.dispatch_hooks(
            "invoke.after",
            {"mount": mount, "args": normalized_args, "runtime": runtime, "result": payload},
        )
        return dict(updated_payload.get("result", payload))
    
    # Resolve reliability configuration
    reliability_config = _resolve_reliability_config(app, mount)
    
    # Get or create reliability manager
    reliability_manager = _get_reliability_manager(app)
    
    # Prepare reliability context
    reliability_ctx = reliability_manager.prepare_execution(
        mount_id=mount.mount_id,
        operation_id=mount.operation.id,
        source_name=mount.source_name,
        provider_type=mount.provider_type,
        args=normalized_args,
        run_id=runtime.get("run_id") or str(uuid.uuid4()),
        config=reliability_config,
    )
    
    # Check for duplicate execution
    if reliability_ctx.idempotency_key:
        existing = reliability_manager.check_duplicate(reliability_ctx)
        if existing and existing.status == "completed":
            app.dispatch_hooks(
                "invoke.duplicate",
                {
                    "mount": mount,
                    "args": normalized_args,
                    "runtime": runtime,
                    "existing_run_id": existing.run_id,
                },
            )
            return {
                "ok": True,
                "mount_id": mount.mount_id,
                "stable_name": mount.stable_name,
                "source": mount.source_name,
                "provider_type": mount.provider_type,
                "operation_id": mount.operation.id,
                "data": {"duplicate": True, "original_run_id": existing.run_id},
                "run_id": runtime.get("run_id") or str(uuid.uuid4()),
                "trace_id": runtime.get("trace_id"),
                "reliability": {"was_duplicate": True},
            }
    
    # Execute with reliability guarantees
    def do_invoke():
        return provider.invoke(mount.source_name, mount.source_config, request, app)
    
    try:
        reliability_result = reliability_manager.execute_with_reliability(
            reliability_ctx,
            do_invoke,
            is_idempotent=reliability_config.idempotency.required,
        )
    except Exception as exc:
        app.dispatch_hooks(
            "invoke.error",
            {"mount": mount, "args": normalized_args, "runtime": runtime, "error": exc},
        )
        raise
    
    if not reliability_result.success:
        error_payload = build_error_envelope(
            reliability_result.error,
            stage="invoke",
            mount=mount,
            run_id=runtime.get("run_id"),
            trace_id=runtime.get("trace_id"),
        )
        error_payload["reliability"] = reliability_result.to_dict()
        return error_payload
    
    result = reliability_result.result
    payload = {
        "ok": result.ok,
        "mount_id": mount.mount_id,
        "stable_name": mount.stable_name,
        "source": mount.source_name,
        "provider_type": mount.provider_type,
        "operation_id": mount.operation.id,
        "data": result.data,
        "text": result.text,
        "stderr": result.stderr,
        "status_code": result.status_code,
        "metadata": result.metadata,
        "run_id": runtime.get("run_id") or str(uuid.uuid4()),
        "trace_id": runtime.get("trace_id"),
        "reliability": reliability_result.to_dict(),
    }
    updated_payload = app.dispatch_hooks(
        "invoke.after",
        {"mount": mount, "args": normalized_args, "runtime": runtime, "result": payload},
    )
    return dict(updated_payload.get("result", payload))


def build_error_envelope(
    exc: Exception,
    stage: str,
    mount: MountRecord | None = None,
    source: str | None = None,
    provider_type: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
) -> Dict[str, Any]:
    classification = classify_exception(exc, stage)
    return ErrorEnvelope(
        error=ErrorInfo(
            type=classification.type,
            code=classification.code,
            message=str(exc),
            retryable=classification.retryable,
            stage=stage,
            source=source or (mount.source_name if mount else None),
            mount_id=mount.mount_id if mount else None,
            operation_id=mount.operation.id if mount else None,
            provider_type=provider_type or (mount.provider_type if mount else None),
            user_fixable=classification.user_fixable,
            details=classification.details,
            suggestions=classification.suggestions,
        ),
        run_id=run_id or str(uuid.uuid4()),
        trace_id=trace_id or str(uuid.uuid4()),
    ).model_dump(mode="json")


def apply_schema_defaults(schema: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(args)
    for key, property_schema in (schema.get("properties") or {}).items():
        if key not in normalized and "default" in property_schema:
            normalized[key] = property_schema["default"]
    return normalized


def render_payload(payload: Dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return render_text_payload(payload)


def _build_request(mount: MountRecord, args: Dict[str, Any], runtime: Dict[str, Any]):
    from cts.models import InvokeRequest

    return InvokeRequest(
        source=mount.source_name,
        operation_id=mount.operation.id,
        args=args,
        profile=None,
        dry_run=bool(runtime.get("dry_run")),
        non_interactive=bool(runtime.get("non_interactive")),
    )


def _resolve_reliability_config(app: "CTSApp", mount: MountRecord):
    """Resolve reliability configuration for a mount execution."""
    from cts.reliability import merge_reliability_config

    global_defaults = app.config.get_reliability_defaults() if hasattr(app, "config") and app.config else None
    
    # Get source-level reliability config
    source_reliability = None
    if mount.source_config and hasattr(mount.source_config, "reliability"):
        source_reliability = mount.source_config.reliability
    
    # Get mount-level reliability config
    mount_reliability = None
    if mount.mount_config and hasattr(mount.mount_config, "reliability"):
        mount_reliability = mount.mount_config.reliability
    
    # Get operation risk level
    operation_risk = mount.operation.risk if mount.operation else "read"
    
    return merge_reliability_config(
        global_defaults,
        source_reliability,
        mount_reliability,
        operation_risk,
    )


def _get_reliability_manager(app: "CTSApp"):
    """Get or create reliability manager for the app."""
    from pathlib import Path
    from cts.reliability import ReliabilityManager

    if not hasattr(app, "_reliability_manager"):
        global_defaults = app.config.get_reliability_defaults() if hasattr(app, "config") and app.config else None
        cache_dir = None
        if hasattr(app, "primary_config_dir"):
            cache_dir = Path(app.primary_config_dir) / ".cts_state" / "reliability"

        app._reliability_manager = ReliabilityManager(
            global_defaults=global_defaults,
            cache_dir=cache_dir,
        )

        if hasattr(app, "config") and app.config:
            for key, budget in app.config.get_rate_limit_budgets().items():
                app._reliability_manager.rate_limit_manager.register_budget(key, budget)

    return app._reliability_manager
