from __future__ import annotations

import json
import sys
from io import StringIO
from typing import Any, Dict, Iterable, List

try:
    from rich import box
    from rich.console import Console, Group, RenderableType
    from rich.json import JSON
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    HAS_RICH = True
except ModuleNotFoundError:
    box = None
    Console = None
    Group = None
    JSON = None
    Panel = None
    Table = None
    Text = None
    RenderableType = Any
    HAS_RICH = False


def render_text_payload(payload: Dict[str, Any]) -> str:
    if not HAS_RICH:
        return _render_text_payload_fallback(payload)
    renderable = _payload_to_renderable(payload)
    console = _build_console()
    console.print(renderable)
    return console.file.getvalue().rstrip()


def _render_text_payload_fallback(payload: Dict[str, Any]) -> str:
    if payload.get("ok") is False and "error" in payload:
        error = payload["error"]
        lines = [f"Error [{error['type']}]: {error['message']}"]
        if error.get("suggestions"):
            lines.extend(f"- {item}" for item in error["suggestions"])
        return "\n".join(lines)

    if "mounts" in payload:
        lines = ["Mounts"]
        lines.extend(
            f"- {item['mount_id']}: {' '.join(item.get('command_path') or [])} ({item.get('provider_type') or '-'})"
            for item in payload["mounts"]
        )
        return "\n".join(lines)

    if "errors" in payload and "warnings" in payload:
        lines = ["Config lint: OK" if payload.get("ok") else "Config lint: FAILED"]
        if payload.get("loaded_paths"):
            lines.append("Loaded Files:")
            lines.extend(f"- {item}" for item in payload["loaded_paths"])
        if payload.get("warnings"):
            lines.append("Warnings:")
            lines.extend(f"- {item['code']}: {item['message']}" for item in payload["warnings"])
        if payload.get("errors"):
            lines.append("Errors:")
            lines.extend(f"- {item['code']}: {item['message']}" for item in payload["errors"])
        return "\n".join(lines)

    if "checks" in payload and "runtime_paths" in payload:
        lines = [
            "Doctor",
            f"- config_files: {len(payload.get('config_paths') or [])}",
            f"- checks: {len(payload.get('checks') or [])}",
            f"- conflicts: {len(payload.get('conflicts') or [])}",
            f"- discovery_errors: {len(payload.get('discovery_errors') or {})}",
        ]
        lines.append("Health Checks")
        lines.extend(
            f"- {item.get('source') or '-'} provider={item.get('provider_type') or '-'} ok={item.get('ok')} provider_ok={item.get('provider_ok')}"
            for item in payload.get("checks") or []
        )
        lines.append("Runtime Paths")
        lines.extend(f"- {key}: {value}" for key, value in (payload.get("runtime_paths") or {}).items())
        compatibility = payload.get("compatibility") or {}
        if compatibility:
            lines.append("Compatibility")
            lines.append(f"- compatibility_ok: {compatibility.get('ok')}")
            lines.extend(f"- {item.get('message')}" for item in compatibility.get("issues") or [])
        auth = payload.get("auth") or {}
        if auth:
            lines.append("Auth Validation")
            lines.append(f"- auth_valid: {auth.get('valid_count', 0)}/{auth.get('total_count', 0)}")
        reliability = payload.get("reliability") or {}
        if reliability:
            lines.append("Reliability")
            lines.append(f"- reliability_budgets: {reliability.get('configured_budget_count', 0)}")
        return "\n".join(lines)

    if "items" in payload:
        items = payload["items"]
        if items and isinstance(items[0], dict) and items[0].get("run_id"):
            lines = ["Runs"]
            lines.extend(
                f"- {item['run_id']} {item.get('mode')} ok={item.get('ok')} mount={item.get('mount_id') or '-'}"
                for item in items
            )
            return "\n".join(lines)
        if items and isinstance(items[0], dict) and items[0].get("event"):
            lines = ["Logs"]
            lines.extend(
                f"- {item.get('ts')} {item.get('level')} {item.get('event')} source={item.get('source') or '-'} mount={item.get('mount_id') or '-'}"
                for item in items
            )
            return "\n".join(lines)
        if items and isinstance(items[0], dict) and items[0].get("source"):
            lines = []
            for item in items:
                line = (
                    f"{item.get('source')} ({item.get('provider_type')}) "
                    f"ok={item.get('ok')} usable={item.get('usable')} operations={item.get('operation_count')}"
                )
                if item.get("drift") and item["drift"].get("changed"):
                    line += f" drift={item['drift'].get('severity')}"
                if item.get("fallback"):
                    line += f" fallback={item['fallback']}"
                if item.get("error"):
                    line += f" error={item['error']}"
                lines.append(line)
            if payload.get("report_path"):
                lines.append(f"report={payload['report_path']}")
            if payload.get("capability_snapshot_path"):
                lines.append(f"capability_snapshot={payload['capability_snapshot_path']}")
            return "\n".join(["Sources", *[f"- {line}" for line in lines]])
        if items and isinstance(items[0], dict) and items[0].get("name") and "configured" in items[0] and "source_count" in items[0]:
            lines = ["Auth Profiles"]
            lines.extend(
                f"- {item.get('name')} state={item.get('state')} configured={item.get('configured')} sources={item.get('source_count')}"
                for item in items
            )
            if payload.get("summary"):
                lines.append("Summary")
                lines.extend(f"- {key}: {_stringify(value)}" for key, value in payload["summary"].items())
            return "\n".join(lines)
        if items and isinstance(items[0], dict) and items[0].get("name") and items[0].get("provider") and "value_present" in items[0]:
            lines = ["Secrets"]
            lines.extend(
                f"- {item.get('name')} provider={item.get('provider')} state={item.get('state')} value={'present' if item.get('value_present') else 'missing'}"
                for item in items
            )
            if payload.get("summary"):
                lines.append("Summary")
                lines.extend(f"- {key}: {_stringify(value)}" for key, value in payload["summary"].items())
            return "\n".join(lines)
        if items and isinstance(items[0], dict) and items[0].get("name") and items[0].get("type") and "operation_count" in items[0]:
            lines = ["Sources"]
            lines.extend(
                f"- {item.get('name')} ({item.get('type')}) discovery={item.get('discovery_mode')} operations={item.get('operation_count')} auth={item.get('auth_ref') or '-'}"
                for item in items
            )
            return "\n".join(lines)
        return "\n".join(json.dumps(item, ensure_ascii=False) for item in items)

    if payload.get("surface") and payload.get("base_url"):
        lines = [f"Surface {payload.get('surface')}"]
        lines.append(f"URL: {payload.get('base_url')}")
        if payload.get("browser_url"):
            lines.append(f"Open: {payload.get('browser_url')}")
        if payload.get("ui_enabled") is not None:
            lines.append(f"UI Enabled: {payload.get('ui_enabled')}")
        if payload.get("ui_dir"):
            lines.append(f"UI Dir: {payload.get('ui_dir')}")
        if payload.get("tools_count") is not None:
            lines.append(f"Tools: {payload.get('tools_count')}")
        if payload.get("next_command"):
            lines.append("Next")
            lines.append(f"- {payload.get('next_command')}")
        return "\n".join(lines)

    if payload.get("action") == "completion_bootstrap":
        lines = [f"Completion Bootstrap ({payload.get('shell')})"]
        if payload.get("message"):
            lines.append(payload["message"])
        if payload.get("copy_command"):
            lines.append("Copy Command")
            lines.append(f"- {payload['copy_command']}")
        if payload.get("command_preview"):
            lines.append("Command Preview")
            lines.extend(f"- {line}" for line in str(payload["command_preview"]).splitlines())
        return "\n".join(lines)

    if payload.get("name") and payload.get("compiled_operation_count") is not None:
        lines = [
            f"Source {payload['name']} ({payload.get('type')})",
            f"operations={payload.get('compiled_operation_count')} enabled={payload.get('enabled')}",
            f"origin={payload.get('origin_file') or '<unknown>'}",
        ]
        auth = payload.get("auth") or {}
        if auth:
            lines.append(f"auth={auth.get('state') or '-'}")
        discovery_state = payload.get("discovery_state") or {}
        if discovery_state:
            lines.append(f"discovery_state={_stringify(discovery_state)}")
        drift_state = payload.get("drift_state") or {}
        if drift_state:
            lines.append(f"drift_state={_stringify(drift_state)}")
        operation_ids = payload.get("operation_ids") or []
        if operation_ids:
            lines.append("Operation IDs")
            lines.extend(f"- {item}" for item in operation_ids)
        next_commands = payload.get("next_commands") or []
        if next_commands:
            lines.append("Next Suggested Command")
            lines.extend(f"- {item}" for item in next_commands)
        return "\n".join(lines)

    if payload.get("source") and payload.get("provider_type") and "operation_count" in payload:
        lines = [
            f"{payload['source']} ({payload['provider_type']})",
            f"ok={payload.get('ok')} operations={payload.get('operation_count')}",
        ]
        if payload.get("discovery"):
            lines.append(
                "discovery="
                + str(payload["discovery"].get("ok"))
                + f" count={payload['discovery'].get('operation_count', 0)}"
            )
        return "\n".join(lines)

    if payload.get("run_id") and payload.get("mode"):
        lines = [
            f"Run {payload['run_id']}",
            f"mode={payload.get('mode')} ok={payload.get('ok')} exit_code={payload.get('exit_code')}",
            f"mount={payload.get('mount_id') or '-'} source={payload.get('source') or '-'}",
        ]
        if payload.get("error_type") or payload.get("error_code"):
            lines.append(f"error_type={payload.get('error_type') or '-'} error_code={payload.get('error_code') or '-'}")
        if payload.get("summary"):
            lines.append("Summary")
            lines.append(f"- {payload.get('summary')}")
        if payload.get("metadata") is not None:
            lines.append("Metadata")
            lines.append(f"- {json.dumps(payload.get('metadata'), ensure_ascii=False)}")
        return "\n".join(lines)

    if "profiles" in payload and "valid_count" in payload and "total_count" in payload:
        lines = [
            "Auth Validation",
            f"- ok={payload.get('ok')}",
            f"- valid={payload.get('valid_count')}/{payload.get('total_count')}",
        ]
        for name, item in sorted((payload.get("profiles") or {}).items()):
            issues = ",".join(issue.get("code", "-") for issue in item.get("issues") or []) or "-"
            actions = ",".join(action.get("action", "-") for action in item.get("actions") or []) or "-"
            lines.append(f"- {name}: state={item.get('state')} valid={item.get('valid')} issues={issues} actions={actions}")
        return "\n".join(lines)

    if "valid" in payload and payload.get("auth_profile"):
        lines = [
            f"Auth Check {payload['auth_profile']}",
            f"- valid={payload.get('valid')}",
            f"- state={payload.get('state') or '-'}",
        ]
        if payload.get("issues"):
            lines.append("Issues")
            lines.extend(f"- {item.get('code')}: {item.get('message')}" for item in payload["issues"])
        if payload.get("actions"):
            lines.append("Actions")
            lines.extend(f"- {item.get('action')}: {item.get('command') or item.get('message') or '-'}" for item in payload["actions"])
        if payload.get("status"):
            lines.append("Status")
            lines.extend(f"- {key}: {_stringify(value)}" for key, value in payload["status"].items())
        return "\n".join(lines)

    if payload.get("name") and "configured" in payload and "source_count" in payload:
        lines = [
            f"Auth {payload['name']}",
            f"state={payload.get('state') or '-'} configured={payload.get('configured')} sources={payload.get('source_count')}",
        ]
        source_names = payload.get("source_names") or []
        if source_names:
            lines.append("Sources")
            lines.extend(f"- {item}" for item in source_names)
        if payload.get("status"):
            lines.append("Status")
            lines.extend(f"- {key}: {_stringify(value)}" for key, value in payload["status"].items())
        next_commands = payload.get("next_commands") or []
        if next_commands:
            lines.append("Next Suggested Command")
            lines.extend(f"- {item}" for item in next_commands)
        return "\n".join(lines)

    if payload.get("name") and payload.get("provider") and "value_present" in payload:
        lines = [
            f"Secret {payload['name']}",
            f"provider={payload.get('provider')} state={payload.get('state') or '-'} value={'present' if payload.get('value_present') else 'missing'}",
        ]
        metadata = payload.get("metadata") or {}
        if metadata:
            lines.append("Metadata")
            lines.extend(f"- {key}: {_stringify(value)}" for key, value in metadata.items())
        next_commands = payload.get("next_commands") or []
        if next_commands:
            lines.append("Next Suggested Command")
            lines.extend(f"- {item}" for item in next_commands)
        return "\n".join(lines)

    if payload.get("ok") is True and payload.get("action"):
        lines = [f"Action {payload.get('action')}"]
        change_rows = _action_change_rows(payload)
        if change_rows:
            lines.append("What Changed")
            lines.extend(f"- {key}: {value}" for key, value in change_rows)
        where_rows = _action_where_rows(payload)
        if where_rows:
            lines.append("Where Written")
            lines.extend(f"- {key}: {value}" for key, value in where_rows)
        if payload.get("warnings"):
            lines.append("Warnings")
            lines.extend(f"- {item}" for item in payload["warnings"])
        next_commands = list(payload.get("next_commands") or [])
        if payload.get("next_command"):
            next_commands.insert(0, payload["next_command"])
        if next_commands:
            lines.append("Next Suggested Command")
            lines.extend(f"- {item}" for item in next_commands)
        return "\n".join(lines)

    if _is_execution_payload(payload):
        lines = [
            f"Execution {payload.get('mount_id') or payload.get('stable_name') or '-'}",
            f"status={'ok' if payload.get('ok') else 'failed'} mode={payload.get('mode') or '-'} duration={_format_duration(payload.get('duration_ms'))}",
            f"provider={payload.get('provider_type') or '-'} source={payload.get('source') or '-'} operation={payload.get('operation_id') or '-'}",
        ]
        if payload.get("summary"):
            lines.append(f"summary={payload['summary']}")
        reliability = payload.get("reliability") or {}
        if reliability:
            lines.append(
                "reliability="
                + f"attempts={reliability.get('attempts', 1)}"
                + f" retried={reliability.get('was_retried', False)}"
                + f" duplicate={reliability.get('was_duplicate', False)}"
            )
        if payload.get("text"):
            lines.append("Output")
            lines.append(str(payload["text"]))
        elif payload.get("data") is not None:
            lines.append("Output")
            lines.append(json.dumps(payload["data"], ensure_ascii=False, indent=2))
        metadata = payload.get("metadata") or {}
        if metadata:
            lines.append("Metadata")
            lines.append(json.dumps(metadata, ensure_ascii=False))
        return "\n".join(lines)

    if payload.get("mount_id") and payload.get("command_path"):
        lines = [
            f"Mount {payload['mount_id']}: {' '.join(payload['command_path'])}",
            f"source={payload.get('source')} provider={payload.get('provider_type')} risk={payload.get('risk')}",
            f"stable_name={payload.get('stable_name')}",
        ]
        aliases = payload.get("aliases") or []
        if aliases:
            lines.append("Aliases")
            lines.extend(f"- {' '.join(item)}" for item in aliases)
        next_commands = payload.get("next_commands") or []
        if next_commands:
            lines.append("Next Suggested Command")
            lines.extend(f"- {item}" for item in next_commands)
        return "\n".join(lines)

    if payload.get("text"):
        return str(payload["text"])

    if payload.get("data") is not None:
        return json.dumps(payload["data"], ensure_ascii=False, indent=2)

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_console() -> Console:
    is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    return Console(
        file=StringIO(),
        record=True,
        force_terminal=is_tty,
        color_system="auto" if is_tty else None,
        width=100,
        soft_wrap=False,
    )


