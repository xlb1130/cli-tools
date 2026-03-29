from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click

from cts.app import schema_from_mount_params
from cts.models import HelpDescriptor
from cts.models import MountRecord


RUNTIME_OPTION_NAMES = {
    "input_json",
    "input_file",
    "output_format",
    "dry_run",
    "non_interactive",
    "yes",
}


def compile_input_schema(mount: MountRecord) -> Dict[str, Any]:
    schema = dict(mount.operation.input_schema or {})
    if not schema and getattr(mount.mount_config, "params", None):
        schema = schema_from_mount_params(mount.mount_config.params)

    properties = dict(schema.get("properties") or {})
    required = set(schema.get("required") or [])

    for name, param in getattr(mount.mount_config, "params", {}).items():
        if name not in properties:
            properties[name] = {"type": param.type}
        if param.help and "description" not in properties[name]:
            properties[name]["description"] = param.help
        if param.default is not None and "default" not in properties[name]:
            properties[name]["default"] = param.default
        if param.enum and "enum" not in properties[name]:
            properties[name]["enum"] = list(param.enum)
        if param.required:
            required.add(name)

    schema["type"] = schema.get("type", "object")
    schema["properties"] = properties
    schema["required"] = sorted(required)
    return schema


def build_click_params(mount: MountRecord) -> List[click.Parameter]:
    schema = compile_input_schema(mount)
    overrides = getattr(mount.mount_config.help, "param_overrides", {})
    params: List[click.Parameter] = []

    for name, property_schema in schema.get("properties", {}).items():
        param_config = getattr(mount.mount_config, "params", {}).get(name)
        option_name = (param_config.flag if param_config and param_config.flag else f"--{name.replace('_', '-')}")
        property_type = property_schema.get("type", "string")
        item_type = property_schema.get("items", {}).get("type", "string")
        enum = property_schema.get("enum")
        required = name in schema.get("required", [])
        default = property_schema.get("default")
        help_text = (
            (overrides.get(name) or {}).get("help")
            or property_schema.get("description")
            or (param_config.help if param_config else None)
            or ""
        )
        help_text = _build_help_text(help_text, property_type, required, default, enum)

        if property_type == "array":
            click_type = _schema_to_click_type(item_type, enum)
            params.append(
                click.Option(
                    [option_name],
                    multiple=True,
                    type=click_type,
                    help=help_text,
                    show_default=False,
                )
            )
            continue

        if property_type == "boolean":
            params.append(click.Option([option_name], is_flag=True, default=None, help=help_text))
            continue

        click_type = _schema_to_click_type(property_type, enum)
        params.append(
            click.Option(
                [option_name],
                type=click_type,
                default=None if default is None else default,
                required=False,
                show_default=default is not None,
                help=help_text,
            )
        )

    params.extend(
        [
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
    )
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
    mount: MountRecord,
    provider_help: Optional[HelpDescriptor] = None,
    schema_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    summary = mount.summary or (provider_help.summary if provider_help else None) or mount.operation.title
    description = mount.description or (provider_help.description if provider_help else None) or mount.operation.description or ""
    examples = _dedupe_strings(
        list(getattr(mount.mount_config.help, "examples", []) or [])
        + list(provider_help.examples if provider_help else [])
        + [example.get("cli", "") for example in mount.operation.examples if isinstance(example, dict)]
    )
    notes = _dedupe_strings(
        list(provider_help.notes if provider_help else [])
        + list(getattr(mount.mount_config.help, "notes", []) or [])
        + _schema_provenance_notes(schema_provenance)
    )

    surfaces = list(
        mount.operation.supported_surfaces
        or getattr(mount.mount_config.machine, "expose_via", [])
        or getattr(mount.source_config, "expose_to_surfaces", [])
    )
    details = [
        f"Risk: {mount.operation.risk}",
        f"Provider: {mount.provider_type}",
        f"Source: {mount.source_name}",
        f"Operation: {mount.operation.id}",
    ]
    if surfaces:
        details.append("Supported surfaces: " + ", ".join(surfaces))
    if mount.generated:
        details.append(f"Generated from: {mount.generated_from}")

    long_help_parts = [description] if description else []
    long_help_parts.append("Details:\n" + "\n".join(f"- {item}" for item in details))
    if notes:
        long_help_parts.append("Notes:\n" + "\n".join(f"- {note}" for note in notes))

    epilog_parts = []
    if examples:
        epilog_parts.append("Examples:\n" + "\n".join(examples))
    epilog_parts.append(f"Stable mount id: {mount.mount_id}")
    epilog_parts.append(f"Stable name: {mount.stable_name}")

    return {
        "short_help": summary,
        "help": "\n\n".join(part for part in long_help_parts if part),
        "epilog": "\n\n".join(epilog_parts),
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
