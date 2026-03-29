from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.execution.logging import utc_now_iso
from cts.importers.cli_completion import parse_completion_output
from cts.importers.cli_help import build_imported_cli_operation


@dataclass
class CLISchemaImportResult:
    command_argv: List[str]
    schema_command: Optional[List[str]]
    schema_payload: Dict[str, Any]
    operation: Dict[str, Any]


def import_cli_schema(
    *,
    operation_id: str,
    command_argv: List[str],
    schema_command: Optional[List[str]] = None,
    schema_file: Optional[Path] = None,
    schema_format: str = "auto",
    risk: str = "read",
    output_mode: str = "text",
    title: Optional[str] = None,
) -> CLISchemaImportResult:
    if schema_command is None and schema_file is None:
        raise ValueError("schema_command or schema_file is required")

    if schema_file is not None:
        raw_text = schema_file.read_text(encoding="utf-8")
    else:
        assert schema_command is not None
        completed = subprocess.run(
            schema_command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            message = stderr or stdout or "CLI schema command failed"
            raise RuntimeError(message)
        raw_text = completed.stdout

    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("schema payload must be a JSON object")

    operation = operation_from_schema_payload(
        operation_id=operation_id,
        command_argv=command_argv,
        payload=payload,
        schema_format=schema_format,
        risk=risk,
        output_mode=output_mode,
        title=title,
        schema_command=schema_command,
        schema_file=schema_file,
    )
    return CLISchemaImportResult(
        command_argv=list(command_argv),
        schema_command=list(schema_command) if schema_command else None,
        schema_payload=payload,
        operation=operation,
    )


def operation_from_schema_payload(
    *,
    operation_id: str,
    command_argv: List[str],
    payload: Dict[str, Any],
    schema_format: str,
    risk: str,
    output_mode: str,
    title: Optional[str],
    schema_command: Optional[List[str]],
    schema_file: Optional[Path],
) -> Dict[str, Any]:
    normalized_format = schema_format.lower()
    imported_from = {
        "strategy": "cli_schema",
        "schema_format": normalized_format,
        "schema_command": list(schema_command) if schema_command else None,
        "schema_file": str(schema_file) if schema_file else None,
        "captured_at": utc_now_iso(),
    }

    if normalized_format in {"auto", "operation"} and isinstance(payload.get("operation"), dict):
        operation = dict(payload["operation"])
        operation.setdefault("id", operation_id)
        operation.setdefault("title", title or payload.get("title") or operation_id)
        operation.setdefault("risk", risk)
        operation.setdefault("supported_surfaces", ["cli", "invoke"])
        operation.setdefault("examples", [{"cli": " ".join(command_argv)}])
        provider_config = dict(operation.get("provider_config") or {})
        provider_config.setdefault("command_argv", list(command_argv))
        operation["provider_config"] = provider_config
        operation["imported_from"] = imported_from
        return operation

    if normalized_format in {"auto", "bindings"} and _looks_like_bindings_payload(payload):
        operation = build_imported_cli_operation(
            operation_id=operation_id,
            command_argv=command_argv,
            parsed={
                "title": payload.get("title"),
                "summary": payload.get("summary"),
                "description": payload.get("description"),
                "properties": dict((payload.get("input_schema") or {}).get("properties") or {}),
                "required": list((payload.get("input_schema") or {}).get("required") or []),
                "option_bindings": dict(payload.get("option_bindings") or {}),
                "option_order": list(payload.get("option_order") or list((payload.get("option_bindings") or {}).keys())),
            },
            risk=risk,
            output_mode=str(payload.get("output_mode") or output_mode),
            title=title,
            imported_from=imported_from,
        )
        if payload.get("output_schema") is not None:
            operation["output_schema"] = payload.get("output_schema")
        if payload.get("supported_surfaces"):
            operation["supported_surfaces"] = list(payload["supported_surfaces"])
        return operation

    if normalized_format in {"auto", "options"} and isinstance(payload.get("options"), list):
        parsed = parse_completion_output(json.dumps(payload, ensure_ascii=False), "json")
        operation = build_imported_cli_operation(
            operation_id=operation_id,
            command_argv=command_argv,
            parsed=parsed,
            risk=risk,
            output_mode=str(payload.get("output_mode") or output_mode),
            title=title or payload.get("title"),
            imported_from=imported_from,
        )
        if payload.get("output_schema") is not None:
            operation["output_schema"] = payload.get("output_schema")
        if payload.get("supported_surfaces"):
            operation["supported_surfaces"] = list(payload["supported_surfaces"])
        return operation

    raise ValueError(
        "unsupported schema payload; expected one of: operation object, input_schema + option_bindings, or options[]"
    )


def _looks_like_bindings_payload(payload: Dict[str, Any]) -> bool:
    return isinstance(payload.get("input_schema"), dict) and isinstance(payload.get("option_bindings"), dict)