def _payload_to_renderable(payload: Dict[str, Any]) -> RenderableType:
    if payload.get("ok") is False and "error" in payload:
        return _render_error(payload["error"])

    if "checks" in payload and "runtime_paths" in payload:
        return _render_doctor(payload)

    if "profiles" in payload and "valid_count" in payload and "total_count" in payload:
        return _render_auth_validation(payload)

    if "mounts" in payload:
        return _render_mounts(payload["mounts"], conflicts=payload.get("conflicts"))

    if "errors" in payload and "warnings" in payload:
        return _render_lint(payload)

    if "items" in payload:
        return _render_items(payload)

    if _is_execution_payload(payload):
        return _render_execution_result(payload)

    if payload.get("mount_id") and payload.get("command_path"):
        return _render_mount_details(payload)

    if payload.get("name") and payload.get("compiled_operation_count") is not None:
        return _render_source_details(payload)

    if payload.get("source") and payload.get("provider_type") and "operation_count" in payload:
        rows = [
            ("Source", payload.get("source") or "-"),
            ("Provider", payload.get("provider_type") or "-"),
            ("OK", str(payload.get("ok"))),
            ("Operations", str(payload.get("operation_count"))),
        ]
        if payload.get("discovery"):
            discovery = payload["discovery"]
            rows.append(("Discovery", f"ok={discovery.get('ok')} count={discovery.get('operation_count', 0)}"))
        return _render_key_values(title="Source Check", rows=rows)

    if payload.get("run_id") and payload.get("mode"):
        return _render_run_detail(payload)

    if payload.get("name") and "configured" in payload and "source_count" in payload:
        return _render_auth_profile(payload)

    if payload.get("name") and payload.get("provider") and "value_present" in payload:
        return _render_secret_detail(payload)

    if "valid" in payload and payload.get("auth_profile"):
        return _render_auth_validation_detail(payload)

    if payload.get("app") and "source_count" in payload and "mount_count" in payload:
        return _render_app_summary(payload)

    if payload.get("ok") is True and payload.get("action"):
        return _render_action_result(payload)

    if payload.get("text"):
        return Text(str(payload["text"]))

    if payload.get("data") is not None:
        return JSON.from_data(payload["data"], ensure_ascii=False, indent=2)

    return JSON.from_data(payload, ensure_ascii=False, indent=2)


