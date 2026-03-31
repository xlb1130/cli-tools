from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional


def execute_import_mcp(
    ctx,
    *,
    source_name: str,
    server_config: Optional[str],
    server_name: Optional[str],
    config_file: Optional[Path],
    under_values: tuple[str, ...],
    apply: bool,
    progress,
    get_state: Callable,
    prepare_edit_session: Callable,
    apply_update: Callable,
) -> Dict[str, Any]:
    state = get_state(ctx)
    session = prepare_edit_session(state.config_path, target_file=None)

    if config_file is None:
        config_file = session.target_path.parent / "servers.json"

    if server_config:
        try:
            server_cfg = json.loads(server_config)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in --server-config: {exc}")
    elif server_name:
        server_cfg = None
    else:
        raise ValueError("Either --server-config or --server-name must be provided")

    servers_json_path = Path(config_file)
    servers_data: Dict[str, Any] = {}
    if servers_json_path.exists():
        with open(servers_json_path) as handle:
            servers_data = json.load(handle)

    if server_config:
        actual_server_name = server_name or f"{source_name}-server"
        servers_data["mcpServers"] = servers_data.get("mcpServers", {})
        servers_data["mcpServers"][actual_server_name] = server_cfg
    else:
        actual_server_name = server_name

    plan = {
        "source_name": source_name,
        "server_name": actual_server_name,
        "config_file": str(servers_json_path),
        "servers_data": servers_data,
        "under": list(under_values),
    }
    if not apply:
        return {"ok": True, "action": "import_mcp_preview", **plan}

    if progress is not None:
        progress.advance("Writing server config")
    servers_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(servers_json_path, "w") as handle:
        json.dump(servers_data, handle, indent=2)

    baseline_conflicts = set()

    def mutator(payload: Dict[str, Any]) -> None:
        if "sources" not in payload:
            payload["sources"] = {}
        payload["sources"][source_name] = {
            "type": "mcp",
            "adapter": "mcp-cli",
            "config_file": str(servers_json_path),
            "server": actual_server_name,
            "discovery": {"mode": "live"},
        }

    if progress is not None:
        progress.advance("Compiling source config")
    updated, compiled_app = apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=state.profile,
        baseline_conflicts=baseline_conflicts,
    )

    if compiled_app:
        try:
            if progress is not None:
                progress.advance("Discovering tools")
            sync_result = compiled_app.sync(source_name)
            sync_items = sync_result.get("items", [])
            discovery = sync_items[0] if sync_items else {}
            discovery_ok = bool(discovery.get("ok", False))
            if not discovery_ok:
                discovery = {**discovery, "operation_count": 0}
            operations = compiled_app.source_operations.get(source_name, {}) if discovery_ok else {}

            mounts_to_create = []
            operation_items = list(operations.items())
            total_operations = len(operation_items)
            if progress is not None:
                progress.advance("Creating mounts")
            for idx, (op_id, op) in enumerate(operation_items, start=1):
                if progress is not None:
                    progress.update_current(f"Creating mounts ({idx}/{total_operations}: {op_id})")
                mount_id = f"{source_name}-{op_id}"
                mount_path = list(under_values) + [op_id] if under_values else [source_name, op_id]
                mount_entry = {
                    "id": mount_id,
                    "source": source_name,
                    "operation": op_id,
                    "command": {"path": mount_path},
                }
                help_entry: Dict[str, Any] = {}
                if op.title:
                    help_entry["summary"] = op.title
                if op.description:
                    help_entry["description"] = op.description
                if help_entry:
                    mount_entry["help"] = help_entry
                mounts_to_create.append(mount_entry)

            mount_session = prepare_edit_session(state.config_path, target_file=session.target_path)

            def mount_mutator(payload: Dict[str, Any]) -> None:
                if "mounts" not in payload:
                    payload["mounts"] = []
                payload["mounts"].extend(mounts_to_create)

            apply_update(
                mount_session,
                mount_mutator,
                compile_runtime=True,
                profile=state.profile,
                baseline_conflicts=baseline_conflicts,
            )

            result = {
                "ok": True,
                "action": "import_mcp_apply",
                "file": str(session.target_path),
                "created_file": session.created,
                "servers_file": str(servers_json_path),
                "warnings": list(session.warnings),
                "source_config": updated.get("sources", {}).get(source_name, {}),
                "tools_count": len(operations),
                "mounts_created": len(mounts_to_create),
                "discovery": discovery,
                "discovery_report_path": sync_result.get("report_path"),
                "capability_snapshot_path": sync_result.get("capability_snapshot_path"),
            }
            if discovery and not discovery.get("ok", True) and discovery.get("error"):
                result["tools_import_error"] = discovery.get("error")
            return result
        except Exception as exc:
            return {
                "ok": True,
                "action": "import_mcp_apply",
                "file": str(session.target_path),
                "created_file": session.created,
                "servers_file": str(servers_json_path),
                "warnings": list(session.warnings),
                "source_config": updated.get("sources", {}).get(source_name, {}),
                "tools_import_error": str(exc),
            }

    return {
        "ok": True,
        "action": "import_mcp_apply",
        "file": str(session.target_path),
        "created_file": session.created,
        "servers_file": str(servers_json_path),
        "warnings": list(session.warnings),
        "source_config": updated.get("sources", {}).get(source_name, {}),
    }


