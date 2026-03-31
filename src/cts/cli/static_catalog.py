from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class StaticHelpCatalog:
    def __init__(self) -> None:
        self._path_index: Dict[tuple[str, ...], Any] = {}
        self._group_help: Dict[tuple[str, ...], Dict[str, str]] = {}

    def add_mount(self, mount: Any) -> None:
        primary_path = tuple(mount.command_path)
        if primary_path:
            self._path_index.setdefault(primary_path, mount)
        for alias in getattr(mount, "aliases", []) or []:
            alias_path = tuple(alias)
            if alias_path:
                self._path_index.setdefault(alias_path, mount)

    def find_by_path(self, path: tuple[str, ...]) -> Any:
        return self._path_index.get(tuple(path))

    def child_tokens(self, prefix: tuple[str, ...]) -> List[str]:
        tokens = set()
        prefix_tuple = tuple(prefix)
        for path in self._path_index:
            if len(path) <= len(prefix_tuple):
                continue
            if path[: len(prefix_tuple)] == prefix_tuple:
                tokens.add(path[len(prefix_tuple)])
        return sorted(tokens)

    def has_group(self, prefix: tuple[str, ...]) -> bool:
        prefix_tuple = tuple(prefix)
        for path in self._path_index:
            if len(path) > len(prefix_tuple) and path[: len(prefix_tuple)] == prefix_tuple:
                return True
        if prefix_tuple in self._group_help:
            return True
        return False

    def group_summary(self, prefix: tuple[str, ...]) -> str:
        help_payload = self._group_help.get(tuple(prefix)) or {}
        return help_payload.get("summary") or "Dynamic command group for " + " ".join(prefix)

    def group_description(self, prefix: tuple[str, ...]) -> str:
        help_payload = self._group_help.get(tuple(prefix)) or {}
        return help_payload.get("description") or self.group_summary(prefix)

    def add_group_help(self, prefix: tuple[str, ...], *, summary: Optional[str], description: Optional[str]) -> None:
        prefix_tuple = tuple(prefix)
        if not prefix_tuple:
            return
        self._group_help[prefix_tuple] = {
            "summary": summary or " ".join(prefix_tuple),
            "description": description or summary or "Dynamic command group for " + " ".join(prefix_tuple),
        }


@dataclass
class StaticOperationRecord:
    id: str
    source: str
    provider_type: str
    title: str
    stable_name: Optional[str] = None
    description: Optional[str] = None
    kind: str = "action"
    tags: List[str] = field(default_factory=list)
    group: Optional[str] = None
    risk: str = "read"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    examples: List[Dict[str, Any]] = field(default_factory=list)
    supported_surfaces: List[str] = field(default_factory=lambda: ["cli", "invoke"])
    provider_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StaticMountRecord:
    mount_id: str
    source_name: str
    provider_type: str
    operation: StaticOperationRecord
    command_path: List[str] = field(default_factory=list)
    aliases: List[List[str]] = field(default_factory=list)
    stable_name: str = ""
    summary: Optional[str] = None
    description: Optional[str] = None
    source_config: Any = None
    mount_config: Any = None
    generated: bool = False
    generated_from: Optional[str] = None


