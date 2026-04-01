from __future__ import annotations

import re
from typing import Any, Dict, List

from cts.config.models import MountConfig, ParamConfig, SourceConfig
from cts.models import MountRecord, OperationDescriptor
from cts.operation_select import operation_matches_select


def build_generated_mount(mount: MountConfig, source_config: SourceConfig, operation: OperationDescriptor) -> MountRecord:
    command_prefix = list(mount.command.under or mount.command.path)
    if not command_prefix:
        command_prefix = tokenize_identifier(mount.id)
    operation_tokens = tokenize_identifier(operation.id)
    if command_prefix and operation_tokens and command_prefix[-1] == operation_tokens[0]:
        operation_tokens = operation_tokens[1:]
    command_path = command_prefix + operation_tokens

    stable_name = operation.stable_name or f"{mount.source}.{operation.id}".replace("_", ".")
    return MountRecord(
        mount_id=f"{mount.id}.{operation.id}",
        source_name=mount.source,
        provider_type=source_config.type,
        operation=operation,
        command_path=command_path,
        aliases=[],
        stable_name=stable_name,
        summary=operation.title,
        description=operation.description,
        source_config=source_config,
        mount_config=mount,
        generated=True,
        generated_from=mount.id,
    )


def build_mount_record(
    mount: MountConfig,
    source_config: SourceConfig,
    operation: OperationDescriptor,
    generated: bool,
) -> MountRecord:
    command_path = list(mount.command.path or [])
    if not command_path:
        command_path = list(mount.command.under or []) + tokenize_identifier(operation.id)
    if not command_path:
        command_path = tokenize_identifier(mount.id)

    stable_name = mount.machine.stable_name or operation.stable_name or f"{mount.source}.{operation.id}".replace("_", ".")

    return MountRecord(
        mount_id=mount.id,
        source_name=mount.source,
        provider_type=source_config.type,
        operation=operation,
        command_path=command_path,
        aliases=[list(alias) for alias in mount.command.aliases],
        stable_name=stable_name,
        summary=mount.help.summary or operation.title,
        description=mount.help.description or operation.description,
        source_config=source_config,
        mount_config=mount,
        generated=generated,
    )


def synthesize_operation(mount: MountConfig, source_config: SourceConfig, operation_id: str) -> OperationDescriptor:
    return OperationDescriptor(
        id=operation_id,
        source=mount.source,
        provider_type=source_config.type,
        title=mount.help.summary or operation_id,
        stable_name=mount.machine.stable_name,
        description=mount.help.description,
        kind="action",
        risk=mount.policy.get("risk", "read"),
        input_schema=schema_from_mount_params(mount.params),
        examples=[{"cli": example} for example in mount.help.examples],
        supported_surfaces=list(mount.machine.expose_via or source_config.expose_to_surfaces),
    )


def schema_from_mount_params(params: Dict[str, ParamConfig]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in params.items():
        if param.type == "array":
            schema = {"type": "array", "items": {"type": "string"}}
        else:
            schema = {"type": normalize_schema_type(param.type)}
        if param.help:
            schema["description"] = param.help
        if param.default is not None:
            schema["default"] = param.default
        if param.enum:
            schema["enum"] = list(param.enum)
        if param.required:
            required.append(name)
        properties[name] = schema
    return {"type": "object", "properties": properties, "required": required}


def normalize_schema_type(param_type: str) -> str:
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


def tokenize_identifier(value: str) -> List[str]:
    parts = [segment for segment in re.split(r"[_./:\-]+", value) if segment]
    return [part.lower() for part in parts] or [value]
