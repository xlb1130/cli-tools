from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.execution.logging import utc_now_iso
from cts.importers.cli_help import build_imported_cli_operation, parse_cli_option_spec


@dataclass
class CLIManpageImportResult:
    command_argv: List[str]
    man_command: Optional[List[str]]
    man_text: str
    operation: Dict[str, Any]


def import_cli_manpage(
    *,
    operation_id: str,
    command_argv: List[str],
    man_command: Optional[List[str]] = None,
    man_file: Optional[Path] = None,
    risk: str = "read",
    output_mode: str = "text",
    title: Optional[str] = None,
) -> CLIManpageImportResult:
    if man_command is None and man_file is None:
        raise ValueError("man_command or man_file is required")

    if man_file is not None:
        man_text = man_file.read_text(encoding="utf-8")
    else:
        assert man_command is not None
        completed = subprocess.run(
            man_command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            message = stderr or stdout or "CLI man page command failed"
            raise RuntimeError(message)
        man_text = completed.stdout

    parsed = parse_manpage_output(man_text)
    operation = build_imported_cli_operation(
        operation_id=operation_id,
        command_argv=command_argv,
        parsed=parsed,
        risk=risk,
        output_mode=output_mode,
        title=title,
        imported_from={
            "strategy": "cli_manpage",
            "man_command": list(man_command) if man_command else None,
            "man_file": str(man_file) if man_file else None,
            "captured_at": utc_now_iso(),
        },
    )
    return CLIManpageImportResult(
        command_argv=list(command_argv),
        man_command=list(man_command) if man_command else None,
        man_text=man_text,
        operation=operation,
    )


def parse_manpage_output(text: str) -> Dict[str, Any]:
    lines = [_strip_backspaces(line.rstrip("\n")) for line in text.splitlines()]
    sections = _split_sections(lines)

    name_lines = sections.get("NAME", [])
    synopsis_lines = sections.get("SYNOPSIS", [])
    options_lines = sections.get("OPTIONS") or sections.get("OPTION") or sections.get("PARAMETERS") or []

    parsed_options = _parse_man_options(options_lines)
    properties: Dict[str, Any] = {}
    required: List[str] = []
    option_bindings: Dict[str, Dict[str, Any]] = {}
    option_order: List[str] = []

    for item in parsed_options:
        properties[item["arg_name"]] = dict(item["schema"])
        if item["required"]:
            required.append(item["arg_name"])
        option_bindings[item["arg_name"]] = {
            "flags": list(item["flags"]),
            "emit_flag": item["emit_flag"],
            "kind": item["kind"],
            "repeatable": item["repeatable"],
        }
        option_order.append(item["arg_name"])

    section_descriptions = []
    for key in ["DESCRIPTION", "OVERVIEW"]:
        for line in sections.get(key, []):
            current = line.strip()
            if current:
                section_descriptions.append(current)

    title, summary = _parse_name_section(name_lines)
    synopsis = " ".join(line.strip() for line in synopsis_lines if line.strip())
    description_parts = [part for part in [summary, *section_descriptions] if part]
    if synopsis:
        description_parts.append(f"Synopsis: {synopsis}")

    return {
        "title": title,
        "summary": summary,
        "description": " ".join(description_parts).strip() or None,
        "properties": properties,
        "required": sorted(set(required)),
        "option_bindings": option_bindings,
        "option_order": option_order,
    }


def _split_sections(lines: List[str]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current_section = "_preamble"
    sections[current_section] = []

    for line in lines:
        stripped = line.strip()
        if _looks_like_section_header(stripped):
            current_section = stripped.upper()
            sections.setdefault(current_section, [])
            continue
        sections.setdefault(current_section, []).append(line)
    return sections


def _looks_like_section_header(value: str) -> bool:
    if not value:
        return False
    if len(value.split()) > 4:
        return False
    letters = [char for char in value if char.isalpha()]
    if not letters:
        return False
    return value == value.upper()


def _parse_name_section(lines: List[str]) -> tuple[Optional[str], Optional[str]]:
    collapsed = " ".join(line.strip() for line in lines if line.strip())
    if not collapsed:
        return None, None
    parts = re.split(r"\s+-\s+", collapsed, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return collapsed.strip(), collapsed.strip()


def _parse_man_options(lines: List[str]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    current_spec: Optional[str] = None
    current_desc_lines: List[str] = []

    def flush() -> None:
        nonlocal current_spec, current_desc_lines
        if not current_spec:
            return
        parsed = parse_cli_option_spec(current_spec, " ".join(current_desc_lines).strip())
        if parsed is not None:
            entries.append(parsed)
        current_spec = None
        current_desc_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if _looks_like_option_spec(stripped):
            flush()
            current_spec = stripped
            continue
        if current_spec:
            current_desc_lines.append(stripped)
    flush()
    return entries


def _looks_like_option_spec(value: str) -> bool:
    return bool(re.match(r"^(?:-[A-Za-z0-9],\s*)?--?[A-Za-z0-9]", value))


def _strip_backspaces(value: str) -> str:
    return re.sub(r".\x08", "", value)
