from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.app import CTSApp, tokenize_identifier
from cts.config.editor import (
    apply_update,
    conflict_signatures,
    ensure_list,
    ensure_mapping,
    prepare_edit_session,
)
from cts.execution.errors import RegistryError
from cts.presentation import build_mount_details, build_source_details


def add_source(
    *,
    explicit_config_path: Optional[str],
    profile: Optional[str],
    provider_type: str,
    source_name: str,
    description: Optional[str] = None,
    executable: Optional[str] = None,
    base_url: Optional[str] = None,
    manifest: Optional[str] = None,
    discover_mode: Optional[str] = None,
    auth_ref: Optional[str] = None,
    surfaces: Optional[List[str]] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    config_path = Path(explicit_config_path).resolve() if explicit_config_path else None
    session = prepare_edit_session(config_path)
    app = CTSApp(
        session.loaded,
        active_profile=profile,
        explicit_config_path=explicit_config_path,
        requested_profile=profile,
    )

    normalized_provider_type = provider_type.lower().strip()
    if source_name in app.config.sources:
        raise RegistryError(f"source already exists: {source_name}", code="source_exists")
    available_types = app.provider_registry.supported_types()
    if available_types and normalized_provider_type not in available_types:
        raise RegistryError(
            f"unsupported provider type: {provider_type}",
            code="provider_type_unsupported",
        )

    def mutator(payload: Dict[str, Any]) -> None:
        sources = ensure_mapping(payload, "sources")
        source_payload: Dict[str, Any] = {"type": normalized_provider_type, "enabled": enabled}
        if description:
            source_payload["description"] = description
        if executable:
            source_payload["executable"] = executable
        if base_url:
            source_payload["base_url"] = base_url
        if auth_ref:
            source_payload["auth_ref"] = auth_ref
        if surfaces:
            source_payload["expose_to_surfaces"] = list(surfaces)
        if manifest or discover_mode:
            discovery_payload: Dict[str, Any] = {}
            if manifest:
                discovery_payload["manifest"] = manifest
            if discover_mode:
                discovery_payload["mode"] = discover_mode
            source_payload["discovery"] = discovery_payload
        sources[source_name] = source_payload

    updated, _ = apply_update(session, mutator, compile_runtime=False, profile=profile)
    return {
        "ok": True,
        "action": "source_add",
        "source_name": source_name,
        "provider_type": normalized_provider_type,
        "file": str(session.target_path),
        "created_file": session.created,
        "warnings": list(session.warnings),
        "config": updated.get("sources", {}).get(source_name),
    }


def remove_source(
    *,
    explicit_config_path: Optional[str],
    profile: Optional[str],
    source_name: str,
    force: bool = False,
) -> Dict[str, Any]:
    config_path = Path(explicit_config_path).resolve() if explicit_config_path else None
    session = prepare_edit_session(config_path)
    app = CTSApp(
        session.loaded,
        active_profile=profile,
        explicit_config_path=explicit_config_path,
        requested_profile=profile,
    )
    if source_name not in app.config.sources:
        raise RegistryError(f"source not found: {source_name}", code="source_not_found")

    dependent_mounts = [mount for mount in app.catalog.mounts if mount.source_name == source_name]
    if dependent_mounts and not force:
        raise RegistryError(
            f"source '{source_name}' has {len(dependent_mounts)} dependent mount(s)",
            code="source_has_dependents",
        )

    def mutator(payload: Dict[str, Any]) -> None:
        sources = payload.get("sources", {})
        if isinstance(sources, dict) and source_name in sources:
            del sources[source_name]
            if not sources:
                payload.pop("sources", None)

        if dependent_mounts:
            mounts = payload.get("mounts", [])
            if isinstance(mounts, list):
                remaining = [
                    item for item in mounts if not (isinstance(item, dict) and item.get("source") == source_name)
                ]
                if remaining:
                    payload["mounts"] = remaining
                else:
                    payload.pop("mounts", None)

    apply_update(session, mutator, compile_runtime=False, profile=profile)
    return {
        "ok": True,
        "action": "source_remove",
        "source_name": source_name,
        "file": str(session.target_path),
        "removed_mounts": [mount.mount_id for mount in dependent_mounts],
    }


def add_mount(
    *,
    explicit_config_path: Optional[str],
    profile: Optional[str],
    source_name: str,
    operation_id: str,
    mount_id: Optional[str] = None,
    command_path: Optional[str] = None,
    stable_name: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    risk: Optional[str] = None,
    surfaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    config_path = Path(explicit_config_path).resolve() if explicit_config_path else None
    session = prepare_edit_session(config_path)
    app = CTSApp(
        session.loaded,
        active_profile=profile,
        explicit_config_path=explicit_config_path,
        requested_profile=profile,
    )
    if source_name not in app.config.sources:
        raise RegistryError(f"source not found: {source_name}", code="source_not_found")

    operations = app.source_operations.get(source_name, {})
    if operation_id not in operations:
        raise RegistryError(f"operation not found: {source_name}.{operation_id}", code="operation_not_found")

    final_mount_id = mount_id or f"{source_name}-{operation_id}".replace(".", "-").replace("_", "-")
    if app.catalog.find_by_id(final_mount_id) is not None:
        raise RegistryError(f"mount already exists: {final_mount_id}", code="mount_exists")

    final_command_path = [part for part in (command_path or "").strip().split() if part] or tokenize_identifier(operation_id)
    baseline_conflicts = conflict_signatures(app.catalog.conflicts)

    def mutator(payload: Dict[str, Any]) -> None:
        mounts = ensure_list(payload, "mounts")
        mount_payload: Dict[str, Any] = {
            "id": final_mount_id,
            "source": source_name,
            "operation": operation_id,
            "command": {"path": final_command_path},
        }
        if stable_name or surfaces:
            mount_payload["machine"] = {}
            if stable_name:
                mount_payload["machine"]["stable_name"] = stable_name
            if surfaces:
                mount_payload["machine"]["expose_via"] = list(surfaces)
        if summary or description:
            mount_payload["help"] = {}
            if summary:
                mount_payload["help"]["summary"] = summary
            if description:
                mount_payload["help"]["description"] = description
        if risk:
            mount_payload["policy"] = {"risk": risk}
        mounts.append(mount_payload)

    _, compiled_app = apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=profile,
        baseline_conflicts=baseline_conflicts,
    )
    compiled_mount = compiled_app.catalog.find_by_id(final_mount_id) if compiled_app else None
    return {
        "ok": True,
        "action": "mount_add",
        "mount_id": final_mount_id,
        "file": str(session.target_path),
        "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
    }


def remove_mount(
    *,
    explicit_config_path: Optional[str],
    profile: Optional[str],
    mount_id: str,
) -> Dict[str, Any]:
    config_path = Path(explicit_config_path).resolve() if explicit_config_path else None
    session = prepare_edit_session(config_path)
    app = CTSApp(
        session.loaded,
        active_profile=profile,
        explicit_config_path=explicit_config_path,
        requested_profile=profile,
    )
    mount = app.catalog.find_by_id(mount_id)
    if mount is None:
        raise RegistryError(f"mount not found: {mount_id}", code="mount_not_found")

    def mutator(payload: Dict[str, Any]) -> None:
        mounts = payload.get("mounts", [])
        if not isinstance(mounts, list):
            return
        remaining = [item for item in mounts if not (isinstance(item, dict) and item.get("id") == mount_id)]
        if remaining:
            payload["mounts"] = remaining
        else:
            payload.pop("mounts", None)

    apply_update(session, mutator, compile_runtime=False, profile=profile)
    return {
        "ok": True,
        "action": "mount_remove",
        "mount_id": mount_id,
        "file": str(session.target_path),
        "source": mount.source_name,
        "operation_id": mount.operation.id,
    }


def add_alias(
    *,
    explicit_config_path: Optional[str],
    profile: Optional[str],
    alias_from: str,
    alias_to: str,
) -> Dict[str, Any]:
    config_path = Path(explicit_config_path).resolve() if explicit_config_path else None
    session = prepare_edit_session(config_path)
    app = CTSApp(
        session.loaded,
        active_profile=profile,
        explicit_config_path=explicit_config_path,
        requested_profile=profile,
    )
    from_tokens = [part for part in alias_from.strip().split() if part]
    to_tokens = [part for part in alias_to.strip().split() if part]
    if not from_tokens or not to_tokens:
        raise RegistryError("alias path cannot be empty", code="alias_path_required")
    target_mount = app.catalog.find_by_path(to_tokens)
    if target_mount is None:
        raise RegistryError(f"alias target path not found: {' '.join(to_tokens)}", code="alias_target_not_found")
    if app.catalog.find_by_path(from_tokens) is not None:
        raise RegistryError(f"alias path already exists: {' '.join(from_tokens)}", code="alias_conflict")
    baseline_conflicts = conflict_signatures(app.catalog.conflicts)

    def mutator(payload: Dict[str, Any]) -> None:
        aliases = ensure_list(payload, "aliases")
        aliases.append({"from": from_tokens, "to": to_tokens})

    apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=profile,
        baseline_conflicts=baseline_conflicts,
    )
    return {
        "ok": True,
        "action": "alias_add",
        "file": str(session.target_path),
        "alias": {"from": from_tokens, "to": to_tokens},
        "mount_id": target_mount.mount_id,
    }


