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
        return "\n".join(
            f"{item['mount_id']}: {' '.join(item.get('command_path') or [])} ({item.get('provider_type') or '-'})"
            for item in payload["mounts"]
        )

    if "errors" in payload and "warnings" in payload:
        lines = ["Config lint: OK" if payload.get("ok") else "Config lint: FAILED"]
        if payload.get("loaded_paths"):
            lines.append("Loaded files:")
            lines.extend(f"- {item}" for item in payload["loaded_paths"])
        if payload.get("warnings"):
            lines.append("Warnings:")
            lines.extend(f"- {item['code']}: {item['message']}" for item in payload["warnings"])
        if payload.get("errors"):
            lines.append("Errors:")
            lines.extend(f"- {item['code']}: {item['message']}" for item in payload["errors"])
        return "\n".join(lines)

    if "items" in payload:
        items = payload["items"]
        if items and isinstance(items[0], dict) and items[0].get("run_id"):
            return "\n".join(
                f"{item['run_id']} {item.get('mode')} ok={item.get('ok')} mount={item.get('mount_id') or '-'}"
                for item in items
            )
        if items and isinstance(items[0], dict) and items[0].get("event"):
            return "\n".join(
                f"{item.get('ts')} {item.get('level')} {item.get('event')} source={item.get('source') or '-'} mount={item.get('mount_id') or '-'}"
                for item in items
            )
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
            return "\n".join(lines)
        return "\n".join(json.dumps(item, ensure_ascii=False) for item in items)

    if payload.get("mount_id") and payload.get("command_path"):
        return "\n".join(
            [
                f"{payload['mount_id']}: {' '.join(payload['command_path'])}",
                f"source={payload.get('source')} provider={payload.get('provider_type')} risk={payload.get('risk')}",
                f"stable_name={payload.get('stable_name')}",
            ]
        )

    if payload.get("name") and payload.get("compiled_operation_count") is not None:
        return "\n".join(
            [
                f"{payload['name']} ({payload.get('type')})",
                f"operations={payload.get('compiled_operation_count')} enabled={payload.get('enabled')}",
                f"origin={payload.get('origin_file') or '<unknown>'}",
            ]
        )

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
            f"run_id={payload['run_id']}",
            f"mode={payload.get('mode')} ok={payload.get('ok')} exit_code={payload.get('exit_code')}",
            f"mount={payload.get('mount_id') or '-'} source={payload.get('source') or '-'}",
        ]
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
    operation_ids = payload.get("operation_ids") or []
    if operation_ids:
        blocks.append(_render_single_column_table("Operation IDs", operation_ids))
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
    ignored_keys = {"ok", "text", "data", "config", "compiled", "profile"}
    rows = [(key.replace("_", " ").title(), _stringify(value)) for key, value in payload.items() if key not in ignored_keys]
    blocks: List[RenderableType] = [_render_key_values(title=f"Action {payload['action']}", rows=rows)]
    if payload.get("profile") is not None and isinstance(payload["profile"], dict):
        profile = payload["profile"]
        if "configured" in profile and "source_count" in profile:
            blocks.append(_render_auth_profile(profile))
        else:
            blocks.append(Panel(JSON.from_data(profile, ensure_ascii=False, indent=2), title="Profile", expand=False))
    if payload.get("warnings"):
        blocks.append(_render_single_column_table("Warnings", payload["warnings"]))
    if payload.get("config") is not None:
        blocks.append(Panel(JSON.from_data(payload["config"], ensure_ascii=False, indent=2), title="Config", expand=False))
    if payload.get("compiled") is not None:
        blocks.append(Panel(JSON.from_data(payload["compiled"], ensure_ascii=False, indent=2), title="Compiled", expand=False))
    return Group(*blocks)


def _render_doctor(payload: Dict[str, Any]) -> RenderableType:
    summary = _render_key_values(
        title="Doctor",
        rows=[
            ("Config Files", str(len(payload.get("config_paths") or []))),
            ("Checks", str(len(payload.get("checks") or []))),
            ("Conflicts", str(len(payload.get("conflicts") or []))),
            ("Discovery Errors", str(len(payload.get("discovery_errors") or {}))),
            ("Plugin Conflicts", str(len(payload.get("plugin_provider_conflicts") or []))),
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
    if payload.get("config_paths"):
        blocks.append(_render_single_column_table("Config Paths", payload["config_paths"]))
    if payload.get("runtime_paths"):
        blocks.append(_render_key_values(title="Runtime Paths", rows=[(k, str(v)) for k, v in payload["runtime_paths"].items()]))
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
