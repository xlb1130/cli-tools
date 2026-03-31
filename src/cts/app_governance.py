from __future__ import annotations

from typing import Any, Dict, List, Optional

from cts.app_drift import (
    aggregate_drift,
    drift_policy_key,
    is_accepting_drift_action,
    max_summary_severity,
    merge_drift_changes,
    more_restrictive_action,
)
from cts.catalog import Catalog
from cts.execution.logging import emit_app_event, utc_now_iso
from cts.models import MountRecord


def sync(app, source_name: Optional[str] = None) -> Dict[str, Any]:
    items = []
    sources = app.config.sources.items()
    if source_name:
        source = app.config.sources.get(source_name)
        if not source:
            return {"items": [], "report_path": None, "capability_snapshot_path": None}
        sources = [(source_name, source)]

    for current_name, source_config in sources:
        items.append(app._discover_source(current_name, source_config, mode="sync"))
    app.catalog = Catalog()
    app._compile_mounts()
    app._compile_aliases()
    sync_generated_at = utc_now_iso()
    drift_summary = aggregate_drift(items)
    governance = build_drift_governance(app, items, report_generated_at=sync_generated_at)
    app._drift_governance_loaded = True
    app.source_drift_state = governance["sources"]
    app.mount_drift_state = governance["mounts"]

    capability_snapshot = build_capability_snapshot(app)
    capability_snapshot_path = app.discovery_store.write_capability_snapshot(
        capability_snapshot,
        source_name=source_name,
    )
    report = {
        "version": 1,
        "kind": "sync_report",
        "generated_at": sync_generated_at,
        "requested_source": source_name,
        "profile": app.active_profile,
        "config_files": [str(path) for path in app.config_paths],
        "items": items,
        "drift_summary": drift_summary,
        "drift_governance": governance,
        "discovery_errors": dict(app.discovery_errors),
        "capability_snapshot_path": str(capability_snapshot_path),
    }
    report_path = app.discovery_store.write_sync_report(report, source_name=source_name)
    app.latest_drift_report = dict(report)
    annotate_drift_report_path(app, str(report_path))
    apply_drift_reconciliations(app)
    emit_app_event(
        app,
        event="sync_report_written",
        data={
            "requested_source": source_name,
            "report_path": str(report_path),
            "capability_snapshot_path": str(capability_snapshot_path),
            "item_count": len(items),
        },
    )
    return {
        "items": items,
        "drift_summary": report["drift_summary"],
        "drift_governance": governance,
        "report_path": str(report_path),
        "capability_snapshot_path": str(capability_snapshot_path),
    }


def build_capability_snapshot(app) -> Dict[str, Any]:
    mounts = []
    for mount in app.catalog.mounts:
        schema_info = app.get_schema_info(mount.source_name, mount.source_config, mount.operation.id)
        mounts.append(
            {
                "mount_id": mount.mount_id,
                "command_path": list(mount.command_path),
                "aliases": [list(alias) for alias in mount.aliases],
                "stable_name": mount.stable_name,
                "source": mount.source_name,
                "provider_type": mount.provider_type,
                "operation_id": mount.operation.id,
                "summary": mount.summary,
                "risk": mount.operation.risk,
                "supported_surfaces": list(mount.operation.supported_surfaces),
                "schema_provenance": schema_info[1] if schema_info else None,
                "drift_state": app.get_mount_drift_state(mount),
            }
        )

    sources = []
    for source_name, source_config in app.config.sources.items():
        sources.append(
            {
                "name": source_name,
                "type": source_config.type,
                "enabled": source_config.enabled,
                "origin_file": str(app.origin_file_for(source_config)) if app.origin_file_for(source_config) else None,
                "operation_count": len(app.source_operations.get(source_name, {})),
                "discovery_state": dict(app.discovery_state.get(source_name, {})),
                "drift_state": app.get_source_drift_state(source_name),
            }
        )

    return {
        "version": 1,
        "kind": "capability_snapshot",
        "generated_at": utc_now_iso(),
        "profile": app.active_profile,
        "config_files": [str(path) for path in app.config_paths],
        "providers": sorted(app.provider_registry.supported_types()),
        "plugins": sorted(app.config.plugins.keys()),
        "hooks": [
            {"event": hook.event, "plugin": hook.plugin, "handler": hook.handler, "fail_mode": hook.fail_mode}
            for hook in app.config.hooks
            if hook.enabled
        ],
        "plugin_provider_conflicts": app.plugin_manager.provider_conflicts,
        "sources": sources,
        "mounts": mounts,
        "conflicts": list(app.catalog.conflicts),
    }