def build_static_help_catalog(loaded) -> StaticHelpCatalog:
    catalog = StaticHelpCatalog()
    source_operations: Dict[str, Dict[str, Any]] = {}
    group_help_sources: set[str] = set()
    raw_config = loaded.raw or {}
    raw_sources = raw_config.get("sources") or {}
    raw_mounts = raw_config.get("mounts") or []

    def get_operations(source_name: str):
        cached = source_operations.get(source_name)
        if cached is not None:
            return cached
        source = raw_sources.get(source_name)
        if not isinstance(source, dict) or source.get("enabled", True) is False:
            result: Dict[str, Any] = {}
            source_operations[source_name] = result
            return result

        discovery = source.get("discovery") or {}
        manifest = discovery.get("manifest") if isinstance(discovery, dict) else None
        source_type = str(source.get("type") or "")
        source_defined_operations = source.get("operations") or {}
        if source_type not in {"cli", "shell", "http", "mcp"} and not manifest and not source_defined_operations:
            result = {}
            source_operations[source_name] = result
            return result

        operations: Dict[str, Any] = {}
        if manifest:
            manifest_path = Path(str(manifest)).expanduser()
            if not manifest_path.is_absolute():
                origin = source.get("__origin_file__") if isinstance(source, dict) else None
                if origin:
                    manifest_path = Path(str(origin)).parent / manifest_path
                else:
                    manifest_path = loaded.root_paths[-1].parent / manifest_path if loaded.root_paths else Path.cwd() / manifest_path
            if manifest_path.exists():
                for operation in _static_manifest_operations_from_data(source_name, source_type, manifest_path):
                    operations[operation.id] = operation

        if isinstance(source_defined_operations, dict):
            for operation_id, operation in source_defined_operations.items():
                if not isinstance(operation, dict):
                    continue
                operations[str(operation_id)] = _static_operation_from_config(source_name, source_type, str(operation_id), operation)

        source_operations[source_name] = operations
        return operations

    def add_group_help_from_source(source_name: str) -> None:
        if source_name in group_help_sources:
            return
        source = raw_sources.get(source_name)
        if not isinstance(source, dict):
            return
        for item in source.get("imported_cli_groups") or []:
            if not isinstance(item, dict):
                continue
            path = tuple(item.get("path") or [])
            if not path:
                continue
            catalog.add_group_help(
                path,
                summary=item.get("summary"),
                description=item.get("description"),
            )
        group_help_sources.add(source_name)

    for mount in raw_mounts:
        if not isinstance(mount, dict):
            continue
        source_name = str(mount.get("source") or "")
        if not source_name:
            continue
        add_group_help_from_source(source_name)
        source = raw_sources.get(source_name)
        if not isinstance(source, dict) or source.get("enabled", True) is False:
            continue

        operations = get_operations(source_name)
        if mount.get("select"):
            for operation in operations.values():
                if not _static_operation_matches_select(operation, mount.get("select") or {}):
                    continue
                record = _static_build_generated_mount(mount, source, operation)
                catalog.add_mount(record)
            continue

        operation_id = str(mount.get("operation") or mount.get("id") or "")
        if not operation_id:
            continue
        operation = operations.get(operation_id) or _static_synthesize_operation(mount, source, operation_id)
        record = _static_build_mount_record(mount, source, operation, generated=False)
        catalog.add_mount(record)
    return catalog


def _static_build_generated_mount(mount, source_config, operation) -> StaticMountRecord:
    command = mount.get("command") or {}
    command_prefix = list(command.get("under") or command.get("path") or [])
    if not command_prefix:
        command_prefix = _static_tokenize_identifier(str(mount.get("id") or "mount"))
    operation_tokens = _static_tokenize_identifier(operation.id)
    if command_prefix and operation_tokens and command_prefix[-1] == operation_tokens[0]:
        operation_tokens = operation_tokens[1:]
    command_path = command_prefix + operation_tokens

    stable_name = operation.stable_name or f"{mount.get('source')}.{operation.id}".replace("_", ".")
    return StaticMountRecord(
        mount_id=f"{mount.get('id')}.{operation.id}",
        source_name=str(mount.get("source")),
        provider_type=str(source_config.get("type") or "cli"),
        operation=operation,
        command_path=command_path,
        aliases=[],
        stable_name=stable_name,
        summary=operation.title,
        description=operation.description,
        source_config=source_config,
        mount_config=mount,
        generated=True,
        generated_from=str(mount.get("id")),
    )


def _static_build_mount_record(mount, source_config, operation, generated: bool) -> StaticMountRecord:
    command = mount.get("command") or {}
    command_path = list(command.get("path") or [])
    if not command_path:
        command_path = list(command.get("under") or []) + _static_tokenize_identifier(operation.id)
    if not command_path:
        command_path = _static_tokenize_identifier(str(mount.get("id") or "mount"))

    machine = mount.get("machine") or {}
    help_config = mount.get("help") or {}
    stable_name = machine.get("stable_name") or operation.stable_name or f"{mount.get('source')}.{operation.id}".replace("_", ".")
    return StaticMountRecord(
        mount_id=str(mount.get("id")),
        source_name=str(mount.get("source")),
        provider_type=str(source_config.get("type") or "cli"),
        operation=operation,
        command_path=command_path,
        aliases=[list(alias) for alias in (command.get("aliases") or []) if isinstance(alias, list)],
        stable_name=stable_name,
        summary=help_config.get("summary") or operation.title,
        description=help_config.get("description") or operation.description,
        source_config=source_config,
        mount_config=mount,
        generated=generated,
    )


