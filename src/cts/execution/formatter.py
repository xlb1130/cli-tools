from __future__ import annotations

import json
import sys
from io import StringIO
from typing import Any, Dict

from cts.execution.formatter_cards import (
    is_execution_payload,
    render_action_result,
    render_app_summary,
    render_auth_profile,
    render_auth_validation,
    render_auth_validation_detail,
    render_completion_bootstrap,
    render_doctor,
    render_error,
    render_execution_result,
    render_items,
    render_key_values,
    render_lint,
    render_mount_details,
    render_mounts,
    render_run_detail,
    render_secret_detail,
    render_source_details,
    render_surface_result,
    stringify,
)

try:
    from rich.console import Console
    from rich.json import JSON
    from rich.text import Text

    HAS_RICH = True
except ModuleNotFoundError:
    Console = None
    JSON = None
    Text = None
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
                lines.extend(f"- {key}: {stringify(value)}" for key, value in payload["summary"].items())
            return "\n".join(lines)
        if items and isinstance(items[0], dict) and items[0].get("name") and items[0].get("provider") and "value_present" in items[0]:
            lines = ["Secrets"]
            lines.extend(
                f"- {item.get('name')} provider={item.get('provider')} state={item.get('state')} value={'present' if item.get('value_present') else 'missing'}"
                for item in items
            )
            if payload.get("summary"):
                lines.append("Summary")
                lines.extend(f"- {key}: {stringify(value)}" for key, value in payload["summary"].items())
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
            lines.append(f"discovery_state={stringify(discovery_state)}")
        drift_state = payload.get("drift_state") or {}
        if drift_state:
            lines.append(f"drift_state={stringify(drift_state)}")
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
                "discovery=" + str(payload["discovery"].get("ok")) + f" count={payload['discovery'].get('operation_count', 0)}"
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
        lines = [f"Auth Check {payload['auth_profile']}", f"- valid={payload.get('valid')}", f"- state={payload.get('state') or '-'}"]
        if payload.get("issues"):
            lines.append("Issues")
            lines.extend(f"- {item.get('code')}: {item.get('message')}" for item in payload["issues"])
        if payload.get("actions"):
            lines.append("Actions")
            lines.extend(f"- {item.get('action')}: {item.get('command') or item.get('message') or '-'}" for item in payload["actions"])
        if payload.get("status"):
            lines.append("Status")
            lines.extend(f"- {key}: {stringify(value)}" for key, value in payload["status"].items())
        return "\n".join(lines)

    if payload.get("name") and "configured" in payload and "source_count" in payload:
        lines = [f"Auth {payload['name']}", f"state={payload.get('state') or '-'} configured={payload.get('configured')} sources={payload.get('source_count')}"]
        source_names = payload.get("source_names") or []
        if source_names:
            lines.append("Sources")
            lines.extend(f"- {item}" for item in source_names)
        if payload.get("status"):
            lines.append("Status")
            lines.extend(f"- {key}: {stringify(value)}" for key, value in payload["status"].items())
        next_commands = payload.get("next_commands") or []
        if next_commands:
            lines.append("Next Suggested Command")
            lines.extend(f"- {item}" for item in next_commands)
        return "\n".join(lines)

    if payload.get("name") and payload.get("provider") and "value_present" in payload:
        lines = [f"Secret {payload['name']}", f"provider={payload.get('provider')} state={payload.get('state') or '-'} value={'present' if payload.get('value_present') else 'missing'}"]
        metadata = payload.get("metadata") or {}
        if metadata:
            lines.append("Metadata")
            lines.extend(f"- {key}: {stringify(value)}" for key, value in metadata.items())
        next_commands = payload.get("next_commands") or []
        if next_commands:
            lines.append("Next Suggested Command")
            lines.extend(f"- {item}" for item in next_commands)
        return "\n".join(lines)

    if payload.get("ok") is True and payload.get("action"):
        lines = [f"Action {payload.get('action')}"]
        return "\n".join(lines)

    if is_execution_payload(payload):
        lines = [
            f"Execution {payload.get('mount_id') or payload.get('stable_name') or '-'}",
            f"status={'ok' if payload.get('ok') else 'failed'} mode={payload.get('mode') or '-'}",
        ]
        return "\n".join(lines)

    if payload.get("mount_id") and payload.get("command_path"):
        lines = [
            f"Mount {payload['mount_id']}: {' '.join(payload['command_path'])}",
            f"source={payload.get('source')} provider={payload.get('provider_type')} risk={payload.get('risk')}",
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
        soft_wrap=True,
    )


def _payload_to_renderable(payload: Dict[str, Any]):
    if payload.get("ok") is False and "error" in payload:
        return render_error(payload["error"])
    if "checks" in payload and "runtime_paths" in payload:
        return render_doctor(payload)
    if "profiles" in payload and "valid_count" in payload and "total_count" in payload:
        return render_auth_validation(payload)
    if "mounts" in payload:
        return render_mounts(payload["mounts"], conflicts=payload.get("conflicts"))
    if "errors" in payload and "warnings" in payload:
        return render_lint(payload)
    if "items" in payload:
        return render_items(payload)
    if is_execution_payload(payload):
        return render_execution_result(payload)
    if payload.get("mount_id") and payload.get("command_path"):
        return render_mount_details(payload)
    if payload.get("name") and payload.get("compiled_operation_count") is not None:
        return render_source_details(payload)
    if payload.get("source") and payload.get("provider_type") and "operation_count" in payload:
        rows = [("Source", payload.get("source") or "-"), ("Provider", payload.get("provider_type") or "-"), ("OK", str(payload.get("ok"))), ("Operations", str(payload.get("operation_count")))]
        if payload.get("discovery"):
            discovery = payload["discovery"]
            rows.append(("Discovery", f"ok={discovery.get('ok')} count={discovery.get('operation_count', 0)}"))
        return render_key_values(title="Source Check", rows=rows)
    if payload.get("run_id") and payload.get("mode"):
        return render_run_detail(payload)
    if payload.get("name") and "configured" in payload and "source_count" in payload:
        return render_auth_profile(payload)
    if payload.get("name") and payload.get("provider") and "value_present" in payload:
        return render_secret_detail(payload)
    if "valid" in payload and payload.get("auth_profile"):
        return render_auth_validation_detail(payload)
    if payload.get("app") and "source_count" in payload and "mount_count" in payload:
        return render_app_summary(payload)
    if payload.get("surface") and payload.get("base_url"):
        return render_surface_result(payload)
    if payload.get("action") == "completion_bootstrap":
        return render_completion_bootstrap(payload)
    if payload.get("ok") is True and payload.get("action"):
        return render_action_result(payload)
    if payload.get("text"):
        return Text(str(payload["text"]))
    if payload.get("data") is not None:
        return JSON.from_data(payload["data"], ensure_ascii=False, indent=2)
    return JSON.from_data(payload, ensure_ascii=False, indent=2)
