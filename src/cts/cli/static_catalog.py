from __future__ import annotations

import json
import re
from dataclasses import asdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from cts.models import OperationDescriptor
from cts.operation_select import operation_matches_select


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


def serialize_static_help_catalog(catalog: StaticHelpCatalog) -> Dict[str, Any]:
    mounts: List[Dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for mount in catalog._path_index.values():
        key = (str(getattr(mount, "mount_id", "")), tuple(getattr(mount, "command_path", []) or []))
        if key in seen:
            continue
        seen.add(key)
        mounts.append(asdict(mount))

    group_help = [
        {
            "path": list(path),
            "summary": payload.get("summary"),
            "description": payload.get("description"),
        }
        for path, payload in sorted(catalog._group_help.items())
    ]
    return {"mounts": mounts, "group_help": group_help}


def deserialize_static_help_catalog(payload: Dict[str, Any]) -> StaticHelpCatalog:
    catalog = StaticHelpCatalog()

    for item in payload.get("mounts", []):
        if not isinstance(item, dict):
            continue
        operation_raw = item.get("operation") or {}
        if not isinstance(operation_raw, dict):
            continue
        operation = StaticOperationRecord(**operation_raw)
        mount_payload = dict(item)
        mount_payload["operation"] = operation
        mount = StaticMountRecord(**mount_payload)
        catalog.add_mount(mount)

    for item in payload.get("group_help", []):
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
    return catalog


def static_catalog_dependency_paths(loaded) -> List[Path]:
    dependencies: List[Path] = []
    seen: set[Path] = set()

    def add_path(path: Optional[Path]) -> None:
        if path is None:
            return
        resolved = path.expanduser().resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        dependencies.append(resolved)

    for path in getattr(loaded, "paths", []) or []:
        add_path(path)

    raw_sources = (getattr(loaded, "raw", None) or {}).get("sources") or {}
    for source_name, source in raw_sources.items():
        if not isinstance(source, dict) or source.get("enabled", True) is False:
            continue
        manifest_path = _static_manifest_path(source, loaded)
        add_path(manifest_path)
        source_type = str(source.get("type") or "")
        if source_type == "mcp" and manifest_path is None:
            add_path(_static_source_snapshot_path(str(source_name), loaded))
    return dependencies


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

        if source_type == "mcp" and not operations:
            for operation in _static_cached_snapshot_operations(source_name, loaded):
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
                if not operation_matches_select(operation, mount.get("select") or {}):
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
        source_config=_compact_source_config_for_index(source_config),
        mount_config=_compact_mount_config_for_index(mount),
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
        source_config=_compact_source_config_for_index(source_config),
        mount_config=_compact_mount_config_for_index(mount),
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


def _static_cached_snapshot_operations(source_name: str, loaded) -> List[StaticOperationRecord]:
    snapshot_path = _static_source_snapshot_path(source_name, loaded)
    if snapshot_path is None or not snapshot_path.exists():
        return []

    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    operations: List[StaticOperationRecord] = []
    schema_index = payload.get("schema_index") or {}
    for item in payload.get("operations", []):
        if not isinstance(item, dict):
            continue
        try:
            operation = OperationDescriptor.model_validate(item)
        except Exception:
            continue
        schema_record = schema_index.get(operation.id) or {}
        if schema_record.get("input_schema"):
            operation.input_schema = dict(schema_record["input_schema"])
        operations.append(
            StaticOperationRecord(
                id=operation.id,
                source=operation.source,
                provider_type=operation.provider_type,
                title=operation.title,
                stable_name=operation.stable_name,
                description=operation.description,
                kind=operation.kind,
                tags=list(operation.tags),
                group=operation.group,
                risk=operation.risk,
                input_schema=dict(operation.input_schema or {}),
                output_schema=operation.output_schema,
                examples=list(operation.examples),
                supported_surfaces=list(operation.supported_surfaces),
                provider_config=dict(operation.provider_config or {}),
            )
        )
    return operations


def _static_source_snapshot_path(source_name: str, loaded) -> Optional[Path]:
    app_config = loaded.raw.get("app") or {}
    cache_dir = _static_optional_path(app_config.get("cache_dir"), loaded)
    return (cache_dir / "discovery" / f"{_static_safe_name(source_name)}.json").resolve()


def _static_manifest_path(source: Dict[str, Any], loaded) -> Optional[Path]:
    discovery = source.get("discovery") or {}
    manifest = discovery.get("manifest") if isinstance(discovery, dict) else None
    if not manifest:
        return None
    manifest_path = Path(str(manifest)).expanduser()
    if manifest_path.is_absolute():
        return manifest_path.resolve()
    origin = source.get("__origin_file__") if isinstance(source, dict) else None
    if origin:
        return (Path(str(origin)).parent / manifest_path).resolve()
    if loaded.root_paths:
        return (loaded.root_paths[-1].parent / manifest_path).resolve()
    return (Path.cwd() / manifest_path).resolve()


def _static_optional_path(raw_path: Optional[str], loaded) -> Path:
    default = Path("~/.cache/cts").expanduser()
    if raw_path is None:
        return default.resolve()
    candidate = Path(str(raw_path)).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if loaded.root_paths:
        return (loaded.root_paths[-1].parent / candidate).resolve()
    return (Path.cwd() / candidate).resolve()


def _static_safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return normalized or "default"


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


def _compact_source_config_for_index(source_config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source_config, dict):
        return {}
    payload: Dict[str, Any] = {}
    source_type = source_config.get("type")
    if source_type is not None:
        payload["type"] = source_type
    expose_to_surfaces = source_config.get("expose_to_surfaces")
    if isinstance(expose_to_surfaces, list) and expose_to_surfaces:
        payload["expose_to_surfaces"] = list(expose_to_surfaces)
    return payload


def _compact_mount_config_for_index(mount_config: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(mount_config, dict):
        return {}
    payload: Dict[str, Any] = {}

    params = mount_config.get("params")
    if isinstance(params, dict) and params:
        payload["params"] = params

    help_config = mount_config.get("help")
    compact_help: Dict[str, Any] = {}
    if isinstance(help_config, dict):
        param_overrides = help_config.get("param_overrides")
        if isinstance(param_overrides, dict) and param_overrides:
            compact_help["param_overrides"] = param_overrides
        examples = help_config.get("examples")
        if isinstance(examples, list) and examples:
            compact_help["examples"] = examples
        notes = help_config.get("notes")
        if isinstance(notes, list) and notes:
            compact_help["notes"] = notes
    if compact_help:
        payload["help"] = compact_help

    machine_config = mount_config.get("machine")
    if isinstance(machine_config, dict):
        expose_via = machine_config.get("expose_via")
        if isinstance(expose_via, list) and expose_via:
            payload["machine"] = {"expose_via": expose_via}

    return payload
