from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from cts.discovery import resolve_discovery_paths
from cts.execution.help_compiler import compile_command_help
from cts.execution.logging import list_app_events, resolve_runtime_paths
from cts.plugins.contracts import get_hook_contract, list_hook_contracts


def build_app_summary(app) -> Dict[str, Any]:
    runtime_paths = resolve_runtime_paths(app)
    discovery_paths = resolve_discovery_paths(app)
    surfaces = _summarize_surfaces(app)
    auth_summary = app.auth_manager.build_summary()
    secret_summary = app.secret_manager.build_summary()
    reliability_summary = build_reliability_summary(app)
    return {
        "app": app.config.app.name,
        "profile": app.active_profile,
        "config_files": [str(path) for path in app.config_paths],
        "source_count": len(app.config.sources),
        "mount_count": len(app.catalog.mounts),
        "plugin_count": len(app.config.plugins),
        "hook_count": len(app.config.hooks),
        "secrets": secret_summary,
        "auth": auth_summary,
        "reliability": reliability_summary,
        "plugin_provider_conflicts": app.plugin_manager.provider_conflicts,
        "surfaces": surfaces,
        "runtime_paths": {
            "app_log": str(runtime_paths.app_log),
            "audit_log": str(runtime_paths.audit_log),
            "history_db": str(runtime_paths.history_db),
            "cache_dir": str(discovery_paths.cache_dir),
            "discovery_cache_dir": str(discovery_paths.source_cache_dir),
            "sync_report_dir": str(discovery_paths.sync_report_dir),
            "capability_snapshot_dir": str(discovery_paths.capability_snapshot_dir),
        },
        "discovery_error_count": len(app.discovery_errors),
    }


def build_reliability_status(app) -> Dict[str, Any]:
    from cts.execution.runtime import _get_reliability_manager

    manager = _get_reliability_manager(app)
    status = manager.get_status()
    defaults = app.config.get_reliability_defaults() if hasattr(app, "config") and app.config else None
    budgets = app.config.get_rate_limit_budgets() if hasattr(app, "config") and app.config else {}

    return {
        "defaults": defaults.model_dump(mode="json") if defaults else None,
        "configured_budget_count": len(budgets),
        "configured_budgets": {key: budget.model_dump(mode="json") for key, budget in budgets.items()},
        "status": status,
    }


def build_reliability_summary(app) -> Dict[str, Any]:
    payload = build_reliability_status(app)
    status = payload["status"]
    rate_limits = status.get("rate_limits", {})
    concurrency = status.get("concurrency", {})
    idempotency = status.get("idempotency", {})

    return {
        "configured_budget_count": payload.get("configured_budget_count", 0),
        "active_rate_limiters": len(rate_limits),
        "active_concurrency_scopes": len(concurrency),
        "tracked_idempotency_keys": int(idempotency.get("total_records", 0) or 0),
    }


def build_auth_inventory(app) -> Dict[str, Any]:
    items = app.auth_manager.list_profiles()
    return {
        "items": items,
        "summary": app.auth_manager.build_summary(),
    }


def build_auth_profile(app, name: str) -> Dict[str, Any]:
    if name not in app.config.auth_profiles:
        raise KeyError(f"auth profile not found: {name}")
    return app.auth_manager.get_profile_status(name)


def build_secret_inventory(app) -> Dict[str, Any]:
    return {
        "items": app.secret_manager.list_secrets(),
        "summary": app.secret_manager.build_summary(),
    }


def build_secret_detail(app, name: str) -> Dict[str, Any]:
    return app.secret_manager.get_secret_status(name)


def build_extensions_summary(app) -> Dict[str, Any]:
    plugins = app.plugin_manager.describe_plugins()
    hooks = app.plugin_manager.describe_hooks()
    providers = build_provider_inventory(app)["items"]
    recent_events = build_extension_events(app, limit=20)["items"]

    hooks_by_event: Dict[str, int] = {}
    for hook in hooks:
        if not hook.get("enabled"):
            continue
        event = str(hook.get("event") or "")
        hooks_by_event[event] = hooks_by_event.get(event, 0) + 1

    return {
        "plugin_count": len(plugins),
        "provider_count": len(providers),
        "plugin_provider_count": len([item for item in providers if item.get("owner_type") == "plugin"]),
        "core_provider_count": len([item for item in providers if item.get("owner_type") == "core"]),
        "hook_count": len(hooks),
        "enabled_hook_count": len([item for item in hooks if item.get("enabled")]),
        "provider_conflict_count": len(app.plugin_manager.provider_conflicts),
        "hooks_by_event": [
            {"event": event, "count": count}
            for event, count in sorted(hooks_by_event.items())
        ],
        "recent_event_count": len(recent_events),
    }


def build_plugin_inventory(app) -> Dict[str, Any]:
    items = []
    for plugin in app.plugin_manager.describe_plugins():
        items.append(
            {
                **plugin,
                "origin_file": path_to_str(app.origin_file_for(app.config.plugins.get(plugin["name"]))),
            }
        )
    return {"items": items, "provider_conflicts": app.plugin_manager.provider_conflicts}


