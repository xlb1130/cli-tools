from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from cts.cli.lazy import (
    CTSApp,
    import_cli_completion,
    import_cli_help,
    import_cli_manpage,
    import_cli_schema,
    inspect_cli_help,
    tokenize_identifier,
)
from cts.execution.errors import RegistryError
from cts.operation_select import operation_matches_select


def prepare_cli_import_tree_plan(
    app: CTSApp,
    *,
    source_name: str,
    command_argv: List[str],
    executable: Optional[str],
    risk: str,
    output_mode: str,
    help_flag: str,
    create_mount: bool,
    under_values: tuple[str, ...],
    prefix: Optional[str],
    save_manifest_path: Optional[Path],
    operation_select: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    existing_source = app.config.sources.get(source_name)
    if existing_source and existing_source.type not in {"cli", "shell"}:
        raise RegistryError(
            f"source '{source_name}' is not a cli/shell source",
            code="source_type_not_supported",
            suggestions=["改用新的 source 名称，或继续使用原来的 provider 专用导入命令。"],
        )

    final_command = list(command_argv)
    source_executable = executable or (existing_source.executable if existing_source else None)
    if not final_command:
        if source_executable:
            final_command = [source_executable]
        else:
            raise RegistryError(
                "command argv required",
                code="command_argv_required",
                suggestions=["传入要导入的命令，例如 `cts import cli aac aac --all --apply`。"],
            )
    if source_executable is None and final_command:
        source_executable = final_command[0]

    if progress_callback is not None:
        progress_callback("inspect_root", {"command_argv": list(final_command)})
    tree = discover_cli_help_tree(final_command, help_flag=help_flag, progress_callback=progress_callback)
    if not tree["leaves"]:
        raise RegistryError(
            f"no executable leaf commands discovered for source '{source_name}'",
            code="import_all_no_leaf_commands",
            suggestions=["确认该 CLI 的每层 help 都会列出子命令，或改为单条 `cts import cli` 导入。"],
        )

    imported_operations = []
    source_operations: Dict[str, Dict[str, Any]] = {}
    for index, leaf in enumerate(tree["leaves"], start=1):
        operation_id = derive_operation_id_from_tokens(leaf["relative_tokens"])
        if progress_callback is not None:
            progress_callback(
                "import_leaf_operations",
                {"current": index, "total": len(tree["leaves"]), "operation_id": operation_id},
            )
        import_result = import_cli_help(
            operation_id=operation_id,
            command_argv=list(leaf["command_argv"]),
            help_flag=help_flag,
            risk=risk,
            output_mode=output_mode,
            title=None,
        )
        imported_operation = dict(import_result.operation)
        if not operation_matches_select(imported_operation, operation_select):
            continue
        imported_operations.append(imported_operation)
        source_operations[operation_id] = build_inline_source_operation(imported_operation)

    manifest_path = save_manifest_path or Path(f"{source_name}-manifest.yaml")
    manifest_write = {
        "path": str(manifest_path),
        "resolved_path": str(app.resolve_path(str(manifest_path), owner=existing_source)),
        "operations": imported_operations,
        "executable": source_executable,
    }

    mounts = []
    warnings = list(tree["warnings"])
    group_help: List[Dict[str, Any]] = []
    if create_mount:
        path_prefix = list(split_command_segments(list(under_values))) or [source_name]
        group_help.append(
            {
                "path": list(path_prefix),
                "summary": tree.get("root_summary") or source_name,
                "description": tree.get("root_description") or tree.get("root_summary") or source_name,
            }
        )
        for item in tree["groups"]:
            group_help.append(
                {
                    "path": list(path_prefix) + list(item["path"]),
                    "summary": item.get("summary"),
                    "description": item.get("description"),
                }
            )
    if create_mount:
        mounts, mount_warnings = build_cli_import_tree_mounts(
            app,
            source_name=source_name,
            operations=imported_operations,
            under_values=under_values,
            prefix=prefix,
            root_command=final_command,
            progress_callback=progress_callback,
        )
        warnings.extend(mount_warnings)

    source_preview = {
        "name": source_name,
        "existing": existing_source is not None,
        "type": existing_source.type if existing_source else "cli",
        "executable": source_executable,
        "stores_operation_inline": False,
        "manifest_path": manifest_write["path"],
        "operation_count": len(imported_operations),
        "operations_preview": sorted(source_operations.keys())[:50],
        "truncated": len(imported_operations) > 50,
    }
    return {
        "source": source_preview,
        "command_argv": final_command,
        "strategy": "help_tree",
        "operations": imported_operations,
        "group_help": group_help,
        "mounts": mounts,
        "tree": {
            "group_count": len(tree["groups"]),
            "leaf_count": len(tree["leaves"]),
            "max_depth": tree["max_depth"],
            "groups": [item["path"] for item in tree["groups"][:50]],
            "leaves": [item["relative_tokens"] for item in tree["leaves"][:50]],
            "truncated": len(tree["groups"]) > 50 or len(tree["leaves"]) > 50,
        },
        "manifest_write": manifest_write,
        "warnings": warnings,
        "operation_select": dict(operation_select or {}),
    }


def discover_cli_help_tree(
    command_argv: List[str],
    *,
    help_flag: str,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    queue: List[List[str]] = [list(command_argv)]
    seen: set[tuple[str, ...]] = set()
    scheduled: set[tuple[str, ...]] = {tuple(command_argv)}
    groups: List[List[str]] = []
    leaves: List[Dict[str, Any]] = []
    warnings: List[str] = []
    max_depth = 0
    root_summary: Optional[str] = None
    root_description: Optional[str] = None

    while queue:
        if progress_callback is not None:
            progress_callback(
                "discover_subcommands",
                {"visited": len(seen), "queued": len(queue), "leaves": len(leaves)},
            )
        current = queue.pop(0)
        current_key = tuple(current)
        if current_key in seen:
            continue
        seen.add(current_key)
        relative_tokens = relative_cli_tokens_from_base(current, command_argv)
        max_depth = max(max_depth, len(relative_tokens))
        node = inspect_cli_help(command_argv=current, help_flag=help_flag)
        if not relative_tokens:
            root_summary = node.summary or root_summary
            root_description = node.description or node.summary or root_description
        if node.subcommands:
            if relative_tokens:
                groups.append(
                    {
                        "path": relative_tokens,
                        "summary": node.summary or (node.description.splitlines()[0] if node.description else " ".join(relative_tokens)),
                        "description": node.description or node.summary or " ".join(relative_tokens),
                    }
                )
            for subcommand in node.subcommands:
                candidate = current + [subcommand]
                candidate_key = tuple(candidate)
                if candidate_key not in scheduled:
                    queue.append(candidate)
                    scheduled.add(candidate_key)
            continue
        if relative_tokens:
            leaves.append({"command_argv": list(current), "relative_tokens": relative_tokens})

    if len(seen) > 500:
        warnings.append("discovered more than 500 help nodes; preview output was truncated")
    return {
        "groups": groups,
        "leaves": leaves,
        "warnings": warnings,
        "max_depth": max_depth,
        "root_summary": root_summary,
        "root_description": root_description,
    }


def build_cli_import_tree_mounts(
    app: CTSApp,
    *,
    source_name: str,
    operations: List[Dict[str, Any]],
    under_values: tuple[str, ...],
    prefix: Optional[str],
    root_command: List[str],
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> tuple[List[Dict[str, Any]], List[str]]:
    reserved_mount_ids = {mount.mount_id for mount in app.catalog.mounts}
    reserved_paths = {tuple(mount.command_path) for mount in app.catalog.mounts}
    mounts: List[Dict[str, Any]] = []
    warnings: List[str] = []
    mount_prefix = prefix or source_name.replace("_", "-").replace(".", "-")
    under_tokens = split_command_segments(list(under_values))

    total_operations = len(operations)
    for index, operation in enumerate(operations, start=1):
        operation_id = str(operation["id"])
        if progress_callback is not None:
            progress_callback("prepare_mounts", {"current": index, "total": total_operations, "operation_id": operation_id})
        existing_mount = app.catalog.find_by_source_and_operation(source_name, operation_id)
        if existing_mount is not None:
            warnings.append(f"mount already exists for {source_name}.{operation_id}; reusing {existing_mount.mount_id}")
            continue

        relative_tokens = relative_cli_tokens_from_base(list(operation.get("command_argv") or root_command), root_command)
        base_mount_id = f"{mount_prefix}-{operation_id.replace('.', '-').replace('_', '-')}"
        base_command_path = list(under_tokens) + relative_tokens if under_tokens else [source_name] + relative_tokens
        final_mount_id, final_command_path, warning = make_mount_identity_unique_respecting(
            app,
            base_mount_id,
            base_command_path,
            reserved_mount_ids=reserved_mount_ids,
            reserved_paths=reserved_paths,
        )
        reserved_mount_ids.add(final_mount_id)
        reserved_paths.add(tuple(final_command_path))

        mount_entry: Dict[str, Any] = {
            "id": final_mount_id,
            "source": source_name,
            "operation": operation_id,
            "command": {"path": final_command_path},
        }
        help_entry: Dict[str, Any] = {}
        if operation.get("title"):
            help_entry["summary"] = operation["title"]
        if operation.get("description"):
            help_entry["description"] = operation["description"]
        if help_entry:
            mount_entry["help"] = help_entry
        if operation.get("risk") and operation.get("risk") != "read":
            mount_entry["policy"] = {"risk": operation["risk"]}
        mounts.append(mount_entry)
        if warning:
            warnings.append(f"{operation_id}: {warning}")
    return mounts, warnings


def prepare_cli_import_plan(
    app: CTSApp,
    *,
    source_name: str,
    command_argv: List[str],
    operation_id: Optional[str],
    import_strategy: str,
    executable: Optional[str],
    title: Optional[str],
    risk: str,
    output_mode: str,
    help_flag: str,
    completion_command: Optional[str],
    completion_file: Optional[Path],
    completion_format: str,
    man_command: Optional[str],
    man_file: Optional[Path],
    schema_command: Optional[str],
    schema_file: Optional[Path],
    schema_format: str,
    create_mount: bool,
    mount_id: Optional[str],
    command_path_value: Optional[str],
    under_values: tuple[str, ...],
    prefix: Optional[str],
    save_manifest_path: Optional[Path],
) -> Dict[str, Any]:
    existing_source = app.config.sources.get(source_name)
    if existing_source and existing_source.type not in {"cli", "shell"}:
        raise RegistryError(
            f"source '{source_name}' is not a cli/shell source",
            code="source_type_not_supported",
            suggestions=["改用新的 source 名称，或继续使用原来的 provider 专用导入命令。"],
        )

    final_command = list(command_argv)
    source_executable = executable or (existing_source.executable if existing_source else None)
    if not final_command:
        if source_executable:
            final_command = [source_executable]
        else:
            raise RegistryError(
                "command argv required",
                code="command_argv_required",
                suggestions=["传入要导入的命令，例如 `cts import cli gh gh issue list --from help`。"],
            )
    if source_executable is None and final_command:
        source_executable = final_command[0]

    final_operation_id = operation_id or derive_operation_id_from_command(final_command)
    import_result = run_cli_import_strategy(
        operation_id=final_operation_id,
        command_argv=final_command,
        import_strategy=import_strategy,
        title=title,
        risk=risk,
        output_mode=output_mode,
        help_flag=help_flag,
        completion_command=completion_command,
        completion_file=completion_file,
        completion_format=completion_format,
        man_command=man_command,
        man_file=man_file,
        schema_command=schema_command,
        schema_file=schema_file,
        schema_format=schema_format,
    )

    imported_operation = dict(import_result.operation)
    source_operation = build_inline_source_operation(imported_operation)
    manifest_write = None
    if save_manifest_path is not None:
        manifest_write = {
            "path": str(save_manifest_path),
            "resolved_path": str(app.resolve_path(str(save_manifest_path), owner=existing_source)),
            "operation": imported_operation,
            "executable": source_executable,
        }

    mount_plan = None
    warnings: List[str] = []
    if create_mount:
        mount_plan, mount_warning = build_cli_import_mount_plan(
            app,
            source_name=source_name,
            operation_id=final_operation_id,
            imported_operation=imported_operation,
            mount_id=mount_id,
            command_path_value=command_path_value,
            under_values=under_values,
            prefix=prefix,
        )
        if mount_warning:
            warnings.append(mount_warning)

    source_preview = {
        "name": source_name,
        "existing": existing_source is not None,
        "type": existing_source.type if existing_source else "cli",
        "executable": source_executable,
        "stores_operation_inline": manifest_write is None,
        "manifest_path": manifest_write["path"] if manifest_write else (existing_source.discovery.manifest if existing_source else None),
        "operation_id": final_operation_id,
        "operation": source_operation,
    }
    return {
        "source": source_preview,
        "operation_id": final_operation_id,
        "command_argv": final_command,
        "strategy": import_strategy,
        "imported_operation": imported_operation,
        "mount": mount_plan,
        "manifest_write": manifest_write,
        "warnings": warnings,
    }


def run_cli_import_strategy(
    *,
    operation_id: str,
    command_argv: List[str],
    import_strategy: str,
    title: Optional[str],
    risk: str,
    output_mode: str,
    help_flag: str,
    completion_command: Optional[str],
    completion_file: Optional[Path],
    completion_format: str,
    man_command: Optional[str],
    man_file: Optional[Path],
    schema_command: Optional[str],
    schema_file: Optional[Path],
    schema_format: str,
):
    if import_strategy == "help":
        return import_cli_help(
            operation_id=operation_id,
            command_argv=command_argv,
            help_flag=help_flag,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
    if import_strategy == "completion":
        if not completion_command and completion_file is None:
            raise RegistryError("completion source required", code="completion_source_required", suggestions=["传入 --completion-command 或 --completion-file。"])
        return import_cli_completion(
            operation_id=operation_id,
            command_argv=command_argv,
            completion_command=shlex.split(completion_command) if completion_command else None,
            completion_file=completion_file,
            completion_format=completion_format,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
    if import_strategy == "manpage":
        if not man_command and man_file is None:
            raise RegistryError("man page source required", code="manpage_source_required", suggestions=["传入 --man-command 或 --man-file。"])
        return import_cli_manpage(
            operation_id=operation_id,
            command_argv=command_argv,
            man_command=shlex.split(man_command) if man_command else None,
            man_file=man_file,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
    if import_strategy == "schema":
        if not schema_command and schema_file is None:
            raise RegistryError("schema source required", code="schema_source_required", suggestions=["传入 --schema-command 或 --schema-file。"])
        return import_cli_schema(
            operation_id=operation_id,
            command_argv=command_argv,
            schema_command=shlex.split(schema_command) if schema_command else None,
            schema_file=schema_file,
            schema_format=schema_format,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
    raise RegistryError(f"unsupported import strategy: {import_strategy}", code="import_strategy_unsupported")


def build_inline_source_operation(imported_operation: Dict[str, Any]) -> Dict[str, Any]:
    provider_config: Dict[str, Any] = {}
    for key in (
        "command_argv",
        "option_bindings",
        "option_order",
        "output",
        "output_mode",
        "imported_from",
        "schema_payload",
        "help_command",
        "completion_command",
        "man_command",
    ):
        if key in imported_operation:
            provider_config[key] = imported_operation[key]

    return {
        "title": imported_operation.get("title"),
        "description": imported_operation.get("description"),
        "kind": imported_operation.get("kind", "action"),
        "risk": imported_operation.get("risk", "read"),
        "input_schema": imported_operation.get("input_schema") or {},
        "output_schema": imported_operation.get("output_schema"),
        "examples": imported_operation.get("examples") or [],
        "supported_surfaces": imported_operation.get("supported_surfaces") or ["cli", "invoke"],
        "provider_config": provider_config,
    }


def build_cli_import_mount_plan(
    app: CTSApp,
    *,
    source_name: str,
    operation_id: str,
    imported_operation: Dict[str, Any],
    mount_id: Optional[str],
    command_path_value: Optional[str],
    under_values: tuple[str, ...],
    prefix: Optional[str],
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    existing_mount = app.catalog.find_by_source_and_operation(source_name, operation_id)
    if existing_mount is not None:
        return (
            {
                "id": existing_mount.mount_id,
                "existing": True,
                "command_path": list(existing_mount.command_path),
                "source": source_name,
                "operation": operation_id,
            },
            f"mount already exists for {source_name}.{operation_id}; reusing {existing_mount.mount_id}",
        )

    mount_prefix = prefix or source_name.replace("_", "-").replace(".", "-")
    base_mount_id = mount_id or f"{mount_prefix}-{operation_id.replace('.', '-').replace('_', '-')}"
    if command_path_value:
        base_command_path = split_command_segments([command_path_value])
    else:
        under_tokens = split_command_segments(list(under_values))
        operation_tokens = tokenize_identifier(operation_id)
        base_command_path = under_tokens + operation_tokens if under_tokens else tokenize_identifier(source_name) + operation_tokens

    final_mount_id, final_command_path, warning = make_mount_identity_unique(app, base_mount_id, base_command_path)
    mount_entry: Dict[str, Any] = {
        "id": final_mount_id,
        "source": source_name,
        "operation": operation_id,
        "command": {"path": final_command_path},
    }
    help_entry: Dict[str, Any] = {}
    if imported_operation.get("title"):
        help_entry["summary"] = imported_operation["title"]
    if imported_operation.get("description"):
        help_entry["description"] = imported_operation["description"]
    if help_entry:
        mount_entry["help"] = help_entry
    risk = imported_operation.get("risk")
    if risk and risk != "read":
        mount_entry["policy"] = {"risk": risk}
    return mount_entry, warning


def make_mount_identity_unique(app: CTSApp, mount_id: str, command_path: List[str]) -> tuple[str, List[str], Optional[str]]:
    return make_mount_identity_unique_respecting(app, mount_id, command_path, reserved_mount_ids=set(), reserved_paths=set())


def make_mount_identity_unique_respecting(
    app: CTSApp,
    mount_id: str,
    command_path: List[str],
    *,
    reserved_mount_ids: set[str],
    reserved_paths: set[tuple[str, ...]],
) -> tuple[str, List[str], Optional[str]]:
    candidate_mount_id = mount_id
    candidate_path = list(command_path)
    suffix = 2
    warning = None
    while (
        app.catalog.find_by_id(candidate_mount_id) is not None
        or app.catalog.find_by_path(candidate_path) is not None
        or candidate_mount_id in reserved_mount_ids
        or tuple(candidate_path) in reserved_paths
    ):
        warning = "mount id or command path already exists; generated a numeric suffix automatically"
        candidate_mount_id = f"{mount_id}-{suffix}"
        candidate_path = list(command_path)
        if candidate_path:
            candidate_path[-1] = f"{candidate_path[-1]}-{suffix}"
        suffix += 1
    return candidate_mount_id, candidate_path, warning


def derive_operation_id_from_command(command_argv: List[str]) -> str:
    relative_tokens = relative_cli_tokens(command_argv)
    if not relative_tokens:
        return "command"
    return derive_operation_id_from_tokens(relative_tokens)


def derive_operation_id_from_tokens(tokens: List[str]) -> str:
    if not tokens:
        return "command"
    return "_".join(token.replace("-", "_").replace(".", "_") for token in tokens)


def relative_cli_tokens(command_argv: List[str]) -> List[str]:
    candidates = [token for token in command_argv if token and not token.startswith("-")]
    if len(candidates) <= 1:
        return []
    if len(candidates) >= 3 and looks_like_script_path(candidates[1]):
        return list(candidates[2:])
    return list(candidates[1:])


def looks_like_script_path(token: str) -> bool:
    return Path(token).suffix.lower() in {".py", ".sh", ".js", ".mjs", ".cjs", ".ts"}


def relative_cli_tokens_from_base(command_argv: List[str], base_command_argv: List[str]) -> List[str]:
    if len(command_argv) >= len(base_command_argv) and command_argv[: len(base_command_argv)] == base_command_argv:
        return [token for token in command_argv[len(base_command_argv) :] if token and not token.startswith("-")]
    return relative_cli_tokens(command_argv)


def apply_cli_import_plan(
    payload: Dict[str, Any],
    plan: Dict[str, Any],
    *,
    ensure_mapping: Callable,
    ensure_list: Callable,
    config_edit_error: Callable,
) -> None:
    source_plan = dict(plan["source"])
    source_name = str(source_plan["name"])
    operation_id = str(source_plan["operation_id"])
    sources = ensure_mapping(payload, "sources")
    source_payload = sources.get(source_name)
    if source_payload is None:
        source_payload = {"type": source_plan["type"], "enabled": True}
        sources[source_name] = source_payload
    if not isinstance(source_payload, dict):
        raise config_edit_error(f"source payload must be a mapping: {source_name}")

    source_payload.setdefault("type", source_plan["type"])
    if source_plan.get("executable"):
        source_payload["executable"] = source_plan["executable"]

    manifest_write = plan.get("manifest_write")
    if manifest_write:
        discovery = ensure_mapping(source_payload, "discovery")
        discovery["manifest"] = manifest_write["path"]
        operations = source_payload.get("operations")
        if isinstance(operations, dict) and operation_id in operations:
            del operations[operation_id]
            if not operations:
                source_payload.pop("operations", None)
    else:
        operations = ensure_mapping(source_payload, "operations")
        operations[operation_id] = dict(source_plan["operation"])

    mount_plan = plan.get("mount")
    if mount_plan and not mount_plan.get("existing"):
        mounts = ensure_list(payload, "mounts")
        mounts.append(dict(mount_plan))


def apply_cli_import_tree_plan(
    payload: Dict[str, Any],
    plan: Dict[str, Any],
    *,
    ensure_mapping: Callable,
    ensure_list: Callable,
    config_edit_error: Callable,
) -> None:
    source_plan = dict(plan["source"])
    source_name = str(source_plan["name"])
    sources = ensure_mapping(payload, "sources")
    source_payload = sources.get(source_name)
    if source_payload is None:
        source_payload = {"type": source_plan["type"], "enabled": True}
        sources[source_name] = source_payload
    if not isinstance(source_payload, dict):
        raise config_edit_error(f"source payload must be a mapping: {source_name}")

    source_payload.setdefault("type", source_plan["type"])
    if source_plan.get("executable"):
        source_payload["executable"] = source_plan["executable"]

    manifest_write = dict(plan["manifest_write"])
    discovery = ensure_mapping(source_payload, "discovery")
    discovery["manifest"] = manifest_write["path"]
    if plan.get("group_help"):
        source_payload["imported_cli_groups"] = list(plan["group_help"])

    mounts = ensure_list(payload, "mounts")
    existing_mount_ids = {item.get("id") for item in mounts if isinstance(item, dict) and item.get("id")}
    for mount in plan.get("mounts") or []:
        if mount.get("id") in existing_mount_ids:
            continue
        mounts.append(dict(mount))
        existing_mount_ids.add(mount.get("id"))


def split_command_segments(values: tuple[str, ...] | list[str]) -> List[str]:
    tokens: List[str] = []
    for value in values:
        tokens.extend(shlex.split(value))
    return tokens
