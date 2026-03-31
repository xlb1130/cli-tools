from cts.execution.runtime import render_payload


def test_render_payload_formats_lint_as_table_text():
    payload = {
        "ok": False,
        "loaded_paths": ["cts.yaml"],
        "warnings": [{"code": "warn_code", "message": "warning text"}],
        "errors": [{"code": "error_code", "message": "error text"}],
    }

    output = render_payload(payload, "text")

    assert "Config lint: FAILED" in output
    assert "Loaded Files" in output
    assert "warn_code" in output
    assert "error_code" in output


def test_render_payload_formats_mount_list_as_table_text():
    payload = {
        "mounts": [
            {
                "mount_id": "demo-echo",
                "command_path": ["demo", "echo"],
                "provider_type": "cli",
            }
        ]
    }

    output = render_payload(payload, "text")

    assert "Mounts" in output
    assert "demo-echo" in output
    assert "demo echo" in output
    assert "cli" in output


def test_render_payload_formats_error_as_panel_text():
    payload = {
        "ok": False,
        "error": {
            "type": "config_error",
            "message": "Something went wrong",
            "suggestions": ["Check the config file"],
        },
    }

    output = render_payload(payload, "text")

    assert "Error [config_error]" in output
    assert "Something went wrong" in output
    assert "Check the config file" in output


def test_render_payload_formats_source_summary_list_as_table_text():
    payload = {
        "items": [
            {
                "name": "demo_cli",
                "type": "cli",
                "enabled": True,
                "discovery_mode": "manifest",
                "operation_count": 3,
                "auth_ref": "github",
                "origin_file": "/tmp/cts.yaml",
            }
        ]
    }

    output = render_payload(payload, "text")

    assert "Sources" in output
    assert "demo_cli" in output
    assert "manifest" in output
    assert "github" in output


def test_render_payload_formats_doctor_payload_as_summary_and_table():
    payload = {
        "config_paths": ["/tmp/cts.yaml"],
        "conflicts": [],
        "plugin_provider_conflicts": [],
        "discovery_errors": {},
        "checks": [
            {
                "source": "demo_cli",
                "provider_type": "cli",
                "provider_ok": True,
                "operation_count": 2,
                "ok": True,
            }
        ],
        "runtime_paths": {
            "app_log": "/tmp/app.jsonl",
            "history_db": "/tmp/history.db",
        },
        "reliability": {
            "configured_budget_count": 1,
            "defaults": {"timeout_seconds": 15},
            "configured_budgets": {"demo": {"requests_per_minute": 60}},
            "status": {"rate_limits": {"demo": {"tokens": 3}}},
        },
        "compatibility": {
            "ok": False,
            "error_count": 1,
            "warning_count": 0,
            "issues": [
                {
                    "level": "error",
                    "category": "cts_version",
                    "object_type": "cts",
                    "message": "CTS version mismatch",
                    "suggestion": "Upgrade CTS",
                }
            ],
        },
        "auth": {
            "ok": False,
            "valid_count": 0,
            "total_count": 1,
            "profiles": {
                "github": {
                    "valid": False,
                    "state": "login_required",
                    "issues": [{"code": "login_required", "message": "Login is required"}],
                    "actions": [{"action": "login", "command": "cts manage auth login github"}],
                }
            },
        },
    }

    output = render_payload(payload, "text")

    assert "Doctor" in output
    assert "Health Checks" in output
    assert "demo_cli" in output
    assert "Runtime Paths" in output
    assert "Reliability" in output
    assert "Compatibility" in output
    assert "Auth Validation" in output
    assert "CTS version mismatch" in output


def test_render_payload_formats_auth_inventory_with_summary():
    payload = {
        "items": [
            {
                "name": "github",
                "configured": True,
                "state": "active",
                "reason": "session_active",
                "source_count": 2,
            }
        ],
        "summary": {
            "profile_count": 1,
            "active_count": 1,
        },
    }

    output = render_payload(payload, "text")

    assert "Auth Profiles" in output
    assert "github" in output
    assert "active" in output
    assert "Summary" in output


def test_render_payload_formats_secret_inventory_with_summary():
    payload = {
        "items": [
            {
                "name": "github_token",
                "provider": "env",
                "state": "active",
                "reason": "env_value_available",
                "value_present": True,
            }
        ],
        "summary": {
            "secret_count": 1,
            "active_count": 1,
        },
    }

    output = render_payload(payload, "text")

    assert "Secrets" in output
    assert "github_token" in output
    assert "present" in output
    assert "Summary" in output


def test_render_payload_formats_auth_validation_summary():
    payload = {
        "ok": False,
        "valid_count": 0,
        "total_count": 1,
        "profiles": {
            "github": {
                "valid": False,
                "state": "login_required",
                "issues": [{"code": "login_required", "message": "Login is required"}],
                "actions": [{"action": "login", "command": "cts manage auth login github"}],
            }
        },
    }

    output = render_payload(payload, "text")

    assert "Auth Validation" in output
    assert "github" in output
    assert "login_required" in output
    assert "login" in output


def test_render_payload_formats_single_auth_validation_detail():
    payload = {
        "valid": False,
        "auth_profile": "github",
        "state": "login_required",
        "issues": [{"code": "login_required", "message": "Login is required"}],
        "actions": [{"action": "login", "command": "cts manage auth login github"}],
        "status": {"type": "bearer", "source": "session"},
    }

    output = render_payload(payload, "text")

    assert "Auth Check github" in output
    assert "Issues" in output
    assert "Actions" in output
    assert "cts manage auth login github" in output
    assert "Status" in output