def build_provider_inventory(app) -> Dict[str, Any]:
    items = []
    for provider_type in sorted(app.provider_registry.supported_types()):
        provider = app.provider_registry.get(provider_type)
        owner = app.plugin_manager.provider_owner(provider_type)
        source_names = sorted([name for name, source in app.config.sources.items() if source.type == provider_type])
        mount_ids = sorted([mount.mount_id for mount in app.catalog.mounts if mount.provider_type == provider_type])
        conflicts = [item for item in app.plugin_manager.provider_conflicts if item.get("provider_type") == provider_type]
        items.append(
            {
                "provider_type": provider_type,
                "owner_type": owner["owner_type"],
                "owner_name": owner["owner_name"],
                "class_name": provider.__class__.__name__,
                "module": provider.__class__.__module__,
                "source_names": source_names,
                "source_count": len(source_names),
                "mount_ids": mount_ids,
                "mount_count": len(mount_ids),
                "conflicts": conflicts,
                "conflict_count": len(conflicts),
            }
        )
    return {"items": items}


def build_hook_inventory(app, *, event: Optional[str] = None, plugin: Optional[str] = None) -> Dict[str, Any]:
    items = []
    for hook in app.plugin_manager.describe_hooks():
        if event and hook.get("event") != event:
            continue
        if plugin and hook.get("plugin") != plugin:
            continue
        items.append(hook)
    return {"items": items}


def build_hook_contracts() -> Dict[str, Any]:
    return {
        "version": 1,
        "items": list_hook_contracts(),
    }


def build_extension_events(
    app,
    *,
    limit: int = 50,
    event: Optional[str] = None,
    plugin: Optional[str] = None,
    hook_event: Optional[str] = None,
    level: Optional[str] = None,
    mount_id: Optional[str] = None,
    source: Optional[str] = None,
    before_ts: Optional[str] = None,
) -> Dict[str, Any]:
    items = list_app_events(
        app,
        limit=limit,
        event_prefixes=[
            "hook_dispatch_",
            "hook_failed",
            "surface_reload_",
            "surface_sync_",
            "surface_http_",
        ],
        events=[event] if event else None,
        plugin=plugin,
        hook_event=hook_event,
        level=level,
        mount_id=mount_id,
        source=source,
        before_ts=before_ts,
    )
    return {
        "items": items,
        "filters": {
            "event": event,
            "plugin": plugin,
            "hook_event": hook_event,
            "level": level,
            "mount_id": mount_id,
            "source": source,
            "before_ts": before_ts,
            "limit": limit,
        },
        "next_before_ts": items[-1]["ts"] if items else None,
    }


def build_source_summary(app, source_name: str, source) -> Dict[str, Any]:
    return {
        "name": source_name,
        "type": source.type,
        "enabled": source.enabled,
        "auth_ref": source.auth_ref,
        "auth": app.auth_manager.auth_state_for_source(source_name, source),
        "discovery_mode": source.discovery.mode,
        "operation_count": len(app.source_operations.get(source_name, {})),
        "origin_file": path_to_str(app.origin_file_for(source)),
        "expose_to_surfaces": list(source.expose_to_surfaces),
        "profile_scope": list(source.profile_scope),
        "discovery_state": dict(app.discovery_state.get(source_name, {})),
        "drift_state": app.get_source_drift_state(source_name),
    }


def build_source_details(app, source_name: str, source) -> Dict[str, Any]:
    payload = strip_internal_metadata(source.model_dump(mode="json", by_alias=True))
    payload.update(
        {
            "name": source_name,
            "origin_file": path_to_str(app.origin_file_for(source)),
            "operation_ids": sorted(app.source_operations.get(source_name, {}).keys()),
            "compiled_operation_count": len(app.source_operations.get(source_name, {})),
            "operations": [item.model_dump(mode="json") for item in app.source_operations.get(source_name, {}).values()],
            "discovery_state": dict(app.discovery_state.get(source_name, {})),
            "drift_state": app.get_source_drift_state(source_name),
            "auth": app.auth_manager.auth_state_for_source(source_name, source),
            "schema_provenance": {
                operation_id: dict(provenance)
                for operation_id, provenance in app.schema_provenance_index.get(source_name, {}).items()
            },
        }
    )
    return payload


def build_source_check_result(app, source_name: str, source) -> Dict[str, Any]:
    provider = app.get_provider(source)
    auth_state = app.auth_manager.auth_state_for_source(source_name, source)
    provider_health = provider.healthcheck(source_name, source, app)
    auth_ok = not auth_state.get("required") or auth_state.get("state") in {"active", "expiring"}
    return {
        "source": source_name,
        "origin_file": path_to_str(app.origin_file_for(source)),
        "operation_count": len(app.source_operations.get(source_name, {})),
        "discovery_state": dict(app.discovery_state.get(source_name, {})),
        "auth": auth_state,
        "provider_ok": provider_health.get("ok", False),
        **provider_health,
        "ok": bool(provider_health.get("ok", False) and auth_ok),
    }


