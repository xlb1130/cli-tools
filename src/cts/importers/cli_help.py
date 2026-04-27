from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from cts.execution.logging import utc_now_iso


@dataclass
class CLIHelpImportResult:
    command_argv: List[str]
    help_command: List[str]
    help_text: str
    operation: Dict[str, Any]


@dataclass
class CLIHelpTreeNode:
    command_argv: List[str]
    help_command: List[str]
    help_text: str
    subcommands: List[str]
    summary: Optional[str] = None
    description: Optional[str] = None


def build_imported_cli_operation(
    *,
    operation_id: str,
    command_argv: List[str],
    parsed: Dict[str, Any],
    risk: str,
    output_mode: str,
    title: Optional[str],
    imported_from: Dict[str, Any],
) -> Dict[str, Any]:
    input_schema = {
        "type": "object",
        "properties": parsed["properties"],
        "required": parsed["required"],
    }
    operation_title = title or parsed["title"] or operation_id
    description = parsed["description"] or parsed["summary"]
    return {
        "id": operation_id,
        "title": operation_title,
        "description": description,
        "kind": "action",
        "risk": risk,
        "input_schema": input_schema,
        "supported_surfaces": ["cli", "invoke"],
        "examples": [{"cli": " ".join(command_argv)}],
        "command_argv": list(command_argv),
        "option_bindings": parsed["option_bindings"],
        "option_order": parsed["option_order"],
        "output": {"mode": output_mode},
        "imported_from": imported_from,
    }


def import_cli_help(
    *,
    operation_id: str,
    command_argv: List[str],
    help_flag: str = "--help",
    risk: str = "read",
    output_mode: str = "text",
    title: Optional[str] = None,
) -> CLIHelpImportResult:
    help_command, help_text = _run_help_command(command_argv, help_flag=help_flag)
    parsed = _parse_help_output(help_text)
    operation = build_imported_cli_operation(
        operation_id=operation_id,
        command_argv=command_argv,
        parsed=parsed,
        risk=risk,
        output_mode=output_mode,
        title=title,
        imported_from={
            "strategy": "cli_help",
            "help_command": list(help_command),
            "captured_at": utc_now_iso(),
        },
    )
    return CLIHelpImportResult(command_argv=list(command_argv), help_command=help_command, help_text=help_text, operation=operation)


def inspect_cli_help(
    *,
    command_argv: List[str],
    help_flag: str = "--help",
) -> CLIHelpTreeNode:
    help_command, help_text = _run_help_command(command_argv, help_flag=help_flag)
    parsed = summarize_help_text(help_text)
    return CLIHelpTreeNode(
        command_argv=list(command_argv),
        help_command=help_command,
        help_text=help_text,
        subcommands=extract_help_subcommands(help_text),
        summary=parsed.get("summary"),
        description=parsed.get("description"),
    )


def summarize_help_text(help_text: str) -> Dict[str, Optional[str]]:
    parsed = _parse_help_output(help_text)
    return {
        "summary": parsed.get("summary"),
        "description": parsed.get("description"),
    }


def merge_operation_into_manifest(path: Path, operation: Dict[str, Any], *, executable: Optional[str] = None) -> Dict[str, Any]:
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"manifest root must be a mapping: {path}")
    else:
        payload = {"version": 1, "operations": []}

    if executable and not payload.get("executable"):
        payload["executable"] = executable

    operations = payload.get("operations")
    if not isinstance(operations, list):
        operations = []
    replaced = False
    for index, item in enumerate(operations):
        if isinstance(item, dict) and item.get("id") == operation.get("id"):
            operations[index] = operation
            replaced = True
            break
    if not replaced:
        operations.append(operation)
    payload["operations"] = operations

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return payload


def write_manifest_operations(path: Path, operations: List[Dict[str, Any]], *, executable: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"version": 1, "operations": list(operations)}
    if executable:
        payload["executable"] = executable
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return payload


def _parse_help_output(help_text: str) -> Dict[str, Any]:
    lines = help_text.splitlines()
    usage_index = _find_usage_index(lines)
    options_index = _find_section_index(lines, {"options:", "optional arguments:", "optional options:"})

    title = None
    summary = None
    description = None
    if usage_index is not None:
        for index in range(usage_index + 1, len(lines)):
            current = lines[index].strip()
            if not current:
                continue
            if current.lower().endswith(":") and index != usage_index + 1:
                break
            title = current
            break

    if usage_index is not None and options_index is not None and options_index > usage_index:
        description_lines = [line.strip() for line in lines[usage_index + 1 : options_index] if line.strip()]
        if description_lines:
            summary = description_lines[0]
            description = " ".join(description_lines)

    parsed_options = _parse_option_lines(lines[options_index + 1 :] if options_index is not None else [])
    properties: Dict[str, Any] = {}
    required: List[str] = []
    option_bindings: Dict[str, Dict[str, Any]] = {}
    option_order: List[str] = []

    for item in parsed_options:
        arg_name = item["arg_name"]
        properties[arg_name] = dict(item["schema"])
        if item["required"]:
            required.append(arg_name)
        option_bindings[arg_name] = {
            "flags": list(item["flags"]),
            "emit_flag": item["emit_flag"],
            "kind": item["kind"],
            "repeatable": item["repeatable"],
        }
        option_order.append(arg_name)

    return {
        "title": title,
        "summary": summary,
        "description": description,
        "properties": properties,
        "required": sorted(set(required)),
        "option_bindings": option_bindings,
        "option_order": option_order,
    }