def _render_error(error: Dict[str, Any]) -> RenderableType:
    body: List[RenderableType] = [Text(error.get("message") or "Unknown error", style="bold red")]
    suggestions = error.get("suggestions") or []
    if suggestions:
        table = Table.grid(padding=(0, 1))
        table.add_column()
        for item in suggestions:
            table.add_row(f"- {item}")
        body.append(table)
    return Panel(
        Group(*body),
        title=Text(f"Error [{error.get('type') or 'unknown'}]"),
        border_style="red",
        expand=False,
    )


def _render_mounts(mounts: Iterable[Dict[str, Any]], *, conflicts: Any = None) -> RenderableType:
    table = Table(title="Mounts", box=box.SIMPLE_HEAVY)
    table.add_column("Mount ID", style="cyan", no_wrap=True)
    table.add_column("Command")
    table.add_column("Source", style="green", no_wrap=True)
    table.add_column("Provider", style="magenta", no_wrap=True)
    table.add_column("Risk", no_wrap=True)
    for item in mounts:
        table.add_row(
            item.get("mount_id") or "-",
            " ".join(item.get("command_path") or []),
            item.get("source") or "-",
            item.get("provider_type") or "-",
            item.get("risk") or "-",
        )
    blocks: List[RenderableType] = [table]
    if conflicts:
        blocks.append(_render_single_column_table("Conflicts", [_compact_json(item) for item in conflicts]))
    return Group(*blocks)