def build_mount_details(app, mount) -> Dict[str, Any]:
    schema_info = app.get_schema_info(mount.source_name, mount.source_config, mount.operation.id)
    return {
        "mount_id": mount.mount_id,
        "command_path": mount.command_path,
        "aliases": mount.aliases,
        "stable_name": mount.stable_name,
        "source": mount.source_name,
        "provider_type": mount.provider_type,
        "operation_id": mount.operation.id,
        "risk": mount.operation.risk,
        "supported_surfaces": list(mount.operation.supported_surfaces),
        "summary": mount.summary,
        "description": mount.description,
        "generated": mount.generated,
        "generated_from": mount.generated_from,
        "origin_file": path_to_str(app.origin_file_for(mount.mount_config)),
        "source_origin_file": path_to_str(app.origin_file_for(mount.source_config)),
        "machine": strip_internal_metadata(mount.mount_config.machine.model_dump(mode="json")),
        "help": strip_internal_metadata(mount.mount_config.help.model_dump(mode="json")),
        "params": strip_internal_metadata(
            {name: param.model_dump(mode="json") for name, param in mount.mount_config.params.items()}
        ),
        "operation": mount.operation.model_dump(mode="json"),
        "schema_provenance": schema_info[1] if schema_info else None,
        "drift_state": app.get_mount_drift_state(mount),
    }


def build_mount_help(app, mount) -> Dict[str, Any]:
    provider = app.get_provider(mount.source_config)
    provider_help = provider.get_help(mount.source_name, mount.source_config, mount.operation.id, app)
    schema_info = app.get_schema_info(mount.source_name, mount.source_config, mount.operation.id)
    hook_payload = app.dispatch_hooks(
        "help.before",
        {
            "mount": mount,
            "provider_help": provider_help,
            "schema_info": schema_info,
        },
    )
    provider_help = hook_payload.get("provider_help", provider_help)
    schema_info = hook_payload.get("schema_info", schema_info)
    help_content = compile_command_help(
        mount,
        provider_help=provider_help,
        schema_provenance=schema_info[1] if schema_info else None,
    )
    payload = {
        "mount_id": mount.mount_id,
        "stable_name": mount.stable_name,
        "summary": help_content["short_help"],
        "description": help_content["description"],
        "epilog": help_content["epilog"],
        "detail_rows": help_content["detail_rows"],
        "note_rows": help_content["note_rows"],
        "example_rows": help_content["example_rows"],
        "reference_rows": help_content["reference_rows"],
        "risk": mount.operation.risk,
        "supported_surfaces": list(mount.operation.supported_surfaces),
        "usage": "cts " + " ".join(mount.command_path) + " [OPTIONS]",
        "schema_provenance": schema_info[1] if schema_info else None,
        "drift_state": app.get_mount_drift_state(mount),
    }
    drift_state = payload.get("drift_state")
    if drift_state:
        payload["description"] = (
            (payload.get("description") or "")
            + "\n\nDrift status:\n"
            + f"- status={drift_state.get('status')} action={drift_state.get('action')}\n"
            + "- reasons="
            + ", ".join(drift_state.get("reasons") or [])
        ).strip()
        payload["epilog"] = (
            (payload.get("epilog") or "")
            + "\n\nDrift policy:\n"
            + f"- blocked={drift_state.get('blocked')}\n"
            + f"- report_generated_at={drift_state.get('report_generated_at')}"
        ).strip()
    updated_payload = app.dispatch_hooks(
        "help.after",
        {"mount": mount, "help": payload},
    )
    return dict(updated_payload.get("help", payload))


def path_to_str(path: Optional[Path]) -> Optional[str]:
    return str(path) if path else None


def strip_internal_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_internal_metadata(item) for key, item in value.items() if not key.startswith("__")}
    if isinstance(value, list):
        return [strip_internal_metadata(item) for item in value]
    return value


def filter_mount_summary(item: Dict[str, Any], *, q: Optional[str], risk: Optional[str], source: Optional[str], surface: Optional[str]) -> bool:
    if q:
        haystack = " ".join(
            [
                item.get("mount_id", ""),
                item.get("stable_name", ""),
                " ".join(item.get("command_path", [])),
                item.get("source", ""),
                item.get("summary", ""),
            ]
        ).lower()
        if q.lower() not in haystack:
            return False
    if risk and item.get("risk") != risk:
        return False
    if source and item.get("source") != source:
        return False
    if surface and surface not in (item.get("supported_surfaces") or []):
        return False
    return True


def _summarize_surfaces(app) -> Dict[str, bool]:
    mount_surfaces = set()
    for mount in app.catalog.mounts:
        mount_surfaces.update(mount.operation.supported_surfaces or [])
    mount_surfaces.update({"cli", "invoke"})
    return {surface: surface in mount_surfaces for surface in ["cli", "invoke", "mcp", "http", "jsonrpc", "ui"]}
