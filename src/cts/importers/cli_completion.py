from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.execution.logging import utc_now_iso
from cts.importers.cli_help import build_imported_cli_operation, parse_cli_option_spec


@dataclass
class CLICompletionImportResult:
    command_argv: List[str]
    completion_command: Optional[List[str]]
    completion_text: str
    operation: Dict[str, Any]


def import_cli_completion(
    *,
    operation_id: str,
    command_argv: List[str],
    completion_format: str,
    completion_command: Optional[List[str]] = None,
    completion_file: Optional[Path] = None,
    risk: str = "read",
    output_mode: str = "text",
    title: Optional[str] = None,
) -> CLICompletionImportResult:
    if completion_command is None and completion_file is None:
        raise ValueError("completion_command or completion_file is required")

    if completion_file is not None:
        completion_text = completion_file.read_text(encoding="utf-8")
    else:
        assert completion_command is not None
        completed = subprocess.run(
            completion_command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            message = stderr or stdout or "CLI completion command failed"
            raise RuntimeError(message)
        completion_text = completed.stdout

    parsed = parse_completion_output(completion_text, completion_format)
    operation = build_imported_cli_operation(
        operation_id=operation_id,
        command_argv=command_argv,
        parsed=parsed,
        risk=risk,
        output_mode=output_mode,
        title=title,
        imported_from={
            "strategy": "cli_completion",
            "completion_format": completion_format,
            "completion_command": list(completion_command) if completion_command else None,
            "completion_file": str(completion_file) if completion_file else None,
            "captured_at": utc_now_iso(),
        },
    )
    return CLICompletionImportResult(
        command_argv=list(command_argv),
        completion_command=list(completion_command) if completion_command else None,
        completion_text=completion_text,
        operation=operation,
    )


def parse_completion_output(text: str, completion_format: str) -> Dict[str, Any]:
    normalized = completion_format.lower()
    if normalized in {"lines", "fish"}:
        return _parse_line_completion(text)
    if normalized == "json":
        return _parse_json_completion(text)
    raise ValueError(f"unsupported completion format: {completion_format}")


def _parse_line_completion(text: str) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    option_bindings: Dict[str, Dict[str, Any]] = {}
    option_order: List[str] = []

    for line in text.splitlines():
        current = line.strip()
        if not current or current.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("\t")]
        spec = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""
        metadata = _parse_metadata(parts[2:])

        item = parse_cli_option_spec(spec, description)
        if item is None:
            continue

        schema = dict(item["schema"])
        if "type" in metadata:
            if item["repeatable"]:
                schema = {"type": "array", "items": {"type": str(metadata["type"])}}
            else:
                schema["type"] = str(metadata["type"])
        if "default" in metadata:
            schema["default"] = metadata["default"]
        if "enum" in metadata and metadata["enum"]:
            schema["enum"] = list(metadata["enum"])
        if metadata.get("description"):
            schema["description"] = str(metadata["description"])

        properties[item["arg_name"]] = schema
        if item["required"] or bool(metadata.get("required")):
            required.append(item["arg_name"])

        binding = {
            "flags": list(item["flags"]),
            "emit_flag": item["emit_flag"],
            "kind": item["kind"],
            "repeatable": bool(metadata.get("repeatable", item["repeatable"])),
        }
        if metadata.get("kind"):
            binding["kind"] = str(metadata["kind"])
        option_bindings[item["arg_name"]] = binding
        option_order.append(item["arg_name"])

    return {
        "title": None,
        "summary": None,
        "description": None,
        "properties": properties,
        "required": sorted(set(required)),
        "option_bindings": option_bindings,
        "option_order": option_order,
    }


def _parse_json_completion(text: str) -> Dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("completion json must be an object")

    properties: Dict[str, Any] = {}
    required: List[str] = []
    option_bindings: Dict[str, Dict[str, Any]] = {}
    option_order: List[str] = []

    for raw in payload.get("options", []):
        if not isinstance(raw, dict):
            continue
        flags = list(raw.get("flags") or ([raw["flag"]] if raw.get("flag") else []))
        if not flags:
            continue
        emit_flag = raw.get("emit_flag") or next((flag for flag in flags if str(flag).startswith("--")), flags[0])
        arg_name = str(raw.get("name") or str(emit_flag).lstrip("-").replace("-", "_"))
        schema_type = str(raw.get("type") or "string")
        repeatable = bool(raw.get("repeatable"))
        schema: Dict[str, Any]
        if repeatable:
            schema = {"type": "array", "items": {"type": schema_type}}
        else:
            schema = {"type": schema_type}
        if raw.get("description"):
            schema["description"] = raw["description"]
        if "default" in raw:
            schema["default"] = raw["default"]
        if raw.get("enum"):
            schema["enum"] = list(raw["enum"])
        properties[arg_name] = schema
        if raw.get("required"):
            required.append(arg_name)
        option_bindings[arg_name] = {
            "flags": flags,
            "emit_flag": emit_flag,
            "kind": raw.get("kind", "value"),
            "repeatable": repeatable,
        }
        option_order.append(arg_name)

    return {
        "title": payload.get("title"),
        "summary": payload.get("summary"),
        "description": payload.get("description"),
        "properties": properties,
        "required": sorted(set(required)),
        "option_bindings": option_bindings,
        "option_order": option_order,
    }


def _parse_metadata(items: List[str]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        key = key.strip().lower()
        value = raw_value.strip()
        if key in {"required", "repeatable"}:
            metadata[key] = value.lower() in {"1", "true", "yes", "on"}
        elif key == "enum":
            metadata[key] = [part.strip() for part in value.split(",") if part.strip()]
        elif key == "default":
            metadata[key] = _coerce_jsonish(value)
        else:
            metadata[key] = value
    return metadata


def _coerce_jsonish(value: str) -> Any:
    normalized = value.strip()
    try:
        return json.loads(normalized)
    except Exception:
        return normalized
