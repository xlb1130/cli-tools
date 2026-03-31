from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, Iterable, List

try:
    from rich import box
    from rich.console import Group, RenderableType
    from rich.json import JSON
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
except ModuleNotFoundError:  # pragma: no cover
    box = None
    Group = None
    JSON = None
    Panel = None
    Syntax = None
    Table = None
    Text = None
    RenderableType = Any


def render_error(error: Dict[str, Any]) -> RenderableType:
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


def render_mounts(mounts: Iterable[Dict[str, Any]], *, conflicts: Any = None) -> RenderableType:
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
        blocks.append(render_single_column_table("Conflicts", [compact_json(item) for item in conflicts]))
    return Group(*blocks)


def render_lint(payload: Dict[str, Any]) -> RenderableType:
    blocks: List[RenderableType] = []
    status = Text("Config lint: OK" if payload.get("ok") else "Config lint: FAILED")
    status.stylize("bold green" if payload.get("ok") else "bold red")
    blocks.append(status)
    if payload.get("loaded_paths"):
        blocks.append(render_single_column_table("Loaded Files", payload["loaded_paths"]))
    if payload.get("warnings"):
        blocks.append(render_issue_table("Warnings", payload["warnings"], style="yellow"))
    if payload.get("errors"):
        blocks.append(render_issue_table("Errors", payload["errors"], style="red"))
    return Group(*blocks)


def render_items(payload: Dict[str, Any]) -> RenderableType:
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
            table.add_row(item.get("run_id") or "-", item.get("mode") or "-", str(item.get("ok")), item.get("mount_id") or "-")
        return table
    if isinstance(first, dict) and first.get("event") and first.get("ts"):
        table = Table(title="Logs", box=box.SIMPLE_HEAVY)
        table.add_column("Time", style="cyan", no_wrap=True)
        table.add_column("Level", no_wrap=True)
        table.add_column("Event", style="magenta", no_wrap=True)
        table.add_column("Source")
        table.add_column("Mount")
        for item in items:
            table.add_row(str(item.get("ts") or "-"), str(item.get("level") or "-"), str(item.get("event") or "-"), str(item.get("source") or "-"), str(item.get("mount_id") or "-"))
        blocks: List[RenderableType] = [table]
        if payload.get("summary"):
            blocks.append(render_key_values(title="Summary", rows=[(k, stringify(v)) for k, v in payload["summary"].items()]))
        return Group(*blocks)
    if isinstance(first, dict) and first.get("name") and "configured" in first and "source_count" in first:
        table = Table(title="Auth Profiles", box=box.SIMPLE_HEAVY)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("State", no_wrap=True)
        table.add_column("Configured", no_wrap=True)
        table.add_column("Sources", justify="right")
        table.add_column("Reason")
        for item in items:
            table.add_row(item.get("name") or "-", item.get("state") or "-", str(item.get("configured")), str(item.get("source_count")), item.get("reason") or "-")
        blocks: List[RenderableType] = [table]
        if payload.get("summary"):
            blocks.append(render_key_values(title="Summary", rows=[(k, stringify(v)) for k, v in payload["summary"].items()]))
        return Group(*blocks)
    if isinstance(first, dict) and first.get("name") and first.get("provider") and "value_present" in first:
        table = Table(title="Secrets", box=box.SIMPLE_HEAVY)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Provider", no_wrap=True)
        table.add_column("State", no_wrap=True)
        table.add_column("Value", no_wrap=True)
        table.add_column("Reason")
        for item in items:
            table.add_row(item.get("name") or "-", item.get("provider") or "-", item.get("state") or "-", "present" if item.get("value_present") else "missing", item.get("reason") or "-")
        blocks: List[RenderableType] = [table]
        if payload.get("summary"):
            blocks.append(render_key_values(title="Summary", rows=[(k, stringify(v)) for k, v in payload["summary"].items()]))
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
            table.add_row(item.get("source") or "-", item.get("provider_type") or "-", str(item.get("ok")), str(item.get("usable")), str(item.get("operation_count")), ", ".join(notes) if notes else "-")
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
            table.add_row(item.get("name") or "-", item.get("type") or "-", str(item.get("enabled")), item.get("discovery_mode") or "-", str(item.get("operation_count")), auth_text, item.get("origin_file") or "-")
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
    return render_single_column_table("Items", [json.dumps(item, ensure_ascii=False) for item in items])