def extract_help_subcommands(help_text: str) -> List[str]:
    lines = help_text.splitlines()
    subcommands: List[str] = []
    for section_name in {
        "commands:",
        "subcommands:",
        "available commands:",
        "available subcommands:",
    }:
        for section_index in _find_section_indexes(lines, {section_name}):
            subcommands.extend(_extract_section_tokens(lines, section_index))

    usage_line = next((line.strip().lower() for line in lines if line.strip().lower().startswith("usage:")), "")
    if "<resource>" in usage_line:
        for section_index in _find_placeholder_section_indexes(lines, placeholder="resource"):
            subcommands.extend(_extract_section_tokens(lines, section_index))
    if "<action>" in usage_line:
        for section_index in _find_placeholder_section_indexes(lines, placeholder="action"):
            subcommands.extend(_extract_section_tokens(lines, section_index))

    unique: List[str] = []
    for name in subcommands:
        if name not in unique:
            unique.append(name)
    return unique


def _extract_section_tokens(lines: List[str], section_index: int) -> List[str]:
    tokens: List[str] = []
    for line in lines[section_index + 1 :]:
        if not line.strip():
            if tokens:
                break
            continue
        if not line.startswith(" "):
            break
        match = re.match(
            r"^\s{2,4}([A-Za-z0-9_][A-Za-z0-9._:-]*)(?:\s{2,}|\s+\[|\s+<|$)",
            line,
        )
        if not match:
            continue
        name = match.group(1).strip()
        if name.lower() == "help":
            continue
        if name and name not in tokens:
            tokens.append(name)
    return tokens


def _find_section_indexes(lines: List[str], names: set[str]) -> List[int]:
    indexes: List[int] = []
    normalized_names = {name.lower() for name in names}
    for index, line in enumerate(lines):
        if line.strip().lower() in normalized_names:
            indexes.append(index)
    return indexes


def _find_placeholder_section_indexes(lines: List[str], *, placeholder: str) -> List[int]:
    indexes: List[int] = []
    placeholder_lower = placeholder.lower()
    command_section_names = {
        "commands:",
        "subcommands:",
        "available commands:",
        "available subcommands:",
    }
    for index, line in enumerate(lines):
        normalized = line.strip().lower()
        if not normalized.endswith(":"):
            continue
        if normalized in command_section_names:
            continue
        if placeholder_lower not in normalized:
            continue
        indexes.append(index)
    return indexes


