from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from cts.cli.import_planning import apply_cli_import_plan, apply_cli_import_tree_plan
from cts.config.editor import ConfigEditError, conflict_signatures, ensure_list, ensure_mapping
from cts.importers import merge_operation_into_manifest, write_manifest_operations
from cts.imports.models import ImportPlan, ImportPostAction, ImportRequest
from cts.operation_select import normalize_operation_select, operation_matches_select
from cts.providers.mcp_cli import build_mcp_group_help_from_discovery


def provider_supports_import(provider: Any) -> bool:
    return callable(getattr(provider, "describe_import", None)) and callable(getattr(provider, "plan_import", None))


def describe_provider_import(provider: Any, app: Any) -> Any:
    return provider.describe_import(app)


def build_provider_import_plan(provider: Any, request: ImportRequest, app: Any) -> ImportPlan:
    return provider.plan_import(request, app)


def execute_import_plan(
    plan: ImportPlan,
    *,
    session: Any,
    app: Any,
    state: Any,
    apply_update: Any,
    prepare_edit_session: Any,
    progress: Any = None,
) -> Dict[str, Any]:
    strategy = str(plan.runtime_data.get("apply_strategy") or "").strip()
    if strategy in {"cli_single", "cli_tree"}:
        return _execute_cli_legacy_plan(
            plan,
            strategy=strategy,
            session=session,
            app=app,
            state=state,
            apply_update=apply_update,
            prepare_edit_session=prepare_edit_session,
            progress=progress,
        )
    return _execute_generic_plan(
        plan,
        session=session,
        app=app,
        state=state,
        apply_update=apply_update,
        prepare_edit_session=prepare_edit_session,
        progress=progress,
    )


def _execute_cli_legacy_plan(
    plan: ImportPlan,
    *,
    strategy: str,
    session: Any,
    app: Any,
    state: Any,
    apply_update: Any,
    prepare_edit_session: Any,
    progress: Any = None,
) -> Dict[str, Any]:
    legacy_plan = dict(plan.runtime_data.get("legacy_plan") or {})
    baseline_conflicts = conflict_signatures(app.catalog.conflicts)
    if strategy == "cli_tree":
        manifest_write = dict(legacy_plan["manifest_write"])
        if progress is not None:
            progress.advance("Writing manifest")
        write_manifest_operations(
            Path(manifest_write["resolved_path"]),
            list(manifest_write["operations"]),
            executable=manifest_write.get("executable"),
        )

        def mutator(payload: Dict[str, Any]) -> None:
            apply_cli_import_tree_plan(
                payload,
                legacy_plan,
                ensure_mapping=ensure_mapping,
                ensure_list=ensure_list,
                config_edit_error=ConfigEditError,
            )

        if progress is not None:
            progress.advance("Compiling config")
        updated, _compiled_app = apply_update(
            session,
            mutator,
            compile_runtime=True,
            profile=state.profile,
            baseline_conflicts=baseline_conflicts,
        )
        return {
            "ok": True,
            "action": "import_cli_tree_apply",
            "file": str(session.target_path),
            "created_file": session.created,
            "warnings": list(session.warnings) + list(plan.warnings),
            **legacy_plan,
            "source_config": updated.get("sources", {}).get(plan.source_name, {}),
            "mount_count": len(legacy_plan.get("mounts") or []),
            "operation_count": len(legacy_plan.get("operations") or []),
        }

    if legacy_plan.get("manifest_write"):
        manifest_write = dict(legacy_plan["manifest_write"])
        if progress is not None:
            progress.advance("Writing manifest")
        merge_operation_into_manifest(
            Path(manifest_write["resolved_path"]),
            dict(manifest_write["operation"]),
            executable=manifest_write.get("executable"),
        )

    def mutator(payload: Dict[str, Any]) -> None:
        apply_cli_import_plan(
            payload,
            legacy_plan,
            ensure_mapping=ensure_mapping,
            ensure_list=ensure_list,
            config_edit_error=ConfigEditError,
        )

    if progress is not None:
        progress.advance("Compiling config")
    updated, compiled_app = apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=state.profile,
        baseline_conflicts=baseline_conflicts,
    )
    compiled_mount = None
    if compiled_app and legacy_plan.get("mount"):
        compiled_mount = compiled_app.catalog.find_by_id(legacy_plan["mount"]["id"])
    return {
        "ok": True,
        "action": "import_cli_apply",
        "file": str(session.target_path),
        "created_file": session.created,
        "warnings": list(session.warnings) + list(plan.warnings),
        **legacy_plan,
        "source_config": updated.get("sources", {}).get(plan.source_name, {}),
        "mount_config": _find_mount_payload(updated.get("mounts", []), legacy_plan["mount"]["id"]) if legacy_plan.get("mount") else None,
        "compiled": compiled_mount.to_summary() if compiled_mount is not None else None,
    }