def load_drift_governance(app) -> None:
    app._drift_governance_loaded = True
    report = app.discovery_store.load_latest_sync_report()
    if not report:
        app.latest_drift_report = None
        app.source_drift_state = {}
        app.mount_drift_state = {}
        return
    app.latest_drift_report = dict(report)
    governance = report.get("drift_governance")
    if isinstance(governance, dict):
        app.source_drift_state = {
            str(key): dict(value) for key, value in (governance.get("sources") or {}).items() if isinstance(value, dict)
        }
        app.mount_drift_state = {
            str(key): dict(value) for key, value in (governance.get("mounts") or {}).items() if isinstance(value, dict)
        }
        annotate_drift_report_path(app, str(app.discovery_store.latest_sync_report_path()))
        apply_drift_reconciliations(app)
        return
    computed = build_drift_governance(
        app,
        list(report.get("items") or []),
        report_generated_at=report.get("generated_at"),
    )
    app.source_drift_state = computed["sources"]
    app.mount_drift_state = computed["mounts"]
    annotate_drift_report_path(app, str(app.discovery_store.latest_sync_report_path()))
    apply_drift_reconciliations(app)


def ensure_drift_governance_loaded(app) -> None:
    if app._drift_governance_loaded:
        return
    if not app.load_drift_governance:
        app._drift_governance_loaded = True
        return
    load_drift_governance(app)


def annotate_drift_report_path(app, report_path: str) -> None:
    if not app.latest_drift_report:
        return
    app.latest_drift_report["report_path"] = report_path
    for source_state in app.source_drift_state.values():
        source_state.setdefault("report_path", report_path)
    for mount_state in app.mount_drift_state.values():
        mount_state.setdefault("report_path", report_path)


