from __future__ import annotations

from typing import Any, Dict, List, Optional

from cts.app_drift import snapshot_age_seconds
from cts.discovery import compare_discovery_snapshots
from cts.execution.logging import emit_app_event, utc_now_iso


def discover_source(app, source_name: str, source_config, *, mode: str) -> Dict[str, Any]:
    cached_snapshot = app.discovery_store.load_source_snapshot(source_name)
    if mode == "compile" and source_name not in app.sync_baselines:
        app.sync_baselines[source_name] = dict(cached_snapshot["snapshot"]) if cached_snapshot else None
    cache_decision = cache_decision_for_source(source_config, mode=mode, cached=cached_snapshot)
    if cache_decision and cached_snapshot:
        state = state_from_cached_snapshot(
            source_name,
            source_config,
            cached_snapshot,
            mode=mode,
            reason=cache_decision["reason"],
            cache_age_seconds=cache_decision.get("cache_age_seconds"),
        )
        apply_source_state(app, source_name, source_config, cached_snapshot["operations"], cached_snapshot["schema_index"], state)
        app.discovery_errors.pop(source_name, None)
        emit_app_event(
            app,
            event="discover_cache_loaded",
            source=source_name,
            data={
                "provider_type": source_config.type,
                "mode": mode,
                "reason": cache_decision["reason"],
                "snapshot_path": str(cached_snapshot["path"]),
                "cache_age_seconds": cache_decision.get("cache_age_seconds"),
                "operation_count": len(cached_snapshot["operations"]),
            },
        )
        return dict(state)

    if cache_decision and not cached_snapshot:
        state = {
            "source": source_name,
            "provider_type": source_config.type,
            "ok": False,
            "usable": False,
            "fallback": None,
            "mode": mode,
            "operation_count": 0,
            "schema_count": 0,
            "snapshot_path": None,
            "snapshot_fingerprint": None,
            "generated_at": None,
            "error": "discovery cache required but no snapshot available",
            "discovery_strategy": "cache",
            "cache_status": "miss",
            "cache_age_seconds": None,
        }
        apply_source_state(app, source_name, source_config, [], {}, state)
        app.discovery_errors[source_name] = state["error"]
        emit_app_event(
            app,
            event="discover_cache_miss",
            level="ERROR",
            source=source_name,
            data={"provider_type": source_config.type, "mode": mode, "reason": cache_decision["reason"]},
        )
        return dict(state)

    provider = app.get_provider(source_config)
    hook_payload = app.dispatch_hooks(
        "discovery.before",
        {"source_name": source_name, "source_config": source_config, "provider": provider, "mode": mode},
    )
    source_config = hook_payload.get("source_config", source_config)
    provider = hook_payload.get("provider", provider)
    emit_app_event(
        app,
        event="discover_start",
        source=source_name,
        data={"provider_type": source_config.type, "mode": mode},
    )

    previous_operations = list(app.source_operations.get(source_name, {}).values())
    previous_schema_index = schema_index_for_source(app, source_name)
    previous_state = dict(app.discovery_state.get(source_name, {}))

    try:
        operations = provider.discover(source_name, source_config, app)
        emit_app_event(
            app,
            event="discover_complete",
            source=source_name,
            data={"provider_type": source_config.type, "operation_count": len(operations), "mode": mode},
        )
        completed_payload = app.dispatch_hooks(
            "discovery.after",
            {
                "source_name": source_name,
                "source_config": source_config,
                "provider": provider,
                "operations": operations,
                "mode": mode,
            },
        )
        operations = list(completed_payload.get("operations", operations))
        schema_index = capture_schema_index(app, source_name, source_config, provider, operations)
        snapshot_record = app.discovery_store.write_source_snapshot(
            source_name=source_name,
            provider_type=source_config.type,
            source_origin=str(app.origin_file_for(source_config)) if app.origin_file_for(source_config) else None,
            operations=operations,
            schema_index=schema_index,
            mode=mode,
        )
        baseline_snapshot = None
        baseline_defined = False
        if mode == "sync":
            baseline_defined = source_name in app.sync_baselines
            baseline_snapshot = app.sync_baselines.get(source_name)
        if baseline_snapshot is None and cached_snapshot and not baseline_defined:
            baseline_snapshot = cached_snapshot["snapshot"]
        drift = compare_discovery_snapshots(baseline_snapshot, snapshot_record["snapshot"])
        state = {
            "source": source_name,
            "provider_type": source_config.type,
            "ok": True,
            "usable": True,
            "fallback": None,
            "mode": mode,
            "operation_count": len(operations),
            "schema_count": len(schema_index),
            "snapshot_path": str(snapshot_record["path"]),
            "snapshot_fingerprint": snapshot_record["snapshot"].get("snapshot_fingerprint"),
            "generated_at": snapshot_record["snapshot"].get("generated_at"),
            "error": None,
            "discovery_strategy": "live",
            "cache_status": "refreshed",
            "cache_age_seconds": 0,
            "drift": drift,
        }
        apply_source_state(app, source_name, source_config, operations, schema_index, state)
        app.discovery_errors.pop(source_name, None)
        emit_app_event(
            app,
            event="discover_snapshot_written",
            source=source_name,
            data={
                "provider_type": source_config.type,
                "mode": mode,
                "snapshot_path": str(snapshot_record["path"]),
                "schema_count": len(schema_index),
            },
        )
        if drift.get("changed"):
            emit_app_event(
                app,
                event="drift_detected",
                level="WARNING" if drift.get("severity") == "breaking" else "INFO",
                source=source_name,
                data={
                    "provider_type": source_config.type,
                    "severity": drift.get("severity"),
                    "status": drift.get("status"),
                    "summary": drift.get("summary"),
                },
            )
        if mode == "sync":
            app.sync_baselines[source_name] = dict(snapshot_record["snapshot"])
        return dict(state)
    except Exception as exc:  # pragma: no cover
        app.discovery_errors[source_name] = str(exc)
        app.dispatch_hooks(
            "discovery.error",
            {
                "source_name": source_name,
                "source_config": source_config,
                "provider": provider,
                "error": exc,
                "mode": mode,
            },
        )
        emit_app_event(
            app,
            event="discover_failed",
            level="ERROR",
            source=source_name,
            data={"provider_type": source_config.type, "error": str(exc), "mode": mode},
        )

        fallback = None
        operations = []
        schema_index: Dict[str, Dict[str, Any]] = {}
        snapshot_path = None
        snapshot_fingerprint = None
        generated_at = None

        if previous_operations:
            fallback = "memory"
            operations = previous_operations
            schema_index = previous_schema_index
            snapshot_path = previous_state.get("snapshot_path")
            snapshot_fingerprint = previous_state.get("snapshot_fingerprint")
            generated_at = previous_state.get("generated_at")
        else:
            cached = app.discovery_store.load_source_snapshot(source_name)
            if cached:
                fallback = "cache"
                operations = cached["operations"]
                schema_index = cached["schema_index"]
                snapshot_path = str(cached["path"])
                snapshot_fingerprint = cached["snapshot"].get("snapshot_fingerprint")
                generated_at = cached["snapshot"].get("generated_at")

        state = {
            "source": source_name,
            "provider_type": source_config.type,
            "ok": False,
            "usable": bool(operations),
            "fallback": fallback,
            "mode": mode,
            "operation_count": len(operations),
            "schema_count": len(schema_index),
            "snapshot_path": snapshot_path,
            "snapshot_fingerprint": snapshot_fingerprint,
            "generated_at": generated_at,
            "error": str(exc),
            "discovery_strategy": "fallback" if fallback else "live",
            "cache_status": fallback or "miss",
            "cache_age_seconds": snapshot_age_seconds(generated_at),
            "drift": None,
        }
        apply_source_state(app, source_name, source_config, operations, schema_index, state)
        if fallback:
            emit_app_event(
                app,
                event="discover_fallback_loaded",
                level="WARNING",
                source=source_name,
                data={
                    "provider_type": source_config.type,
                    "mode": mode,
                    "fallback": fallback,
                    "operation_count": len(operations),
                    "snapshot_path": snapshot_path,
                },
            )
        return dict(state)