def _execute_generic_plan(
    plan: ImportPlan,
    *,
    session: Any,
    app: Any,
    state: Any,
    apply_update: Any,
    prepare_edit_session: Any,
    progress: Any = None,
) -> Dict[str, Any]:
    progress_labels = dict(plan.runtime_data.get("progress_labels") or {})
    for file_write in plan.files_to_write:
        if progress is not None:
            progress.advance(progress_labels.get("files_to_write") or "Writing files")
        _write_file(file_write)

    baseline_conflicts = conflict_signatures(app.catalog.conflicts)

    def mutator(payload: Dict[str, Any]) -> None:
        payload.setdefault("sources", {})
        payload["sources"][plan.source_name] = dict(plan.source_patch)
        if plan.mount_patches:
            _upsert_mount_payloads(payload, plan.mount_patches)

    if progress is not None:
        progress.advance(progress_labels.get("compile") or "Compiling config")
    updated, compiled_app = apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=state.profile,
        baseline_conflicts=baseline_conflicts,
    )

    post_results = []
    if compiled_app is not None:
        for action in plan.post_compile_actions:
            if progress is not None:
                progress.advance(progress_labels.get(action.action) or _default_post_action_label(action.action))
            post_results.append(_execute_post_action(action, compiled_app, progress=progress))

    if post_results:
        mount_entries = []
        for item in post_results:
            mount_entries.extend(item.get("mounts", []))
        if mount_entries:
            mount_session = prepare_edit_session(state.config_path, target_file=session.target_path)

            def mount_mutator(payload: Dict[str, Any]) -> None:
                _upsert_mount_payloads(payload, mount_entries)

            updated, compiled_app = apply_update(
                mount_session,
                mount_mutator,
                compile_runtime=True,
                profile=state.profile,
                baseline_conflicts=baseline_conflicts,
            )
        if plan.provider_type == "mcp":
            group_help = _mcp_group_help_from_post_results(plan.source_name, updated.get("sources", {}).get(plan.source_name, {}), post_results)
            source_operations = _mcp_source_operations_from_app(compiled_app, plan.source_name) if compiled_app is not None else {}
            if group_help is not None or source_operations:
                source_session = prepare_edit_session(state.config_path, target_file=session.target_path)

                def source_mutator(payload: Dict[str, Any]) -> None:
                    payload.setdefault("sources", {})
                    source_payload = payload["sources"].get(plan.source_name)
                    if not isinstance(source_payload, dict):
                        return
                    if group_help is not None:
                        source_payload["imported_cli_groups"] = [group_help]
                    if source_operations:
                        source_payload["operations"] = source_operations

                updated, compiled_app = apply_update(
                    source_session,
                    source_mutator,
                    compile_runtime=True,
                    profile=state.profile,
                    baseline_conflicts=baseline_conflicts,
                )

    mounts = []
    for mount in updated.get("mounts", []):
        if isinstance(mount, dict) and mount.get("source") == plan.source_name:
            mounts.append(dict(mount))
    payload = {
        "ok": True,
        "action": plan.preview.get("apply_action") or f"import_{plan.provider_type}_apply",
        "provider_type": plan.provider_type,
        "source_name": plan.source_name,
        "file": str(session.target_path),
        "created_file": session.created,
        "warnings": list(session.warnings) + list(plan.warnings),
        "source_config": updated.get("sources", {}).get(plan.source_name, {}),
        "mounts": mounts,
        "post_actions": post_results,
    }
    payload.update({key: value for key, value in plan.preview.items() if key not in {"action", "apply_action"}})
    if plan.provider_type == "mcp":
        payload.update(_mcp_apply_summary(post_results))
    elif plan.provider_type == "shell":
        payload.setdefault("mount", mounts[0] if mounts else None)
    return payload


