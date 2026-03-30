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
        "reliability": {},
    }

    output = render_payload(payload, "text")

    assert "Doctor" in output
    assert "Health Checks" in output
    assert "demo_cli" in output
    assert "Runtime Paths" in output


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
