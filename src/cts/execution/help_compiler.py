from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click


RUNTIME_OPTION_NAMES = {
    "input_json",
    "input_file",
    "output_format",
    "dry_run",
    "non_interactive",
    "yes",
}

REQUEST_PARAMETER_GROUP = "Request Parameters"
RUNTIME_OPTION_GROUP = "Runtime Options"


def compile_input_schema(mount: Any) -> Dict[str, Any]:
    schema = dict(mount.operation.input_schema or {})
    mount_params = _mount_params(mount)
    if not schema and mount_params:
        schema = _schema_from_mount_params(mount_params)

    properties = dict(schema.get("properties") or {})
    required = set(schema.get("required") or [])

    for name, param in mount_params.items():
        param_type = _param_value(param, "type", "string")
        param_help = _param_value(param, "help")
        param_default = _param_value(param, "default")
        param_enum = _param_value(param, "enum", []) or []
        param_required = bool(_param_value(param, "required", False))
        if name not in properties:
            properties[name] = {"type": param_type}
        if param_help and "description" not in properties[name]:
            properties[name]["description"] = param_help
        if param_default is not None and "default" not in properties[name]:
            properties[name]["default"] = param_default
        if param_enum and "enum" not in properties[name]:
            properties[name]["enum"] = list(param_enum)
        if param_required:
            required.add(name)

    schema["type"] = schema.get("type", "object")
    schema["properties"] = properties
    schema["required"] = sorted(required)
    return schema


def build_click_params(mount: Any) -> List[click.Parameter]:
    schema = compile_input_schema(mount)
    overrides = _mount_help_param_overrides(mount)
    params: List[click.Parameter] = []
    mount_params = _mount_params(mount)

    for name, property_schema in schema.get("properties", {}).items():
        param_config = mount_params.get(name)
        option_name = _param_value(param_config, "flag") or f"--{name.replace('_', '-')}"
        property_type = property_schema.get("type", "string")
        item_type = property_schema.get("items", {}).get("type", "string")
        enum = property_schema.get("enum")
        required = name in schema.get("required", [])
        default = property_schema.get("default")
        help_text = (
            (overrides.get(name) or {}).get("help")
            or property_schema.get("description")
            or _param_value(param_config, "help")
            or ""
        )
        help_text = _build_help_text(help_text, property_type, required, default, enum)

        if property_type == "array":
            click_type = _schema_to_click_type(item_type, enum)
            option = click.Option(
                [option_name],
                multiple=True,
                type=click_type,
                help=help_text,
                show_default=False,
            )
            setattr(option, "help_group", REQUEST_PARAMETER_GROUP)
            params.append(option)
            continue

        if property_type == "boolean":
            option = click.Option([option_name], is_flag=True, default=None, help=help_text)
            setattr(option, "help_group", REQUEST_PARAMETER_GROUP)
            params.append(option)
            continue

        click_type = _schema_to_click_type(property_type, enum)
        option = click.Option(
            [option_name],
            type=click_type,
            default=None if default is None else default,
            required=False,
            show_default=default is not None,
            help=help_text,
        )
        setattr(option, "help_group", REQUEST_PARAMETER_GROUP)
        params.append(option)

    runtime_options = [
        click.Option(["--input-json", "input_json"], help="Raw JSON object input."),
        click.Option(
            ["--input-file", "input_file"],
            type=click.Path(path_type=Path, exists=True, dir_okay=False),
            help="Path to a JSON file containing the operation input payload.",
        ),
        click.Option(
            ["--output", "output_format"],
            type=click.Choice(["text", "json"]),
            default="text",
            show_default=True,
            help="Render output as text or structured JSON.",
        ),
        click.Option(["--dry-run"], is_flag=True, help="Plan the request without executing it."),
        click.Option(
            ["--non-interactive"],
            is_flag=True,
            help="Disable interactive prompts and return structured errors.",
        ),
        click.Option(["--yes"], is_flag=True, help="Reserved for future confirmable operations."),
    ]
    for option in runtime_options:
        setattr(option, "help_group", RUNTIME_OPTION_GROUP)
    params.extend(runtime_options)
    return params