def _render_lint(payload: Dict[str, Any]) -> RenderableType:
    blocks: List[RenderableType] = []
    status = Text("Config lint: OK" if payload.get("ok") else "Config lint: FAILED")
    status.stylize("bold green" if payload.get("ok") else "bold red")
    blocks.append(status)

    if payload.get("loaded_paths"):
        blocks.append(_render_single_column_table("Loaded Files", payload["loaded_paths"]))
    if payload.get("warnings"):
        blocks.append(_render_issue_table("Warnings", payload["warnings"], style="yellow"))
    if payload.get("errors"):
        blocks.append(_render_issue_table("Errors", payload["errors"], style="red"))
    return Group(*blocks)


def _render_items(payload: Dict[str, Any]) -> RenderableType:
    items = payload.get("items") or []
    if not items:
        return Text("No items.")

    first = items[0]
    if isinstance(first, dict) and first.get("run_id"):
        table = Table(title="Runs", box=box.SIMPLE_HEAVY)
        table.add_column("Run ID", style="cyan", no_wrap=True)
        table.add_column("Mode", no_wrap=True)
        table.add_column("OK", no_wrap=True)
        table.add_column("Mount")
        for item in items:
            table.add_row(
                item.get("run_id") or "-",
                item.get("mode") or "-",
                str(item.get("ok")),
                item.get("mount_id") or "-",
            )
        return table

    if isinstance(first, dict) and first.get("event") and first.get("ts"):
        table = Table(title="Logs", box=box.SIMPLE_HEAVY)
        table.add_column("Time", style="cyan", no_wrap=True)
        table.add_column("Level", no_wrap=True)
        table.add_column("Event", style="magenta", no_wrap=True)
        table.add_column("Source")
        table.add_column("Mount")
        for item in items:
            table.add_row(
                str(item.get("ts") or "-"),
                str(item.get("level") or "-"),
                str(item.get("event") or "-"),
                str(item.get("source") or "-"),
                str(item.get("mount_id") or "-"),
            )
        blocks: List[RenderableType] = [table]
        if payload.get("summary"):
            blocks.append(_render_key_values(title="Summary", rows=[(k, _stringify(v)) for k, v in payload["summary"].items()]))
        return Group(*blocks)

    if isinstance(first, dict) and first.get("name") and "configured" in first and "source_count" in first:
        table = Table(title="Auth Profiles", box=box.SIMPLE_HEAVY)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("State", no_wrap=True)
        table.add_column("Configured", no_wrap=True)
        table.add_column("Sources", justify="right")
        table.add_column("Reason")
        for item in items:
            table.add_row(
                item.get("name") or "-",
                item.get("state") or "-",
                str(item.get("configured")),
                str(item.get("source_count")),
                item.get("reason") or "-",
            )
        blocks: List[RenderableType] = [table]
        if payload.get("summary"):
            blocks.append(_render_key_values(title="Summary", rows=[(k, _stringify(v)) for k, v in payload["summary"].items()]))
        return Group(*blocks)

    if isinstance(first, dict) and first.get("name") and first.get("provider") and "value_present" in first:
        table = Table(title="Secrets", box=box.SIMPLE_HEAVY)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Provider", no_wrap=True)
        table.add_column("State", no_wrap=True)
        table.add_column("Value", no_wrap=True)
        table.add_column("Reason")
        for item in items:
            table.add_row(
                item.get("name") or "-",
                item.get("provider") or "-",
                item.get("state") or "-",
                "present" if item.get("value_present") else "missing",
                item.get("reason") or "-",
            )
        blocks: List[RenderableType] = [table]
        if payload.get("summary"):
            blocks.append(_render_key_values(title="Summary", rows=[(k, _stringify(v)) for k, v in payload["summary"].items()]))
        return Group(*blocks)

    if isinstance(first, dict) and first.get("source"):
        table = Table(title="Sources", box=box.SIMPLE_HEAVY)
        table.add_column("Source", style="cyan", no_wrap=True)
        table.add_column("Provider", style="magenta", no_wrap=True)
        table.add_column("OK", no_wrap=True)
        table.add_column("Usable", no_wrap=True)
        table.add_column("Operations", justify="right")
        table.add_column("Notes")
        for item in items:
            notes: List[str] = []
            drift = item.get("drift") or {}
            if drift.get("changed"):
                notes.append(f"drift={drift.get('severity')}")
            if item.get("fallback"):
                notes.append(f"fallback={item['fallback']}")
            if item.get("error"):
                notes.append(f"error={item['error']}")
            table.add_row(
                item.get("source") or "-",
                item.get("provider_type") or "-",
                str(item.get("ok")),
                str(item.get("usable")),
                str(item.get("operation_count")),
                ", ".join(notes) if notes else "-",
            )
        footers: List[RenderableType] = [table]
        if payload.get("report_path"):
            footers.append(Text(f"report: {payload['report_path']}"))
        if payload.get("capability_snapshot_path"):
            footers.append(Text(f"capability_snapshot: {payload['capability_snapshot_path']}"))
        return Group(*footers)

    if isinstance(first, dict) and first.get("name") and first.get("type") and "operation_count" in first:
        table = Table(title="Sources", box=box.SIMPLE_HEAVY)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta", no_wrap=True)
        table.add_column("Enabled", no_wrap=True)
        table.add_column("Discovery", no_wrap=True)
        table.add_column("Operations", justify="right")
        table.add_column("Auth")
        table.add_column("Origin")
        for item in items:
            auth = item.get("auth") or {}
            auth_text = item.get("auth_ref") or auth.get("state") or "-"
            table.add_row(
                item.get("name") or "-",
                item.get("type") or "-",
                str(item.get("enabled")),
                item.get("discovery_mode") or "-",
                str(item.get("operation_count")),
                auth_text,
                item.get("origin_file") or "-",
            )
        return table

    if isinstance(first, dict) and first.get("from") and first.get("to"):
        table = Table(title="Aliases", box=box.SIMPLE_HEAVY)
        table.add_column("From", style="cyan")
        table.add_column("To", style="green")
        for item in items:
            table.add_row(str(item.get("from") or "-"), str(item.get("to") or "-"))
        return table

    if isinstance(first, dict):
        rendered = [Panel(JSON.from_data(item, ensure_ascii=False, indent=2), expand=False) for item in items]
        return Group(*rendered)

    return _render_single_column_table("Items", [json.dumps(item, ensure_ascii=False) for item in items])