def remove_alias(
    *,
    explicit_config_path: Optional[str],
    profile: Optional[str],
    alias_from: str,
) -> Dict[str, Any]:
    config_path = Path(explicit_config_path).resolve() if explicit_config_path else None
    session = prepare_edit_session(config_path)
    from_tokens = [part for part in alias_from.strip().split() if part]
    removed: Optional[Dict[str, Any]] = None

    def mutator(payload: Dict[str, Any]) -> None:
        nonlocal removed
        aliases = ensure_list(payload, "aliases")
        remaining = []
        for item in aliases:
            if removed is None and isinstance(item, dict) and item.get("from") == from_tokens:
                removed = item
                continue
            remaining.append(item)
        if removed is None:
            raise RegistryError(f"alias not found: {' '.join(from_tokens)}", code="alias_not_found")
        payload["aliases"] = remaining

    updated, _ = apply_update(session, mutator, compile_runtime=False, profile=profile)
    return {
        "ok": True,
        "action": "alias_remove",
        "file": str(session.target_path),
        "alias": removed,
        "remaining_count": len(updated.get("aliases", [])),
    }


def list_aliases(app: CTSApp) -> Dict[str, Any]:
    items = []
    for raw in app.config.aliases:
        if isinstance(raw, dict):
            items.append({"from": raw.get("from"), "to": raw.get("to")})
    return {"items": items}


def get_source_detail(app: CTSApp, source_name: str) -> Dict[str, Any]:
    source = app.config.sources.get(source_name)
    if source is None:
        raise KeyError(f"source not found: {source_name}")
    return build_source_details(app, source_name, source)