def render_key_values(*, title: str, rows: Iterable[tuple[str, str]]) -> RenderableType:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    for key, value in rows:
        table.add_row(key, value)
    return Panel(table, title=title, box=box.ROUNDED, expand=False)


def is_execution_payload(payload: Dict[str, Any]) -> bool:
    return bool(payload.get("mount_id") and payload.get("source") and payload.get("provider_type") and payload.get("operation_id") and ("data" in payload or "text" in payload or "stderr" in payload or "status_code" in payload or payload.get("mode") in {"invoke", "explain"}))


def format_duration(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        duration_ms = int(value)
    except (TypeError, ValueError):
        return str(value)
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    return f"{duration_ms / 1000:.2f} s"


def render_wrapped_text(value: Any) -> Text:
    return Text(str(value), no_wrap=False, overflow="fold")


def wrap_json_lines(raw: str, width: int = 90) -> str:
    wrapped_lines: List[str] = []
    for line in raw.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        wrapped_lines.extend(textwrap.wrap(line, width=width, subsequent_indent=" " * indent, break_long_words=True, break_on_hyphens=False, drop_whitespace=False, replace_whitespace=False) or [""])
    return "\n".join(wrapped_lines)


def render_wrapped_json(value: Any) -> RenderableType:
    raw = json.dumps(value, ensure_ascii=False, indent=2)
    wrapped = wrap_json_lines(raw)
    if Syntax is None:
        return render_wrapped_text(wrapped)
    return Syntax(wrapped, "json", theme="friendly", word_wrap=False, background_color="default")


def render_execution_result(payload: Dict[str, Any]) -> RenderableType:
    summary = render_key_values(title=f"Execution {payload.get('mount_id') or payload.get('stable_name') or '-'}", rows=[("Status", "ok" if payload.get("ok") else "failed"), ("Mode", payload.get("mode") or "-"), ("Duration", format_duration(payload.get("duration_ms"))), ("Provider", payload.get("provider_type") or "-"), ("Source", payload.get("source") or "-"), ("Operation", payload.get("operation_id") or "-"), ("Risk", payload.get("risk") or "-"), ("Run ID", payload.get("run_id") or "-"), ("Trace ID", payload.get("trace_id") or "-")])
    blocks: List[RenderableType] = [summary]
    if payload.get("summary"):
        blocks.append(Panel(render_wrapped_text(payload["summary"]), title="Summary", expand=False))
    if payload.get("data") is not None:
        blocks.append(Panel(render_wrapped_json(payload["data"]), title="Output", expand=False))
    elif payload.get("text"):
        blocks.append(Panel(render_wrapped_text(payload["text"]), title="Output", expand=False))
    if payload.get("stderr"):
        blocks.append(Panel(render_wrapped_text(payload["stderr"]), title="Stderr", expand=False, border_style="yellow"))
    reliability = payload.get("reliability") or {}
    if reliability:
        rows = [("Attempts", str(reliability.get("attempts", 1))), ("Retried", str(reliability.get("was_retried", False))), ("Rate Limited", str(reliability.get("was_rate_limited", False))), ("Duplicate", str(reliability.get("was_duplicate", False)))]
        if reliability.get("duration_ms") is not None:
            rows.append(("Reliability Duration", format_duration(reliability.get("duration_ms"))))
        blocks.append(render_key_values(title="Reliability", rows=rows))
    metadata = payload.get("metadata") or {}
    if metadata:
        blocks.append(Panel(render_wrapped_json(metadata), title="Metadata", expand=False))
    return Group(*blocks)


def render_single_column_table(title: str, items: Iterable[Any]) -> RenderableType:
    table = Table(title=title, box=box.SIMPLE)
    table.add_column("Value")
    for item in items:
        table.add_row(str(item))
    return table


def render_issue_table(title: str, items: Iterable[Dict[str, Any]], *, style: str) -> RenderableType:
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("Code", style=style, no_wrap=True)
    table.add_column("Message")
    for item in items:
        table.add_row(str(item.get("code") or "-"), str(item.get("message") or "-"))
    return table


def render_source_details(payload: Dict[str, Any]) -> RenderableType:
    summary = render_key_values(title=f"Source {payload['name']} ({payload.get('type') or '-'})", rows=[("Enabled", str(payload.get("enabled"))), ("Operations", str(payload.get("compiled_operation_count"))), ("Discovery", payload.get("discovery_mode") or "-"), ("Origin", payload.get("origin_file") or "<unknown>")])
    blocks: List[RenderableType] = [summary]
    auth = payload.get("auth") or {}
    if auth:
        blocks.append(render_key_values(title="Auth", rows=[(k, stringify(v)) for k, v in auth.items()]))
    discovery_state = payload.get("discovery_state") or {}
    if discovery_state:
        blocks.append(render_key_values(title="Discovery State", rows=[(k, stringify(v)) for k, v in discovery_state.items()]))
    drift_state = payload.get("drift_state") or {}
    if drift_state:
        blocks.append(render_key_values(title="Drift State", rows=[(k, stringify(v)) for k, v in drift_state.items()]))
    operation_ids = payload.get("operation_ids") or []
    if operation_ids:
        blocks.append(render_single_column_table("Operation IDs", operation_ids))
    next_commands = payload.get("next_commands") or []
    if next_commands:
        blocks.append(render_single_column_table("Next Suggested Command", next_commands))
    return Group(*blocks)


def render_mount_details(payload: Dict[str, Any]) -> RenderableType:
    summary = render_key_values(title=f"Mount {payload['mount_id']}", rows=[("Command", " ".join(payload.get("command_path") or [])), ("Source", payload.get("source") or "-"), ("Provider", payload.get("provider_type") or "-"), ("Operation", payload.get("operation_id") or "-"), ("Risk", payload.get("risk") or "-"), ("Stable Name", payload.get("stable_name") or "-"), ("Origin", payload.get("origin_file") or "-")])
    blocks: List[RenderableType] = [summary]
    aliases = payload.get("aliases") or []
    if aliases:
        blocks.append(render_single_column_table("Aliases", [" ".join(item) for item in aliases]))
    if payload.get("summary"):
        blocks.append(Panel(Text(str(payload["summary"])), title="Summary", expand=False))
    if payload.get("description"):
        blocks.append(Panel(Text(str(payload["description"])), title="Description", expand=False))
    if payload.get("supported_surfaces"):
        blocks.append(render_single_column_table("Supported Surfaces", payload["supported_surfaces"]))
    params = payload.get("params") or {}
    if params:
        blocks.append(render_single_column_table("Parameters", [f"{name}: {stringify(item)}" for name, item in params.items()]))
    next_commands = payload.get("next_commands") or []
    if next_commands:
        blocks.append(render_single_column_table("Next Suggested Command", next_commands))
    return Group(*blocks)


def render_app_summary(payload: Dict[str, Any]) -> RenderableType:
    summary = render_key_values(title=f"App {payload['app']}", rows=[("Profile", str(payload.get("profile") or "-")), ("Sources", str(payload.get("source_count"))), ("Mounts", str(payload.get("mount_count"))), ("Plugins", str(payload.get("plugin_count"))), ("Hooks", str(payload.get("hook_count"))), ("Discovery Errors", str(payload.get("discovery_error_count")))])
    blocks: List[RenderableType] = [summary]
    if payload.get("config_files"):
        blocks.append(render_single_column_table("Config Files", payload["config_files"]))
    runtime_paths = payload.get("runtime_paths") or {}
    if runtime_paths:
        blocks.append(render_key_values(title="Runtime Paths", rows=[(k, str(v)) for k, v in runtime_paths.items()]))
    return Group(*blocks)


def render_action_result(payload: Dict[str, Any]) -> RenderableType:
    blocks: List[RenderableType] = [render_key_values(title=f"Action {payload['action']}", rows=[("Status", "ok"), ("Action", str(payload.get("action") or "-"))])]
    changed_rows = action_change_rows(payload)
    if changed_rows:
        blocks.append(render_key_values(title="What Changed", rows=changed_rows))
    where_rows = action_where_rows(payload)
    if where_rows:
        blocks.append(render_key_values(title="Where Written", rows=where_rows))
    if payload.get("profile") is not None and isinstance(payload["profile"], dict):
        profile = payload["profile"]
        if "configured" in profile and "source_count" in profile:
            blocks.append(render_auth_profile(profile))
        else:
            blocks.append(Panel(JSON.from_data(profile, ensure_ascii=False, indent=2), title="Profile", expand=False))
    if payload.get("warnings"):
        blocks.append(render_single_column_table("Warnings", payload["warnings"]))
    next_commands = list(payload.get("next_commands") or [])
    if payload.get("next_command"):
        next_commands.insert(0, payload["next_command"])
    if next_commands:
        blocks.append(render_single_column_table("Next Suggested Command", next_commands))
    if payload.get("config") is not None:
        blocks.append(Panel(JSON.from_data(payload["config"], ensure_ascii=False, indent=2), title="Config", expand=False))
    if payload.get("compiled") is not None:
        blocks.append(Panel(JSON.from_data(payload["compiled"], ensure_ascii=False, indent=2), title="Compiled", expand=False))
    return Group(*blocks)


def render_surface_result(payload: Dict[str, Any]) -> RenderableType:
    lines = [f"URL: {payload.get('base_url') or '-'}"]
    if payload.get("browser_url"):
        lines.append(f"Open: {payload['browser_url']}")
    if payload.get("ui_enabled") is not None:
        lines.append(f"UI Enabled: {payload.get('ui_enabled')}")
    if payload.get("ui_dir"):
        lines.append(f"UI Dir: {payload['ui_dir']}")
    if payload.get("tools_count") is not None:
        lines.append(f"Tools: {payload['tools_count']}")
    blocks: List[RenderableType] = [Panel(render_wrapped_text("\n".join(lines)), title=f"Surface {payload.get('surface') or '-'}", expand=False)]
    if payload.get("next_command"):
        blocks.append(render_single_column_table("Next", [payload["next_command"]]))
    return Group(*blocks)


def render_completion_bootstrap(payload: Dict[str, Any]) -> RenderableType:
    rows = [("Shell", str(payload.get("shell") or "-"))]
    if payload.get("message"):
        rows.append(("Message", str(payload["message"])))
    blocks: List[RenderableType] = [render_key_values(title=f"Completion Bootstrap ({payload.get('shell') or '-'})", rows=rows)]
    if payload.get("copy_command"):
        blocks.append(render_single_column_table("Copy Command", [payload["copy_command"]]))
    if payload.get("command_preview"):
        blocks.append(Panel(render_wrapped_text(payload["command_preview"]), title="Command Preview", expand=False))
    return Group(*blocks)


def action_change_rows(payload: Dict[str, Any]) -> List[tuple[str, str]]:
    rows: List[tuple[str, str]] = []
    for key in ("source", "source_name", "provider_type", "mount_id", "operation_id", "reconcile_action", "removed_mounts", "remaining_count", "mounts_created", "shell", "base_url", "tools_count"):
        if payload.get(key) is not None:
            rows.append((key.replace("_", " ").title(), stringify(payload[key])))
    if payload.get("alias") is not None:
        rows.append(("Alias", stringify(payload["alias"])))
    if payload.get("message") and payload.get("action") in {"completion_install", "completion_bootstrap"}:
        rows.append(("Message", str(payload["message"])))
    return rows


def action_where_rows(payload: Dict[str, Any]) -> List[tuple[str, str]]:
    rows: List[tuple[str, str]] = []
    for key in ("file", "completion_script", "servers_file", "ui_dir", "browser_url"):
        if payload.get(key):
            rows.append((key.replace("_", " ").title(), stringify(payload[key])))
    if payload.get("created_file") is not None:
        rows.append(("Created File", str(payload["created_file"])))
    return rows


def render_doctor(payload: Dict[str, Any]) -> RenderableType:
    compatibility = payload.get("compatibility") or {}
    auth = payload.get("auth") or {}
    reliability = payload.get("reliability") or {}
    summary = render_key_values(title="Doctor", rows=[("Config Files", str(len(payload.get("config_paths") or []))), ("Checks", str(len(payload.get("checks") or []))), ("Conflicts", str(len(payload.get("conflicts") or []))), ("Discovery Errors", str(len(payload.get("discovery_errors") or {}))), ("Plugin Conflicts", str(len(payload.get("plugin_provider_conflicts") or []))), ("Compatibility", "enabled" if compatibility else "not requested"), ("Auth Validation", "enabled" if auth else "not requested"), ("Reliability Budgets", str(reliability.get("configured_budget_count", 0)))])
    checks = payload.get("checks") or []
    check_table = Table(title="Health Checks", box=box.SIMPLE_HEAVY)
    check_table.add_column("Source", style="cyan", no_wrap=True)
    check_table.add_column("Provider", style="magenta", no_wrap=True)
    check_table.add_column("OK", no_wrap=True)
    check_table.add_column("Provider OK", no_wrap=True)
    check_table.add_column("Operations", justify="right")
    for item in checks:
        check_table.add_row(item.get("source") or "-", item.get("provider_type") or "-", str(item.get("ok")), str(item.get("provider_ok")), str(item.get("operation_count")))
    blocks: List[RenderableType] = [summary, check_table]
    conflicts = payload.get("conflicts") or []
    if conflicts:
        blocks.append(render_single_column_table("Command Conflicts", [compact_json(item) for item in conflicts]))
    discovery_errors = payload.get("discovery_errors") or {}
    if discovery_errors:
        blocks.append(render_key_values(title="Discovery Errors", rows=[(key, str(value)) for key, value in discovery_errors.items()]))
    runtime_paths = payload.get("runtime_paths") or {}
    if runtime_paths:
        blocks.append(render_key_values(title="Runtime Paths", rows=[(key, str(value)) for key, value in runtime_paths.items()]))
    if compatibility:
        blocks.append(render_compatibility_report(compatibility))
    if auth:
        blocks.append(render_auth_validation(auth))
    if reliability:
        blocks.append(render_reliability_status(reliability))
    return Group(*blocks)


def render_reliability_status(payload: Dict[str, Any]) -> RenderableType:
    defaults = payload.get("defaults") or {}
    rows = [("Configured Budgets", str(payload.get("configured_budget_count", 0))), ("Timeout", stringify(defaults.get("timeout_seconds"))), ("Retry Attempts", stringify((defaults.get("retry") or {}).get("max_attempts"))), ("Global Concurrency", stringify((defaults.get("concurrency") or {}).get("max_inflight_global")))]
    blocks: List[RenderableType] = [render_key_values(title="Reliability", rows=rows)]
    if payload.get("configured_budgets"):
        blocks.append(Panel(render_wrapped_json(payload["configured_budgets"]), title="Budgets", expand=False))
    if payload.get("status"):
        blocks.append(Panel(render_wrapped_json(payload["status"]), title="Runtime Status", expand=False))
    return Group(*blocks)


def render_compatibility_report(payload: Dict[str, Any]) -> RenderableType:
    rows = [("OK", str(payload.get("ok"))), ("Issue Count", str(len(payload.get("issues") or [])))]
    blocks: List[RenderableType] = [render_key_values(title="Compatibility", rows=rows)]
    issues = payload.get("issues") or []
    if issues:
        blocks.append(render_issue_table("Issues", issues, style="yellow"))
    return Group(*blocks)


def render_run_detail(payload: Dict[str, Any]) -> RenderableType:
    rows = [("Mode", payload.get("mode") or "-"), ("OK", str(payload.get("ok"))), ("Exit Code", stringify(payload.get("exit_code"))), ("Mount", payload.get("mount_id") or "-"), ("Source", payload.get("source") or "-"), ("Trace ID", payload.get("trace_id") or "-")]
    if payload.get("error_type") or payload.get("error_code"):
        rows.append(("Error", f"{payload.get('error_type') or '-'} / {payload.get('error_code') or '-'}"))
    blocks: List[RenderableType] = [render_key_values(title=f"Run {payload['run_id']}", rows=rows)]
    if payload.get("summary"):
        blocks.append(Panel(render_wrapped_text(payload["summary"]), title="Summary", expand=False))
    if payload.get("metadata") is not None:
        blocks.append(Panel(render_wrapped_json(payload["metadata"]), title="Metadata", expand=False))
    return Group(*blocks)


def render_auth_profile(payload: Dict[str, Any]) -> RenderableType:
    rows = [("State", payload.get("state") or "-"), ("Configured", str(payload.get("configured"))), ("Sources", str(payload.get("source_count")))]
    blocks: List[RenderableType] = [render_key_values(title=f"Auth {payload['name']}", rows=rows)]
    source_names = payload.get("source_names") or []
    if source_names:
        blocks.append(render_single_column_table("Sources", source_names))
    if payload.get("status"):
        blocks.append(render_key_values(title="Status", rows=[(k, stringify(v)) for k, v in payload["status"].items()]))
    next_commands = payload.get("next_commands") or []
    if next_commands:
        blocks.append(render_single_column_table("Next Suggested Command", next_commands))
    return Group(*blocks)


def render_secret_detail(payload: Dict[str, Any]) -> RenderableType:
    rows = [("Provider", payload.get("provider") or "-"), ("State", payload.get("state") or "-"), ("Value", "present" if payload.get("value_present") else "missing")]
    blocks: List[RenderableType] = [render_key_values(title=f"Secret {payload['name']}", rows=rows)]
    metadata = payload.get("metadata") or {}
    if metadata:
        blocks.append(render_key_values(title="Metadata", rows=[(k, stringify(v)) for k, v in metadata.items()]))
    next_commands = payload.get("next_commands") or []
    if next_commands:
        blocks.append(render_single_column_table("Next Suggested Command", next_commands))
    return Group(*blocks)


def render_auth_validation(payload: Dict[str, Any]) -> RenderableType:
    rows = [("OK", str(payload.get("ok"))), ("Valid", f"{payload.get('valid_count')}/{payload.get('total_count')}")]
    table = Table(title="Profiles", box=box.SIMPLE_HEAVY)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Valid", no_wrap=True)
    table.add_column("Issues")
    table.add_column("Actions")
    for name, item in sorted((payload.get("profiles") or {}).items()):
        issues = ",".join(issue.get("code", "-") for issue in item.get("issues") or []) or "-"
        actions = ",".join(action.get("action", "-") for action in item.get("actions") or []) or "-"
        table.add_row(name, item.get("state") or "-", str(item.get("valid")), issues, actions)
    return Group(render_key_values(title="Auth Validation", rows=rows), table)


def render_auth_validation_detail(payload: Dict[str, Any]) -> RenderableType:
    rows = [("Valid", str(payload.get("valid"))), ("State", payload.get("state") or "-")]
    blocks: List[RenderableType] = [render_key_values(title=f"Auth Check {payload['auth_profile']}", rows=rows)]
    if payload.get("issues"):
        blocks.append(render_issue_table("Issues", payload["issues"], style="yellow"))
    if payload.get("actions"):
        blocks.append(render_single_column_table("Actions", [f"{item.get('action')}: {item.get('command') or item.get('message') or '-'}" for item in payload["actions"]]))
    if payload.get("status"):
        blocks.append(render_key_values(title="Status", rows=[(key, stringify(value)) for key, value in payload["status"].items()]))
    return Group(*blocks)


def stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