def build_drift_governance(
    app,
    items: List[Dict[str, Any]],
    *,
    report_generated_at: Optional[str] = None,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    sources: Dict[str, Dict[str, Any]] = {}
    mounts: Dict[str, Dict[str, Any]] = {}
    effective_generated_at = report_generated_at or utc_now_iso()
    for item in items:
        source_name = str(item.get("source") or "")
        if not source_name:
            continue
        drift = dict(item.get("drift") or {})
        affected_mount_ids: List[str] = []
        affected_aliases: List[List[str]] = []
        blocked_mount_ids: List[str] = []
        source_state = {
            "source": source_name,
            "provider_type": item.get("provider_type"),
            "drift": drift,
            "status": "clean" if not drift.get("changed") else drift.get("severity") or "changed",
            "report_generated_at": effective_generated_at,
            "affected_mount_ids": affected_mount_ids,
            "affected_aliases": affected_aliases,
            "blocked_mount_ids": blocked_mount_ids,
        }
        sources[source_name] = source_state
        if not drift.get("changed"):
            source_state["accepted_mount_ids"] = []
            source_state["accepted_mount_count"] = 0
            source_state["affected_mount_count"] = 0
            source_state["blocked_mount_count"] = 0
            continue

        all_changes_accepted = True
        for change in drift.get("changes") or []:
            change_severity = str(change.get("severity") or drift.get("severity") or "compatible").strip().lower()
            impacted = affected_mount_ids_for_change(app, source_name, change)
            affected_mount_ids.extend(item for item in impacted if item not in affected_mount_ids)
            impacted_mounts = affected_mounts_for_change(app, source_name, change)
            change_actions: List[str] = []
            for mount in impacted_mounts:
                action = resolve_drift_action(app, mount, change_severity)
                change_actions.append(action)
                state = mounts.setdefault(
                    mount.mount_id,
                    {
                        "mount_id": mount.mount_id,
                        "source": mount.source_name,
                        "operation_id": mount.operation.id,
                        "provider_type": mount.provider_type,
                        "status": "warning",
                        "blocked": False,
                        "action": action,
                        "severity": change_severity,
                        "reasons": [],
                        "changes": [],
                        "report_generated_at": effective_generated_at,
                        "aliases": [list(alias) for alias in mount.aliases],
                        "supported_surfaces": list(mount.operation.supported_surfaces),
                    },
                )
                state["action"] = more_restrictive_action(state.get("action"), action)
                state["severity"] = max_summary_severity(str(state.get("severity") or "none"), change_severity)
                if state["action"] in {"freeze_mount", "disable_mount"}:
                    state["status"] = "frozen"
                    state["blocked"] = True
                elif state["action"] == "require_manual_review":
                    state["status"] = "review_required"
                    state["blocked"] = True
                elif is_accepting_drift_action(state["action"]):
                    state["status"] = "accepted"
                    state["blocked"] = False
                else:
                    state["status"] = "warning"
                    state["blocked"] = False
                state["reasons"] = sorted(set(list(state.get("reasons") or []) + list(change.get("reasons") or [])))
                state["changes"] = merge_drift_changes(state.get("changes") or [], [change])
                for alias in state.get("aliases") or []:
                    if alias not in affected_aliases:
                        affected_aliases.append(alias)
            if not change_actions:
                change_actions.append(resolve_drift_action(app, None, change_severity, source_name=source_name))
            if not all(is_accepting_drift_action(action) for action in change_actions):
                all_changes_accepted = False
        accepted_mount_ids: List[str] = []
        for mount in app.catalog.mounts:
            if mount.source_name != source_name:
                continue
            mount_state = mounts.get(mount.mount_id)
            if not mount_state:
                continue
            if mount_state.get("blocked") and mount.mount_id not in blocked_mount_ids:
                blocked_mount_ids.append(mount.mount_id)
            if mount_state.get("status") == "accepted" and mount.mount_id not in accepted_mount_ids:
                accepted_mount_ids.append(mount.mount_id)
        source_state["affected_mount_count"] = len(affected_mount_ids)
        source_state["blocked_mount_count"] = len(blocked_mount_ids)
        source_state["accepted_mount_ids"] = accepted_mount_ids
        source_state["accepted_mount_count"] = len(accepted_mount_ids)
        if all_changes_accepted:
            source_state["status"] = "accepted"
            source_state["accepted_by_policy"] = True
    return {"sources": sources, "mounts": mounts}


def affected_mounts_for_change(app, source_name: str, change: Dict[str, Any]) -> List[MountRecord]:
    operation_id = change.get("operation_id")
    mounts = [mount for mount in app.catalog.mounts if mount.source_name == source_name]
    if operation_id:
        mounts = [mount for mount in mounts if mount.operation.id == operation_id]
    return mounts


def affected_mount_ids_for_change(app, source_name: str, change: Dict[str, Any]) -> List[str]:
    operation_id = str(change.get("operation_id") or "")
    result: List[str] = []
    for mount in affected_mounts_for_change(app, source_name, change):
        if mount.mount_id not in result:
            result.append(mount.mount_id)
    for mount_config in app.config.mounts:
        if mount_config.source != source_name:
            continue
        if mount_config.select:
            if operation_id:
                candidate = f"{mount_config.id}.{operation_id}"
                if candidate not in result:
                    result.append(candidate)
            continue
        configured_operation = mount_config.operation or mount_config.id
        if operation_id and configured_operation == operation_id and mount_config.id not in result:
            result.append(mount_config.id)
    return result


def resolve_drift_action(
    app,
    mount: Optional[MountRecord],
    severity: str,
    *,
    source_name: Optional[str] = None,
) -> str:
    mount_policy = dict(getattr(mount.mount_config, "drift_policy", {}) or {}) if mount else {}
    if mount is not None:
        source_policy = dict(getattr(mount.source_config, "drift_policy", {}) or {})
    else:
        source_config = app.config.sources.get(str(source_name or ""))
        source_policy = dict(getattr(source_config, "drift_policy", {}) or {}) if source_config else {}
    defaults = dict((app.config.drift.get("defaults") or {})) if isinstance(app.config.drift, dict) else {}
    policy_key = drift_policy_key(severity)
    alias_key = f"accept_{severity}_changes"
    for policy in [mount_policy, source_policy, defaults]:
        if not policy:
            continue
        action = policy.get(policy_key)
        if action is not None:
            return str(action).strip().lower()
        if policy.get(alias_key) is True:
            return "auto_accept"
    return "warn"


def apply_drift_reconciliations(app) -> None:
    reconciliations = app.discovery_store.load_drift_reconciliations()
    items = [item for item in reconciliations.get("items", []) if isinstance(item, dict)]
    if not items:
        return
    index = {
        (str(item.get("source") or ""), str(item.get("report_generated_at") or "")): item
        for item in items
        if item.get("source") and item.get("report_generated_at")
    }
    for source_name, state in app.source_drift_state.items():
        key = (source_name, str(state.get("report_generated_at") or ""))
        reconcile = index.get(key)
        if not reconcile:
            continue
        action = str(reconcile.get("action") or "").strip().lower()
        if action != "accept_breaking":
            continue
        state["reconciled"] = True
        state["reconcile_action"] = action
        state["reconciled_at"] = reconcile.get("updated_at")
        if state.get("status") in {"breaking", "changed"}:
            state["status"] = "accepted"
    for _, state in app.mount_drift_state.items():
        key = (str(state.get("source") or ""), str(state.get("report_generated_at") or ""))
        reconcile = index.get(key)
        if not reconcile:
            continue
        action = str(reconcile.get("action") or "").strip().lower()
        if action != "accept_breaking":
            continue
        state["blocked"] = False
        state["status"] = "accepted"
        state["reconciled"] = True
        state["reconcile_action"] = action
        state["reconciled_at"] = reconcile.get("updated_at")