def _write_file(file_write: Any) -> None:
    path = Path(file_write.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    merge_strategy = str(file_write.merge_strategy or "replace")
    if file_write.format == "json":
        content = file_write.content
        if merge_strategy == "merge_json" and path.exists():
            with open(path, encoding="utf-8") as handle:
                existing = json.load(handle)
            content = _deep_merge(existing, content)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(content, handle, indent=2)
        return
    text = file_write.content if isinstance(file_write.content, str) else str(file_write.content)
    mode = "a" if merge_strategy == "append_text" else "w"
    with open(path, mode, encoding="utf-8") as handle:
        handle.write(text)


def _execute_post_action(action: ImportPostAction, app: Any, *, progress: Any = None) -> Dict[str, Any]:
    if action.action == "sync_source":
        source_name = str(action.payload.get("source_name") or "")
        if progress is not None:
            progress.update_current(f"Discovering tools (syncing source '{source_name}')")
        result = app.sync(source_name)
        if progress is not None:
            discovered_count = sum(int(item.get("operation_count", 0) or 0) for item in result.get("items", []))
            progress.update_current(f"Discovering tools ({discovered_count} discovered)")
        return {"action": action.action, **result}
    if action.action == "create_mounts_from_source_operations":
        source_name = str(action.payload.get("source_name") or "")
        under = list(action.payload.get("under") or [source_name])
        operation_select = normalize_operation_select(action.payload.get("select"))
        mounts = []
        source_operations = app.source_operations.get(source_name, {})
        total = len(source_operations)
        for index, (operation_id, operation) in enumerate(source_operations.items(), start=1):
            if not operation_matches_select(operation, operation_select):
                continue
            if progress is not None:
                progress.update_current(f"Creating mounts ({index}/{total}: {operation_id})")
            existing_mount = app.catalog.find_by_source_and_operation(source_name, operation_id)
            if existing_mount is not None:
                mount_id = existing_mount.mount_id
                command_path = list(existing_mount.command_path)
            else:
                if operation.provider_type == "mcp":
                    mount_id = _unique_mount_id(app, f"{source_name}-{operation_id}")
                    path_token = str(operation_id)
                else:
                    mount_id = _unique_mount_id(app, f"{source_name}-{operation_id}".replace("_", "-"))
                    path_token = str(operation_id).replace("_", "-")
                command_path = list(under) + [path_token]
            mounts.append(
                {
                    "id": mount_id,
                    "source": source_name,
                    "operation": operation_id,
                    "command": {"path": command_path},
                    "help": {
                        "summary": operation.title,
                        "description": operation.description,
                    },
                }
            )
        return {"action": action.action, "mounts": mounts, "count": len(mounts), "operation_select": operation_select}
    return {"action": action.action, "skipped": True, "payload": dict(action.payload)}


def _find_mount_payload(items: list[Any], mount_id: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and item.get("id") == mount_id:
            return dict(item)
    return None


def _unique_mount_id(app: Any, desired: str) -> str:
    current = desired
    index = 2
    while app.catalog.find_by_id(current) is not None:
        current = f"{desired}-{index}"
        index += 1
    return current


def _upsert_mount_payloads(payload: Dict[str, Any], mounts: list[Dict[str, Any]]) -> None:
    payload.setdefault("mounts", [])
    existing_mounts = payload["mounts"]
    if not isinstance(existing_mounts, list):
        payload["mounts"] = []
        existing_mounts = payload["mounts"]

    index_by_id: Dict[str, int] = {}
    index_by_source_operation: Dict[tuple[str, str], int] = {}
    for index, item in enumerate(existing_mounts):
        if not isinstance(item, dict):
            continue
        mount_id = item.get("id")
        if mount_id:
            index_by_id[str(mount_id)] = index
        source_name = item.get("source")
        operation_id = item.get("operation")
        if source_name and operation_id:
            index_by_source_operation[(str(source_name), str(operation_id))] = index

    for mount in mounts:
        if not isinstance(mount, dict):
            continue
        mount_id = str(mount.get("id") or "")
        source_name = str(mount.get("source") or "")
        operation_id = str(mount.get("operation") or "")

        target_index = None
        if mount_id and mount_id in index_by_id:
            target_index = index_by_id[mount_id]
        elif source_name and operation_id and (source_name, operation_id) in index_by_source_operation:
            target_index = index_by_source_operation[(source_name, operation_id)]

        if target_index is None:
            existing_mounts.append(dict(mount))
            target_index = len(existing_mounts) - 1
        else:
            existing_mounts[target_index] = dict(mount)

        if mount_id:
            index_by_id[mount_id] = target_index
        if source_name and operation_id:
            index_by_source_operation[(source_name, operation_id)] = target_index


def _deep_merge(left: Any, right: Any) -> Any:
    if isinstance(left, dict) and isinstance(right, dict):
        result = dict(left)
        for key, value in right.items():
            if key in result:
                result[key] = _deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    return right


def _default_post_action_label(action: str) -> str:
    mapping = {
        "sync_source": "Syncing source",
        "create_mounts_from_source_operations": "Creating mounts",
    }
    return mapping.get(action, action.replace("_", " ").capitalize())


def _mcp_apply_summary(post_results: list[Dict[str, Any]]) -> Dict[str, Any]:
    tools_count = 0
    mounts_created = 0
    discovery = None
    report_path = None
    capability_snapshot_path = None
    tools_import_error = None
    for item in post_results:
        if item.get("action") == "sync_source":
            report_path = item.get("report_path")
            capability_snapshot_path = item.get("capability_snapshot_path")
            sync_items = item.get("items") or []
            discovery = sync_items[0] if sync_items else None
            if discovery:
                tools_count = int(discovery.get("operation_count") or 0)
                if not discovery.get("ok", True) and discovery.get("error"):
                    tools_import_error = discovery.get("error")
        if item.get("action") == "create_mounts_from_source_operations":
            mounts_created = int(item.get("count") or 0)
    result = {
        "tools_count": tools_count,
        "mounts_created": mounts_created,
        "discovery": discovery,
        "discovery_report_path": report_path,
        "capability_snapshot_path": capability_snapshot_path,
    }
    if tools_import_error:
        result["tools_import_error"] = tools_import_error
    return result


def _mcp_group_help_from_post_results(
    source_name: str,
    source_config: Dict[str, Any],
    post_results: list[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    server_name = str(source_config.get("server") or source_name)
    for item in post_results:
        if item.get("action") != "sync_source":
            continue
        sync_items = item.get("items") or []
        discovery = sync_items[0] if sync_items else None
        return build_mcp_group_help_from_discovery(source_name, {"server": server_name}, discovery)
    return None


def _mcp_source_operations_from_app(app: Any, source_name: str) -> Dict[str, Any]:
    operations: Dict[str, Any] = {}
    for operation_id, operation in (app.source_operations.get(source_name, {}) if app is not None else {}).items():
        operations[operation_id] = {
            "title": operation.title,
            "description": operation.description,
            "kind": operation.kind,
            "risk": operation.risk,
            "tags": list(operation.tags),
            "group": operation.group,
            "input_schema": dict(operation.input_schema or {}),
            "output_schema": operation.output_schema,
            "examples": list(operation.examples),
            "supported_surfaces": list(operation.supported_surfaces),
            "provider_config": dict(operation.provider_config or {}),
        }
    return operations