def execute_import_shell(
    ctx,
    *,
    source_name: str,
    exec_command: Optional[str],
    script_file: Optional[Path],
    shell_bin: str,
    under_values: tuple[str, ...],
    title: Optional[str],
    description: Optional[str],
    risk: str,
    output_mode: str,
    apply: bool,
    get_state: Callable,
    prepare_edit_session: Callable,
    app_factory: Callable,
    conflict_signatures: Callable,
    ensure_mapping: Callable,
    ensure_list: Callable,
    apply_update: Callable,
    strip_internal_metadata: Callable,
    find_mount_payload: Callable,
    build_mount_details: Callable,
    registry_error: Callable,
    split_command_segments: Callable,
) -> Dict[str, Any]:
    state = get_state(ctx)
    session = prepare_edit_session(state.config_path, target_file=None)
    app = app_factory(session.loaded, state.profile, state.config_path)

    if source_name in app.config.sources:
        raise registry_error(f"source already exists: {source_name}", code="source_exists")

    mount_id = source_name.replace(".", "-").replace("_", "-")
    if app.catalog.find_by_id(mount_id) is not None:
        raise registry_error(f"mount already exists: {mount_id}", code="mount_exists")

    operation_id = "run"
    command_path = list(split_command_segments(under_values)) + [source_name]
    script_path = script_file.resolve() if script_file else None
    source_label = exec_command if exec_command else str(script_path)
    argv_template = [shell_bin, "-c", exec_command] if exec_command else [shell_bin, str(script_path)]
    source_payload = {
        "type": "shell",
        "enabled": True,
        "executable": shell_bin,
        "operations": {
            operation_id: {
                "title": title or source_name,
                "description": description or f"Execute shell command: {source_label}",
                "risk": risk,
                "input_schema": {"type": "object", "properties": {}},
                "provider_config": {
                    "argv_template": argv_template,
                    "output_mode": output_mode,
                },
            }
        },
    }
    mount_payload = {
        "id": mount_id,
        "source": source_name,
        "operation": operation_id,
        "command": {"path": command_path},
        "machine": {"stable_name": f"{source_name}.run"},
        "help": {
            "summary": title or source_name,
            "description": description or f"Execute shell command: {source_label}",
            "notes": [f"Shell executable: {shell_bin}"],
        },
    }
    plan = {
        "source": {"name": source_name, "type": "shell"},
        "operation_id": operation_id,
        "mount_id": mount_id,
        "exec": exec_command,
        "script_file": str(script_path) if script_path else None,
        "shell_bin": shell_bin,
        "command_path": command_path,
        "source_config": source_payload,
        "mount_config": mount_payload,
    }
    if not apply:
        return {"ok": True, "action": "import_shell_preview", **plan}

    baseline_conflicts = conflict_signatures(app.catalog.conflicts)

    def mutator(payload: Dict[str, Any]) -> None:
        sources = ensure_mapping(payload, "sources")
        sources[source_name] = source_payload
        mounts = ensure_list(payload, "mounts")
        mounts.append(mount_payload)

    updated, compiled_app = apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=state.profile,
        baseline_conflicts=baseline_conflicts,
    )
    compiled_mount = compiled_app.catalog.find_by_id(mount_id) if compiled_app else None
    return {
        "ok": True,
        "action": "import_shell_apply",
        "file": str(session.target_path),
        "created_file": session.created,
        "warnings": list(session.warnings),
        "source": {"name": source_name, "type": "shell"},
        "operation_id": operation_id,
        "mount_id": mount_id,
        "exec": exec_command,
        "script_file": str(script_path) if script_path else None,
        "shell_bin": shell_bin,
        "command_path": command_path,
        "source_config": strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
        "mount_config": find_mount_payload(updated.get("mounts", []), mount_id),
        "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
    }