def _static_synthesize_operation(mount, source_config, operation_id: str) -> StaticOperationRecord:
    help_config = mount.get("help") or {}
    machine = mount.get("machine") or {}
    policy = mount.get("policy") or {}
    return StaticOperationRecord(
        id=operation_id,
        source=str(mount.get("source")),
        provider_type=str(source_config.get("type") or "cli"),
        title=help_config.get("summary") or operation_id,
        stable_name=machine.get("stable_name"),
        description=help_config.get("description"),
        kind="action",
        risk=policy.get("risk", "read"),
        input_schema=_static_schema_from_mount_params(mount.get("params") or {}),
        examples=[{"cli": example} for example in (help_config.get("examples") or [])],
        supported_surfaces=list(machine.get("expose_via") or source_config.get("expose_to_surfaces") or ["cli", "invoke"]),
    )


def _static_schema_from_mount_params(params) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in params.items():
        if not isinstance(param, dict):
            continue
        param_type = str(param.get("type") or "string")
        if param_type == "array":
            schema = {"type": "array", "items": {"type": "string"}}
        else:
            schema = {"type": _static_normalize_schema_type(param_type)}
        if param.get("help"):
            schema["description"] = param.get("help")
        if param.get("default") is not None:
            schema["default"] = param.get("default")
        if param.get("enum"):
            schema["enum"] = list(param.get("enum") or [])
        if param.get("required"):
            required.append(name)
        properties[name] = schema
    return {"type": "object", "properties": properties, "required": required}


def _static_normalize_schema_type(param_type: str) -> str:
    mapping = {
        "str": "string",
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "number": "number",
        "float": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "object": "object",
        "array": "array",
    }
    return mapping.get(param_type, "string")


def _static_tokenize_identifier(value: str) -> List[str]:
    parts = [segment for segment in re.split(r"[_./:\-]+", value) if segment]
    return [part.lower() for part in parts] or [value]


def _static_operation_matches_select(operation, select: Dict[str, Any]) -> bool:
    includes = list(select.get("include", []))
    excludes = list(select.get("exclude", []))
    tags = set(select.get("tags", []))

    haystacks = [operation.id, operation.stable_name or ""] + list(operation.tags)
    if includes and not any(any(fnmatch.fnmatch(item, pattern) for item in haystacks) for pattern in includes):
        return False
    if excludes and any(any(fnmatch.fnmatch(item, pattern) for item in haystacks) for pattern in excludes):
        return False
    if tags and not tags.intersection(set(operation.tags)):
        return False
    return True


def _static_manifest_operations_from_data(source_name: str, provider_type: str, manifest_path: Path) -> List[StaticOperationRecord]:
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return []
    operations = []
    for item in raw.get("operations", []):
        if not isinstance(item, dict) or "id" not in item:
            continue
        operation_id = str(item["id"])
        operations.append(
            StaticOperationRecord(
                id=operation_id,
                source=source_name,
                provider_type=provider_type,
                title=item.get("title") or operation_id,
                stable_name=item.get("stable_name"),
                description=item.get("description"),
                kind=item.get("kind", "action"),
                tags=list(item.get("tags", [])),
                group=item.get("group"),
                risk=item.get("risk", "read"),
                input_schema=dict(item.get("input_schema") or {}),
                output_schema=item.get("output_schema"),
                examples=list(item.get("examples", [])),
                supported_surfaces=list(item.get("supported_surfaces", ["cli", "invoke"])),
                provider_config=dict(item),
            )
        )
    return operations


def _static_operation_from_config(
    source_name: str,
    provider_type: str,
    operation_id: str,
    operation: Dict[str, Any],
) -> StaticOperationRecord:
    provider_config = dict(operation.get("provider_config") or {})
    return StaticOperationRecord(
        id=operation_id,
        source=source_name,
        provider_type=provider_type,
        title=operation.get("title") or operation_id,
        stable_name=provider_config.get("stable_name"),
        description=operation.get("description"),
        kind=operation.get("kind", "action"),
        tags=list(operation.get("tags", [])),
        group=operation.get("group"),
        risk=operation.get("risk", "read"),
        input_schema=dict(operation.get("input_schema") or {}),
        output_schema=operation.get("output_schema"),
        examples=list(operation.get("examples", [])),
        supported_surfaces=list(operation.get("supported_surfaces", ["cli", "invoke"])),
        provider_config=provider_config,
    )