def extract_request_args(kwargs: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload: Dict[str, Any] = {}

    if kwargs.get("input_file"):
        payload.update(json.loads(Path(kwargs["input_file"]).read_text(encoding="utf-8")))
    if kwargs.get("input_json"):
        payload.update(json.loads(kwargs["input_json"]))

    for key, value in kwargs.items():
        if key in RUNTIME_OPTION_NAMES:
            continue
        if value is None:
            continue
        if isinstance(value, tuple):
            if value:
                payload[key] = list(value)
            continue
        payload[key] = value

    runtime = {key: kwargs.get(key) for key in RUNTIME_OPTION_NAMES}
    return payload, runtime


def compile_command_help(
    mount: Any,
    provider_help: Optional[Any] = None,
    schema_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = mount.summary or (provider_help.summary if provider_help else None) or mount.operation.title
    description = mount.description or (provider_help.description if provider_help else None) or mount.operation.description or ""
    examples = _dedupe_strings(
        list(_mount_help_list(mount, "examples"))
        + list(provider_help.examples if provider_help else [])
        + [example.get("cli", "") for example in mount.operation.examples if isinstance(example, dict)]
    )
    notes = _dedupe_strings(
        list(provider_help.notes if provider_help else [])
        + list(_mount_help_list(mount, "notes"))
        + _schema_provenance_notes(schema_provenance)
    )

    surfaces = list(
        mount.operation.supported_surfaces
        or _mount_machine_list(mount, "expose_via")
        or _source_config_list(mount, "expose_to_surfaces")
    )
    detail_rows: List[Tuple[str, str]] = [
        ("Risk", mount.operation.risk),
        ("Provider", mount.provider_type),
        ("Source", mount.source_name),
        ("Operation", mount.operation.id),
    ]
    if surfaces:
        detail_rows.append(("Supported surfaces", ", ".join(surfaces)))
    if mount.generated:
        detail_rows.append(("Generated from", str(mount.generated_from)))

    long_help_parts = [description] if description else []
    long_help_parts.append("Details:\n" + "\n".join(f"- {label}: {value}" for label, value in detail_rows))
    if notes:
        long_help_parts.append("Notes:\n" + "\n".join(f"- {note}" for note in notes))

    epilog_parts = []
    if examples:
        epilog_parts.append("Examples:\n" + "\n".join(examples))
    epilog_parts.append(f"Stable mount id: {mount.mount_id}")
    epilog_parts.append(f"Stable name: {mount.stable_name}")

    return {
        "summary": summary,
        "short_help": summary,
        "help": "\n\n".join(part for part in long_help_parts if part),
        "epilog": "\n\n".join(epilog_parts),
        "description": description,
        "detail_rows": detail_rows,
        "note_rows": [("Note", note) for note in notes],
        "example_rows": [("Example", example) for example in examples],
        "reference_rows": [
            ("Stable mount id", mount.mount_id),
            ("Stable name", mount.stable_name),
        ],
    }


def _schema_to_click_type(schema_type: str, enum: Any):
    if enum and all(isinstance(item, str) for item in enum):
        return click.Choice(list(enum))
    if schema_type == "integer":
        return click.INT
    if schema_type == "number":
        return click.FLOAT
    return click.STRING


def _build_help_text(
    help_text: str,
    schema_type: str,
    required: bool,
    default: Any,
    enum: Any,
) -> str:
    suffix: List[str] = [f"type={schema_type}"]
    if required:
        suffix.append("required")
    if default is not None:
        suffix.append(f"default={default}")
    if enum:
        suffix.append("enum=" + ",".join(str(item) for item in enum))
    if help_text:
        return help_text + " [" + "; ".join(suffix) + "]"
    return "[" + "; ".join(suffix) + "]"


def _schema_provenance_notes(schema_provenance: Optional[Dict[str, Any]]) -> List[str]:
    if not schema_provenance:
        return []
    parts = [str(schema_provenance.get("strategy", "unknown"))]
    if schema_provenance.get("origin"):
        parts.append(str(schema_provenance["origin"]))
    if schema_provenance.get("confidence") is not None:
        parts.append(f"confidence={schema_provenance['confidence']}")
    return ["Schema provenance: " + " | ".join(parts)]


def _dedupe_strings(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _schema_from_mount_params(params: Dict[str, Any]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in params.items():
        if param.type == "array":
            schema = {"type": "array", "items": {"type": "string"}}
        else:
            schema = {"type": _normalize_schema_type(param.type)}
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


def _normalize_schema_type(param_type: str) -> str:
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


def _mount_params(mount: Any) -> Dict[str, Any]:
    mount_config = mount.mount_config
    if isinstance(mount_config, dict):
        params = mount_config.get("params") or {}
        return params if isinstance(params, dict) else {}
    return getattr(mount_config, "params", {}) or {}


def _mount_help_param_overrides(mount: Any) -> Dict[str, Dict[str, Any]]:
    mount_config = mount.mount_config
    if isinstance(mount_config, dict):
        help_config = mount_config.get("help") or {}
        overrides = help_config.get("param_overrides") or {}
        return overrides if isinstance(overrides, dict) else {}
    help_config = getattr(mount_config, "help", None)
    return getattr(help_config, "param_overrides", {}) or {}


def _mount_help_list(mount: Any, field: str) -> List[str]:
    mount_config = mount.mount_config
    if isinstance(mount_config, dict):
        help_config = mount_config.get("help") or {}
        value = help_config.get(field) or []
        return list(value) if isinstance(value, list) else []
    help_config = getattr(mount_config, "help", None)
    value = getattr(help_config, field, []) if help_config is not None else []
    return list(value or [])


def _mount_machine_list(mount: Any, field: str) -> List[str]:
    mount_config = mount.mount_config
    if isinstance(mount_config, dict):
        machine_config = mount_config.get("machine") or {}
        value = machine_config.get(field) or []
        return list(value) if isinstance(value, list) else []
    machine_config = getattr(mount_config, "machine", None)
    value = getattr(machine_config, field, []) if machine_config is not None else []
    return list(value or [])


def _source_config_list(mount: Any, field: str) -> List[str]:
    source_config = mount.source_config
    if isinstance(source_config, dict):
        value = source_config.get(field) or []
        return list(value) if isinstance(value, list) else []
    value = getattr(source_config, field, []) if source_config is not None else []
    return list(value or [])


def _param_value(param: Any, field: str, default: Any = None) -> Any:
    if param is None:
        return default
    if isinstance(param, dict):
        return param.get(field, default)
    return getattr(param, field, default)