def cache_decision_for_source(source_config, *, mode: str, cached: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if mode == "help":
        if cached:
            return {"reason": "help_cached_snapshot"}
        return None
    discovery_mode = str(source_config.discovery.mode or "manual").lower()
    if mode == "sync":
        return None
    if discovery_mode == "cache_only":
        return {"reason": "cache_only"}
    if discovery_mode != "live":
        return None
    ttl = source_config.discovery.cache_ttl
    if ttl is None or ttl < 0 or not cached:
        return None
    cache_age_seconds = snapshot_age_seconds(cached["snapshot"].get("generated_at"))
    if cache_age_seconds is None:
        return None
    if cache_age_seconds <= ttl:
        return {"reason": "cache_ttl", "cache_age_seconds": cache_age_seconds}
    return None


def state_from_cached_snapshot(source_name: str, source_config, cached: Dict[str, Any], *, mode: str, reason: str, cache_age_seconds: Optional[int]) -> Dict[str, Any]:
    snapshot = cached["snapshot"]
    operations = cached["operations"]
    schema_index = cached["schema_index"]
    return {
        "source": source_name,
        "provider_type": source_config.type,
        "ok": True,
        "usable": True,
        "fallback": None,
        "mode": mode,
        "operation_count": len(operations),
        "schema_count": len(schema_index),
        "snapshot_path": str(cached["path"]),
        "snapshot_fingerprint": snapshot.get("snapshot_fingerprint"),
        "generated_at": snapshot.get("generated_at"),
        "error": None,
        "discovery_strategy": "cache",
        "cache_status": reason,
        "cache_age_seconds": cache_age_seconds,
    }


def apply_source_state(app, source_name: str, source_config, operations: List[Any], schema_index: Dict[str, Dict[str, Any]], state: Dict[str, Any]) -> None:
    app.source_operations[source_name] = {operation.id: operation for operation in operations}
    app.schema_cache[source_name] = {}
    app.schema_provenance_index[source_name] = {}

    for operation in operations:
        schema_record = dict(schema_index.get(operation.id) or {})
        schema = dict(schema_record.get("input_schema") or operation.input_schema or {})
        provenance = schema_record.get("provenance") or default_schema_provenance(app, source_config, operation)
        if schema:
            operation.input_schema = schema
        remember_schema_info(app, source_name, operation.id, schema, provenance)

    app.discovery_state[source_name] = dict(state)


def capture_schema_index(app, source_name: str, source_config, provider: Any, operations: List[Any]) -> Dict[str, Dict[str, Any]]:
    schema_index: Dict[str, Dict[str, Any]] = {}
    for operation in operations:
        schema = dict(operation.input_schema or {})
        provenance: Optional[Dict[str, Any]] = None
        try:
            schema_info = provider.get_schema(source_name, source_config, operation.id, app)
        except Exception as exc:  # pragma: no cover
            emit_app_event(
                app,
                event="schema_capture_failed",
                level="WARNING",
                source=source_name,
                operation_id=operation.id,
                data={"provider_type": source_config.type, "error": str(exc)},
            )
            schema_info = None

        if schema_info:
            schema = dict(schema_info[0] or schema or {})
            provenance = dict(schema_info[1] or {})
        elif schema:
            provenance = default_schema_provenance(app, source_config, operation)

        if not schema and not provenance:
            continue
        if schema:
            operation.input_schema = schema
        schema_index[operation.id] = {"input_schema": schema, "provenance": provenance}
    return schema_index


def schema_index_for_source(app, source_name: str) -> Dict[str, Dict[str, Any]]:
    schema_index: Dict[str, Dict[str, Any]] = {}
    for operation_id, operation in app.source_operations.get(source_name, {}).items():
        schema = dict(app.schema_cache.get(source_name, {}).get(operation_id) or operation.input_schema or {})
        provenance = app.schema_provenance_index.get(source_name, {}).get(operation_id)
        if not schema and not provenance:
            continue
        schema_index[operation_id] = {"input_schema": schema, "provenance": dict(provenance) if provenance else None}
    return schema_index


def schema_info_from_memory(app, source_name: str, operation_id: str) -> Optional[tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    schema = app.schema_cache.get(source_name, {}).get(operation_id)
    provenance = app.schema_provenance_index.get(source_name, {}).get(operation_id)
    if schema is None and provenance is None:
        return None

    resolved_schema = dict(schema or {})
    if not resolved_schema:
        operation = app.source_operations.get(source_name, {}).get(operation_id)
        resolved_schema = dict(operation.input_schema or {}) if operation else {}
    return resolved_schema, dict(provenance) if provenance else None


def remember_schema_info(app, source_name: str, operation_id: str, schema: Dict[str, Any], provenance: Optional[Dict[str, Any]]) -> None:
    normalized_schema = dict(schema or {})
    normalized_provenance = dict(provenance or {})
    if normalized_provenance and normalized_provenance.get("fetched_at") is None:
        normalized_provenance["fetched_at"] = utc_now_iso()
    app.schema_cache.setdefault(source_name, {})[operation_id] = normalized_schema
    if normalized_provenance:
        app.schema_provenance_index.setdefault(source_name, {})[operation_id] = normalized_provenance


def default_schema_provenance(app, source_config, operation) -> Dict[str, Any]:
    if source_config.type == "openapi" and source_config.spec:
        spec_origin = source_config.spec.get("path") or source_config.spec.get("file") or source_config.spec.get("url")
        if spec_origin and source_config.spec.get("path"):
            spec_origin = str(app.resolve_path(str(spec_origin), owner=source_config))
        return {"strategy": "authoritative", "origin": spec_origin or "openapi", "confidence": 1.0, "fetched_at": utc_now_iso()}
    if source_config.type == "graphql" and source_config.schema_config:
        schema_origin = source_config.schema_config.get("path") or source_config.schema_config.get("file") or source_config.schema_config.get("url") or source_config.endpoint or source_config.base_url or "graphql"
        if source_config.schema_config.get("path") or source_config.schema_config.get("file"):
            schema_origin = str(app.resolve_path(str(schema_origin), owner=source_config))
        return {"strategy": "authoritative", "origin": schema_origin, "confidence": 1.0, "fetched_at": utc_now_iso()}
    manifest = source_config.discovery.manifest
    if operation.provider_config.get("discovered_via") == "mcp_bridge":
        return {"strategy": "probed", "origin": operation.provider_config.get("discovered_origin", "mcp"), "confidence": 0.95, "fetched_at": utc_now_iso()}
    if operation.id in source_config.operations:
        return {"strategy": "manual", "origin": "source.operations", "confidence": 1.0, "fetched_at": utc_now_iso()}
    if manifest:
        return {"strategy": "declared", "origin": str(app.resolve_path(manifest, owner=source_config)), "confidence": 0.9, "fetched_at": utc_now_iso()}
    return {"strategy": source_config.discovery.schema_strategy or "declared", "origin": source_config.type, "confidence": 0.6, "fetched_at": utc_now_iso()}