def _run_help_command(command_argv: List[str], *, help_flag: str) -> Tuple[List[str], str]:
    help_command = list(command_argv) + [help_flag]
    completed = subprocess.run(
        help_command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        message = stderr or stdout or "CLI help command failed"
        raise RuntimeError(message)
    return help_command, completed.stdout


def _find_usage_index(lines: List[str]) -> Optional[int]:
    for index, line in enumerate(lines):
        if line.strip().lower().startswith("usage:"):
            return index
    return None


def _find_section_index(lines: List[str], names: set[str]) -> Optional[int]:
    for index, line in enumerate(lines):
        if line.strip().lower() in names:
            return index
    return None


def _parse_option_lines(lines: List[str]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    current_spec: Optional[str] = None
    current_desc_lines: List[str] = []

    def flush() -> None:
        nonlocal current_spec, current_desc_lines
        if not current_spec:
            return
        parsed = _parse_option_entry(current_spec, " ".join(current_desc_lines).strip())
        if parsed is not None:
            entries.append(parsed)
        current_spec = None
        current_desc_lines = []

    for line in lines:
        if not line.strip():
            flush()
            continue
        match = re.match(r"^\s{2,}(-[^\s].*?)(?:\s{2,}(.*))?$", line)
        if match:
            flush()
            current_spec = match.group(1).rstrip()
            if match.group(2):
                current_desc_lines.append(match.group(2).strip())
            continue
        if current_spec and line.startswith(" " * 8):
            current_desc_lines.append(line.strip())
            continue
    flush()
    return entries


def _parse_option_entry(spec: str, description: str) -> Optional[Dict[str, Any]]:
    if spec.startswith("-h, --help") or spec.startswith("--help"):
        return None

    flags = _extract_flags(spec)
    if not flags:
        return None
    emit_flag = _pick_emit_flag(flags)
    arg_name = _flag_to_arg_name(emit_flag)
    metavar = _extract_metavar(spec, emit_flag)
    repeated = "..." in spec or "repeatable" in description.lower() or _metavar_is_array(metavar)
    required = "[required]" in description.lower() or "(required)" in description.lower()
    schema_type = _infer_schema_type(metavar, description)
    kind = "flag" if schema_type == "boolean" and metavar is None else "value"

    schema: Dict[str, Any]
    if repeated:
        schema = {"type": "array", "items": {"type": schema_type if schema_type != "boolean" else "string"}}
    else:
        schema = {"type": schema_type}

    normalized_description, default_value = _extract_default(description, schema_type, repeated)
    normalized_description, enum_values = _extract_enum(normalized_description)
    normalized_description = _cleanup_description(normalized_description)

    if normalized_description:
        schema["description"] = normalized_description
    if default_value is not None:
        schema["default"] = default_value
    if enum_values:
        schema["enum"] = enum_values

    return {
        "arg_name": arg_name,
        "flags": flags,
        "emit_flag": emit_flag,
        "kind": kind,
        "repeatable": repeated,
        "required": required and not repeated,
        "schema": schema,
    }


def parse_cli_option_spec(spec: str, description: str) -> Optional[Dict[str, Any]]:
    return _parse_option_entry(spec, description)


def _extract_flags(spec: str) -> List[str]:
    flags = re.findall(r"(?<!/)(--[A-Za-z0-9][A-Za-z0-9._-]*|-[A-Za-z0-9])", spec)
    unique: List[str] = []
    for flag in flags:
        if flag not in unique and not flag.startswith("--no-"):
            unique.append(flag)
    return unique


def _pick_emit_flag(flags: List[str]) -> str:
    long_flags = [flag for flag in flags if flag.startswith("--")]
    return long_flags[0] if long_flags else flags[0]


def _flag_to_arg_name(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_").replace(".", "_")


def _extract_metavar(spec: str, emit_flag: str) -> Optional[str]:
    if "/" in spec and emit_flag in spec and re.search(r"--[A-Za-z0-9._-]+\s*/\s*--", spec):
        return None
    pattern = re.escape(emit_flag) + r"(?:[ =]((?:<[^>\s]+>|[A-Za-z][A-Za-z0-9_<>\[\]-]*\.{0,3})))?"
    match = re.search(pattern, spec)
    if match and match.group(1):
        return match.group(1)
    generic = re.findall(r"(?:^|[ ,])((?:<[^>\s]+>|[A-Za-z][A-Za-z0-9_<>\[\]-]*\.{0,3}))(?:$|[ ,])", spec)
    return generic[0] if generic else None


def _infer_schema_type(metavar: Optional[str], description: str) -> str:
    if metavar is None:
        return "boolean"
    normalized = _normalize_metavar(metavar)
    scalar_normalized = normalized[:-2] if normalized.endswith("[]") else normalized
    upper = scalar_normalized.upper()
    if upper in {"INT", "INTEGER", "COUNT", "NUM"}:
        return "integer"
    if upper in {"FLOAT", "DOUBLE", "NUMBER", "DECIMAL"}:
        return "number"
    if upper in {"BOOL", "BOOLEAN"}:
        return "boolean"
    if "path" in description.lower() or upper in {"PATH", "FILE", "DIR", "DIRECTORY"}:
        return "string"
    return "string"


def _metavar_is_array(metavar: Optional[str]) -> bool:
    if metavar is None:
        return False
    return _normalize_metavar(metavar).endswith("[]")


def _normalize_metavar(metavar: str) -> str:
    return metavar.replace("<", "").replace(">", "").replace("...", "")


def _extract_default(description: str, schema_type: str, repeated: bool) -> tuple[str, Any]:
    patterns = [
        r"\[default:\s*([^\]]+)\]",
        r"\(default:\s*([^)]+)\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, description, flags=re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            cleaned = re.sub(pattern, "", description, flags=re.IGNORECASE).strip()
            return cleaned, _coerce_default(raw, schema_type, repeated)
    return description, None


def _extract_enum(description: str) -> tuple[str, List[Any]]:
    patterns = [
        r"\[possible values:\s*([^\]]+)\]",
        r"\[choices:\s*([^\]]+)\]",
    ]
    for pattern in patterns:
        match = re.search(pattern, description, flags=re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            cleaned = re.sub(pattern, "", description, flags=re.IGNORECASE).strip()
            values = [item.strip() for item in raw.split(",") if item.strip()]
            return cleaned, values
    return description, []


def _cleanup_description(description: str) -> str:
    return re.sub(r"\s+", " ", description).strip(" -")


def _coerce_default(value: str, schema_type: str, repeated: bool) -> Any:
    if repeated:
        if value in {"[]", "none", "None"}:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            return [item.strip() for item in value.split(",") if item.strip()]

    normalized = value.strip()
    if schema_type == "integer":
        try:
            return int(normalized)
        except ValueError:
            return normalized
    if schema_type == "number":
        try:
            return float(normalized)
        except ValueError:
            return normalized
    if schema_type == "boolean":
        lowered = normalized.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return normalized