def test_render_payload_formats_run_detail_with_summary_and_metadata():
    payload = {
        "run_id": "run-1",
        "mode": "invoke",
        "ok": False,
        "exit_code": 1,
        "mount_id": "demo-echo",
        "source": "demo_cli",
        "trace_id": "trace-1",
        "summary": "Invocation failed",
        "metadata": {"surface": "cli", "retryable": False},
        "error_type": "validation_error",
        "error_code": "invalid_input",
    }

    output = render_payload(payload, "text")

    assert "Run run-1" in output
    assert "validation_error" in output
    assert "invalid_input" in output
    assert "Summary" in output
    assert "Invocation failed" in output
    assert "Metadata" in output
    assert '"surface": "cli"' in output


def test_render_payload_formats_action_result_as_result_card():
    payload = {
        "ok": True,
        "action": "source_add",
        "source": "jira",
        "provider_type": "http",
        "file": "/tmp/cts.yaml",
        "created_file": True,
        "warnings": ["imported into new file"],
        "next_commands": ["cts manage source show jira", "cts manage source test jira"],
    }

    output = render_payload(payload, "text")

    assert "Action source_add" in output
    assert "What Changed" in output
    assert "Where Written" in output
    assert "Warnings" in output
    assert "Next Suggested Command" in output
    assert "cts manage source show jira" in output


def test_render_payload_formats_completion_bootstrap_text():
    payload = {
        "ok": True,
        "action": "completion_bootstrap",
        "shell": "zsh",
        "message": "Use this to enable zsh completion for the current shell session.",
        "copy_command": 'eval "$(cts manage completion bootstrap --shell zsh)"',
        "command_preview": "#compdef cts\n_arguments '*: :->args'",
    }

    output = render_payload(payload, "text")

    assert "Completion Bootstrap (zsh)" in output
    assert "Copy Command" in output
    assert 'eval "$(cts manage completion bootstrap --shell zsh)"' in output


def test_render_payload_formats_surface_card_text():
    payload = {
        "ok": True,
        "surface": "http",
        "base_url": "http://127.0.0.1:8787",
        "browser_url": "http://127.0.0.1:8787/api/app/summary",
        "ui_enabled": False,
        "next_command": "curl http://127.0.0.1:8787/api/app/summary",
    }

    output = render_payload(payload, "text")

    assert "Surface http" in output
    assert "URL: http://127.0.0.1:8787" in output
    assert "Next" in output
    assert "curl http://127.0.0.1:8787/api/app/summary" in output


def test_render_payload_formats_source_detail_with_next_commands():
    payload = {
        "name": "demo",
        "type": "http",
        "enabled": True,
        "compiled_operation_count": 2,
        "discovery_mode": "manifest",
        "origin_file": "/tmp/cts.yaml",
        "auth": {"state": "active", "required": True},
        "discovery_state": {"ok": True},
        "drift_state": {"status": "clean"},
        "operation_ids": ["ping", "list_items"],
        "next_commands": ["cts manage source test demo", "cts manage mount import demo --dry-run"],
    }

    output = render_payload(payload, "text")

    assert "Source demo (http)" in output
    assert "Operation IDs" in output or "ping" in output
    assert "Next Suggested Command" in output
    assert "cts manage source test demo" in output


def test_render_payload_formats_mount_detail_with_next_commands():
    payload = {
        "mount_id": "demo-ping",
        "command_path": ["demo", "ping"],
        "source": "demo",
        "provider_type": "http",
        "operation_id": "ping",
        "risk": "read",
        "stable_name": "demo_ping",
        "aliases": [["d", "ping"]],
        "next_commands": ["cts demo ping --help", "cts manage runs list --mount-id demo-ping"],
    }

    output = render_payload(payload, "text")

    assert "Mount demo-ping" in output
    assert "Aliases" in output
    assert "Next Suggested Command" in output
    assert "cts manage runs list --mount-id demo-ping" in output


def test_render_payload_formats_execution_result_with_duration_and_output():
    payload = {
        "ok": True,
        "mount_id": "demo-echo",
        "stable_name": "demo.echo",
        "source": "demo_cli",
        "provider_type": "cli",
        "operation_id": "echo_json",
        "mode": "invoke",
        "risk": "read",
        "summary": "Echo text",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "duration_ms": 24,
        "data": {"text": "hello", "upper": False},
        "metadata": {"argv": ["python3", "demo.py", "hello"]},
        "reliability": {"attempts": 1, "was_retried": False, "was_duplicate": False, "duration_ms": 24},
    }

    output = render_payload(payload, "text")

    assert "Execution demo-echo" in output
    assert "Duration" in output
    assert "24 ms" in output
    assert "Output" in output
    assert '"text": "hello"' in output
    assert "Reliability" in output
    assert "Metadata" in output


def test_render_payload_wraps_long_output_text_without_truncating():
    long_text = "prefix-" + ("x" * 180) + "-suffix"
    payload = {
        "ok": True,
        "mount_id": "demo-echo",
        "mode": "invoke",
        "provider_type": "cli",
        "source": "demo_cli",
        "operation_id": "echo_text",
        "text": long_text,
    }

    output = render_payload(payload, "text")
    normalized = output
    for marker in (" ", "\n", "│", "╭", "╮", "╰", "╯", "─"):
        normalized = normalized.replace(marker, "")

    assert "Output" in output
    assert long_text in normalized