def _render_key_values(*, title: str, rows: Iterable[tuple[str, str]]) -> RenderableType:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    for key, value in rows:
        table.add_row(key, value)
    return Panel(table, title=title, box=box.ROUNDED, expand=False)


def _is_execution_payload(payload: Dict[str, Any]) -> bool:
    return bool(
        payload.get("mount_id")
        and payload.get("source")
        and payload.get("provider_type")
        and payload.get("operation_id")
        and (
            "data" in payload
            or "text" in payload
            or "stderr" in payload
            or "status_code" in payload
            or payload.get("mode") in {"invoke", "explain"}
        )
    )


def _format_duration(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        duration_ms = int(value)
    except (TypeError, ValueError):
        return str(value)
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    return f"{duration_ms / 1000:.2f} s"


def _render_execution_result(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title=f"Execution {payload.get('mount_id') or payload.get('stable_name') or '-'}",
        rows=[
            ("Status", "ok" if payload.get("ok") else "failed"),
            ("Mode", payload.get("mode") or "-"),
            ("Duration", _format_duration(payload.get("duration_ms"))),
            ("Provider", payload.get("provider_type") or "-"),
            ("Source", payload.get("source") or "-"),
            ("Operation", payload.get("operation_id") or "-"),
            ("Risk", payload.get("risk") or "-"),
            ("Run ID", payload.get("run_id") or "-"),
            ("Trace ID", payload.get("trace_id") or "-"),
        ],
    )
    blocks: List[RenderableType] = [summary]
    if payload.get("summary"):
        blocks.append(Panel(Text(str(payload["summary"])), title="Summary", expand=False))
    if payload.get("data") is not None:
        blocks.append(Panel(JSON.from_data(payload["data"], ensure_ascii=False, indent=2), title="Output", expand=False))
    elif payload.get("text"):
        blocks.append(Panel(Text(str(payload["text"])), title="Output", expand=False))
    if payload.get("stderr"):
        blocks.append(Panel(Text(str(payload["stderr"])), title="Stderr", expand=False, border_style="yellow"))
    reliability = payload.get("reliability") or {}
    if reliability:
        rows = [
            ("Attempts", str(reliability.get("attempts", 1))),
            ("Retried", str(reliability.get("was_retried", False))),
            ("Rate Limited", str(reliability.get("was_rate_limited", False))),
            ("Duplicate", str(reliability.get("was_duplicate", False))),
        ]
        if reliability.get("duration_ms") is not None:
            rows.append(("Reliability Duration", _format_duration(reliability.get("duration_ms"))))
        blocks.append(_render_key_values(title="Reliability", rows=rows))
    metadata = payload.get("metadata") or {}
    if metadata:
        blocks.append(Panel(JSON.from_data(metadata, ensure_ascii=False, indent=2), title="Metadata", expand=False))
    return Group(*blocks)


def _render_single_column_table(title: str, items: Iterable[Any]) -> RenderableType:
    table = Table(title=title, box=box.SIMPLE)
    table.add_column("Value")
    for item in items:
        table.add_row(str(item))
    return table


def _render_issue_table(title: str, items: Iterable[Dict[str, Any]], *, style: str) -> RenderableType:
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("Code", style=style, no_wrap=True)
    table.add_column("Message")
    for item in items:
        table.add_row(str(item.get("code") or "-"), str(item.get("message") or "-"))
    return table


def _render_source_details(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title=f"Source {payload['name']}",
        rows=[
            ("Type", payload.get("type") or "-"),
            ("Enabled", str(payload.get("enabled"))),
            ("Operations", str(payload.get("compiled_operation_count"))),
            ("Discovery", payload.get("discovery_mode") or "-"),
            ("Origin", payload.get("origin_file") or "<unknown>"),
        ],
    )
    blocks: List[RenderableType] = [summary]
    auth = payload.get("auth") or {}
    if auth:
        blocks.append(_render_key_values(title="Auth", rows=[(k, _stringify(v)) for k, v in auth.items()]))
    discovery_state = payload.get("discovery_state") or {}
    if discovery_state:
        blocks.append(_render_key_values(title="Discovery State", rows=[(k, _stringify(v)) for k, v in discovery_state.items()]))
    drift_state = payload.get("drift_state") or {}
    if drift_state:
        blocks.append(_render_key_values(title="Drift State", rows=[(k, _stringify(v)) for k, v in drift_state.items()]))
    operation_ids = payload.get("operation_ids") or []
    if operation_ids:
        blocks.append(_render_single_column_table("Operation IDs", operation_ids))
    next_commands = payload.get("next_commands") or []
    if next_commands:
        blocks.append(_render_single_column_table("Next Suggested Command", next_commands))
    return Group(*blocks)


def _render_mount_details(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title=f"Mount {payload['mount_id']}",
        rows=[
            ("Command", " ".join(payload.get("command_path") or [])),
            ("Source", payload.get("source") or "-"),
            ("Provider", payload.get("provider_type") or "-"),
            ("Operation", payload.get("operation_id") or "-"),
            ("Risk", payload.get("risk") or "-"),
            ("Stable Name", payload.get("stable_name") or "-"),
            ("Origin", payload.get("origin_file") or "-"),
        ],
    )
    blocks: List[RenderableType] = [summary]
    aliases = payload.get("aliases") or []
    if aliases:
        blocks.append(_render_single_column_table("Aliases", [" ".join(item) for item in aliases]))
    if payload.get("summary"):
        blocks.append(Panel(Text(str(payload["summary"])), title="Summary", expand=False))
    if payload.get("description"):
        blocks.append(Panel(Text(str(payload["description"])), title="Description", expand=False))
    if payload.get("supported_surfaces"):
        blocks.append(_render_single_column_table("Supported Surfaces", payload["supported_surfaces"]))
    params = payload.get("params") or {}
    if params:
        blocks.append(_render_single_column_table("Parameters", [f"{name}: {_stringify(item)}" for name, item in params.items()]))
    next_commands = payload.get("next_commands") or []
    if next_commands:
        blocks.append(_render_single_column_table("Next Suggested Command", next_commands))
    return Group(*blocks)


def _render_app_summary(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title=f"App {payload['app']}",
        rows=[
            ("Profile", str(payload.get("profile") or "-")),
            ("Sources", str(payload.get("source_count"))),
            ("Mounts", str(payload.get("mount_count"))),
            ("Plugins", str(payload.get("plugin_count"))),
            ("Hooks", str(payload.get("hook_count"))),
            ("Discovery Errors", str(payload.get("discovery_error_count"))),
        ],
    )
    blocks: List[RenderableType] = [summary]
    if payload.get("config_files"):
        blocks.append(_render_single_column_table("Config Files", payload["config_files"]))
    runtime_paths = payload.get("runtime_paths") or {}
    if runtime_paths:
        blocks.append(_render_key_values(title="Runtime Paths", rows=[(k, str(v)) for k, v in runtime_paths.items()]))
    return Group(*blocks)


def _render_action_result(payload: Dict[str, Any]) -> RenderableType:
    blocks: List[RenderableType] = [
        _render_key_values(
            title=f"Action {payload['action']}",
            rows=[("Status", "ok"), ("Action", str(payload.get("action") or "-"))],
        )
    ]
    changed_rows = _action_change_rows(payload)
    if changed_rows:
        blocks.append(_render_key_values(title="What Changed", rows=changed_rows))
    where_rows = _action_where_rows(payload)
    if where_rows:
        blocks.append(_render_key_values(title="Where Written", rows=where_rows))
    if payload.get("profile") is not None and isinstance(payload["profile"], dict):
        profile = payload["profile"]
        if "configured" in profile and "source_count" in profile:
            blocks.append(_render_auth_profile(profile))
        else:
            blocks.append(Panel(JSON.from_data(profile, ensure_ascii=False, indent=2), title="Profile", expand=False))
    if payload.get("warnings"):
        blocks.append(_render_single_column_table("Warnings", payload["warnings"]))
    next_commands = list(payload.get("next_commands") or [])
    if payload.get("next_command"):
        next_commands.insert(0, payload["next_command"])
    if next_commands:
        blocks.append(_render_single_column_table("Next Suggested Command", next_commands))
    if payload.get("config") is not None:
        blocks.append(Panel(JSON.from_data(payload["config"], ensure_ascii=False, indent=2), title="Config", expand=False))
    if payload.get("compiled") is not None:
        blocks.append(Panel(JSON.from_data(payload["compiled"], ensure_ascii=False, indent=2), title="Compiled", expand=False))
    return Group(*blocks)


def _action_change_rows(payload: Dict[str, Any]) -> List[tuple[str, str]]:
    rows: List[tuple[str, str]] = []
    for key in (
        "source",
        "source_name",
        "provider_type",
        "mount_id",
        "operation_id",
        "reconcile_action",
        "removed_mounts",
        "remaining_count",
        "mounts_created",
        "shell",
        "base_url",
        "tools_count",
    ):
        if payload.get(key) is not None:
            rows.append((key.replace("_", " ").title(), _stringify(payload[key])))
    if payload.get("alias") is not None:
        rows.append(("Alias", _stringify(payload["alias"])))
    if payload.get("message") and payload.get("action") in {"completion_install", "completion_bootstrap"}:
        rows.append(("Message", str(payload["message"])))
    return rows


def _action_where_rows(payload: Dict[str, Any]) -> List[tuple[str, str]]:
    rows: List[tuple[str, str]] = []
    for key in ("file", "completion_script", "servers_file", "ui_dir", "browser_url"):
        if payload.get(key):
            rows.append((key.replace("_", " ").title(), _stringify(payload[key])))
    if payload.get("created_file") is not None:
        rows.append(("Created File", str(payload["created_file"])))
    return rows


def _render_doctor(payload: Dict[str, Any]) -> RenderableType:
    compatibility = payload.get("compatibility") or {}
    auth = payload.get("auth") or {}
    reliability = payload.get("reliability") or {}
    summary = _render_key_values(
        title="Doctor",
        rows=[
            ("Config Files", str(len(payload.get("config_paths") or []))),
            ("Checks", str(len(payload.get("checks") or []))),
            ("Conflicts", str(len(payload.get("conflicts") or []))),
            ("Discovery Errors", str(len(payload.get("discovery_errors") or {}))),
            ("Plugin Conflicts", str(len(payload.get("plugin_provider_conflicts") or []))),
            ("Compatibility", "enabled" if compatibility else "not requested"),
            ("Auth Validation", "enabled" if auth else "not requested"),
            ("Reliability Budgets", str(reliability.get("configured_budget_count", 0))),
        ],
    )
    checks = payload.get("checks") or []
    check_table = Table(title="Health Checks", box=box.SIMPLE_HEAVY)
    check_table.add_column("Source", style="cyan", no_wrap=True)
    check_table.add_column("Provider", style="magenta", no_wrap=True)
    check_table.add_column("OK", no_wrap=True)
    check_table.add_column("Provider OK", no_wrap=True)
    check_table.add_column("Operations", justify="right")
    for item in checks:
        check_table.add_row(
            item.get("source") or "-",
            item.get("provider_type") or "-",
            str(item.get("ok")),
            str(item.get("provider_ok")),
            str(item.get("operation_count")),
        )
    blocks: List[RenderableType] = [summary, check_table]
    conflicts = payload.get("conflicts") or []
    if conflicts:
        blocks.append(_render_single_column_table("Command Conflicts", [_compact_json(item) for item in conflicts]))
    discovery_errors = payload.get("discovery_errors") or {}
    if discovery_errors:
        blocks.append(
            _render_single_column_table(
                "Discovery Errors",
                [f"{name}: {_stringify(error)}" for name, error in sorted(discovery_errors.items())],
            )
        )
    provider_conflicts = payload.get("plugin_provider_conflicts") or []
    if provider_conflicts:
        blocks.append(_render_single_column_table("Plugin Provider Conflicts", [_compact_json(item) for item in provider_conflicts]))
    if payload.get("config_paths"):
        blocks.append(_render_single_column_table("Config Paths", payload["config_paths"]))
    if payload.get("runtime_paths"):
        blocks.append(_render_key_values(title="Runtime Paths", rows=[(k, str(v)) for k, v in payload["runtime_paths"].items()]))
    if reliability:
        blocks.append(_render_reliability_status(reliability))
    if compatibility:
        blocks.append(_render_compatibility_report(compatibility))
    if auth:
        blocks.append(_render_auth_validation(auth))
    return Group(*blocks)


def _render_reliability_status(payload: Dict[str, Any]) -> RenderableType:
    blocks: List[RenderableType] = [
        _render_key_values(
            title="Reliability",
            rows=[
                ("Configured Budgets", str(payload.get("configured_budget_count", 0))),
                ("Defaults", "configured" if payload.get("defaults") else "none"),
            ],
        )
    ]
    defaults = payload.get("defaults") or {}
    if defaults:
        blocks.append(_render_key_values(title="Reliability Defaults", rows=[(k, _stringify(v)) for k, v in defaults.items()]))
    budgets = payload.get("configured_budgets") or {}
    if budgets:
        table = Table(title="Reliability Budgets", box=box.SIMPLE_HEAVY)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Settings")
        for name, item in sorted(budgets.items()):
            table.add_row(name, _compact_json(item))
        blocks.append(table)
    status = payload.get("status") or {}
    if status:
        blocks.append(_render_key_values(title="Reliability Status", rows=[(k, _stringify(v)) for k, v in status.items()]))
    return Group(*blocks)


def _render_compatibility_report(payload: Dict[str, Any]) -> RenderableType:
    blocks: List[RenderableType] = [
        _render_key_values(
            title="Compatibility",
            rows=[
                ("OK", str(payload.get("ok"))),
                ("Errors", str(payload.get("error_count", 0))),
                ("Warnings", str(payload.get("warning_count", 0))),
            ],
        )
    ]
    issues = payload.get("issues") or []
    if issues:
        table = Table(title="Compatibility Issues", box=box.SIMPLE_HEAVY)
        table.add_column("Level", no_wrap=True)
        table.add_column("Category", style="yellow", no_wrap=True)
        table.add_column("Object", no_wrap=True)
        table.add_column("Message")
        table.add_column("Suggestion")
        for item in issues:
            object_name = item.get("object_name") or item.get("object_type") or "-"
            table.add_row(
                item.get("level") or "-",
                item.get("category") or "-",
                object_name,
                item.get("message") or "-",
                item.get("suggestion") or "-",
            )
        blocks.append(table)
    return Group(*blocks)


def _render_run_detail(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title=f"Run {payload['run_id']}",
        rows=[
            ("Mode", payload.get("mode") or "-"),
            ("OK", str(payload.get("ok"))),
            ("Exit Code", str(payload.get("exit_code"))),
            ("Mount", payload.get("mount_id") or "-"),
            ("Source", payload.get("source") or "-"),
            ("Trace ID", payload.get("trace_id") or "-"),
            ("Error Type", payload.get("error_type") or "-"),
            ("Error Code", payload.get("error_code") or "-"),
        ],
    )
    blocks: List[RenderableType] = [summary]
    if payload.get("summary"):
        blocks.append(Panel(Text(str(payload["summary"])), title="Summary", expand=False))
    if payload.get("metadata"):
        blocks.append(Panel(JSON.from_data(payload["metadata"], ensure_ascii=False, indent=2), title="Metadata", expand=False))
    return Group(*blocks)


def _render_auth_profile(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title=f"Auth {payload['name']}",
        rows=[
            ("State", payload.get("state") or "-"),
            ("Configured", str(payload.get("configured"))),
            ("Sources", str(payload.get("source_count"))),
            ("Reason", payload.get("reason") or "-"),
        ],
    )
    blocks: List[RenderableType] = [summary]
    source_names = payload.get("source_names") or []
    if source_names:
        blocks.append(_render_single_column_table("Sources", source_names))
    status = payload.get("status") or {}
    if status:
        blocks.append(_render_key_values(title="Status", rows=[(k, _stringify(v)) for k, v in status.items()]))
    next_commands = payload.get("next_commands") or []
    if next_commands:
        blocks.append(_render_single_column_table("Next Suggested Command", next_commands))
    return Group(*blocks)


def _render_secret_detail(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title=f"Secret {payload['name']}",
        rows=[
            ("Provider", payload.get("provider") or "-"),
            ("State", payload.get("state") or "-"),
            ("Value", "present" if payload.get("value_present") else "missing"),
            ("Reason", payload.get("reason") or "-"),
        ],
    )
    blocks: List[RenderableType] = [summary]
    metadata = payload.get("metadata") or {}
    if metadata:
        blocks.append(_render_key_values(title="Metadata", rows=[(k, _stringify(v)) for k, v in metadata.items()]))
    next_commands = payload.get("next_commands") or []
    if next_commands:
        blocks.append(_render_single_column_table("Next Suggested Command", next_commands))
    return Group(*blocks)


def _render_auth_validation(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title="Auth Validation",
        rows=[
            ("OK", str(payload.get("ok"))),
            ("Valid", str(payload.get("valid_count"))),
            ("Total", str(payload.get("total_count"))),
        ],
    )
    table = Table(title="Profiles", box=box.SIMPLE_HEAVY)
    table.add_column("Profile", style="cyan", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Valid", no_wrap=True)
    table.add_column("Issues")
    table.add_column("Actions")
    for name, item in sorted((payload.get("profiles") or {}).items()):
        issues = ", ".join(issue.get("code", "-") for issue in item.get("issues") or []) or "-"
        actions = ", ".join(action.get("action", "-") for action in item.get("actions") or []) or "-"
        table.add_row(name, item.get("state") or "-", str(item.get("valid")), issues, actions)
    return Group(summary, table)


def _render_auth_validation_detail(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title=f"Auth Check {payload['auth_profile']}",
        rows=[
            ("Valid", str(payload.get("valid"))),
            ("State", payload.get("state") or "-"),
        ],
    )
    blocks: List[RenderableType] = [summary]
    issues = payload.get("issues") or []
    if issues:
        table = Table(title="Issues", box=box.SIMPLE_HEAVY)
        table.add_column("Code", style="yellow", no_wrap=True)
        table.add_column("Message")
        table.add_column("Level", no_wrap=True)
        for item in issues:
            table.add_row(item.get("code") or "-", item.get("message") or "-", item.get("level") or "-")
        blocks.append(table)
    actions = payload.get("actions") or []
    if actions:
        table = Table(title="Actions", box=box.SIMPLE_HEAVY)
        table.add_column("Action", style="cyan", no_wrap=True)
        table.add_column("Command")
        table.add_column("Message")
        for item in actions:
            table.add_row(item.get("action") or "-", item.get("command") or "-", item.get("message") or "-")
        blocks.append(table)
    status = payload.get("status") or {}
    if status:
        blocks.append(_render_key_values(title="Status", rows=[(k, _stringify(v)) for k, v in status.items()]))
    return Group(*blocks)


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return _compact_json(value)
    return str(value)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
