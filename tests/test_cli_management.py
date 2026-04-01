import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml
from click.testing import CliRunner
import click

import cts.cli.root as root_module
from cts.cli.dynamic import _mount_short_help
from cts.cli.root import main
from cts.providers import mcp_cli


def _load_trailing_json(output: str) -> dict:
    start = output.rfind("\n{")
    if start == -1:
        start = output.find("{")
    else:
        start += 1
    return json.loads(output[start:])


def test_root_help_only_exposes_manage_for_admin_commands():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "manage  CTS administration and maintenance commands." in result.output
    assert "source      Source registry operations." not in result.output
    assert "auth        Authentication status commands." not in result.output
    assert "invoke      Invoke a mounted capability with validated input." not in result.output


def test_minimal_build_does_not_emit_bootstrap_log_events(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  log_dir: {tmp_path / "logs"}
  state_dir: {tmp_path / "state"}
sources: {{}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    from cts.app import build_app
    from cts.execution.logging import list_app_events

    app = build_app(str(config_path), compile_mode="minimal", load_drift_governance=False)

    assert list_app_events(app, limit=10) == []


def test_manage_source_help_shows_subcommand_descriptions():
    runner = CliRunner()
    result = runner.invoke(main, ["manage", "source", "--help"])

    assert result.exit_code == 0
    assert "add                Register a source in the config." in result.output
    assert "import-completion  Import shell completion data into a source manifest." in result.output
    assert "import-help        Import CLI help output into a source manifest." in result.output
    assert "import-manpage     Import man page content into a source manifest." in result.output
    assert "import-schema      Import JSON schema data into a source manifest." in result.output
    assert "list               List registered sources." in result.output
    assert "remove             Remove a source from the config." in result.output
    assert "show               Show details for a source." in result.output
    assert "test               Run health checks for a source." in result.output


def test_all_builtin_commands_have_short_descriptions():
    missing: list[str] = []

    def walk(group: click.MultiCommand, prefix: tuple[str, ...] = ()) -> None:
        for name, command in group.commands.items():
            path = prefix + (name,)
            short = command.get_short_help_str(limit=1000).strip()
            if not short:
                missing.append(" ".join(path))
            if isinstance(command, click.MultiCommand):
                walk(command, path)

    walk(main)
    assert missing == []


def test_source_add_creates_default_root_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Use explicit config path to avoid writing to user's home directory
        config_path = Path("cts.yaml")
        
        result = runner.invoke(
            main,
            ["--config", str(config_path), "manage", "source", "add", "http", "jira", "--base-url", "https://jira.example.com", "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["created_file"] is True
        assert str(config_path) in payload["file"]

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert raw["sources"]["jira"]["type"] == "http"
        assert raw["sources"]["jira"]["base_url"] == "https://jira.example.com"


def test_mount_add_and_alias_add_enable_dynamic_command():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")

        source_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "source",
                "add",
                "http",
                "jira",
                "--base-url",
                "https://jira.example.com",
                "--format",
                "json",
            ],
        )
        assert source_result.exit_code == 0

        mount_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "mount",
                "add",
                "jira",
                "get_issue",
                "--id",
                "jira-get-issue",
                "--path",
                "ops jira issue get",
                "--summary",
                "Get issue",
                "--param",
                "key:string",
                "--required",
                "key",
                "--format",
                "json",
            ],
        )
        assert mount_result.exit_code == 0
        mount_payload = json.loads(mount_result.output)
        assert mount_payload["compiled"]["command_path"] == ["ops", "jira", "issue", "get"]

        alias_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "alias",
                "add",
                "issue get",
                "ops jira issue get",
                "--format",
                "json",
            ],
        )
        assert alias_result.exit_code == 0

        help_result = runner.invoke(main, ["--config", str(config_path), "issue", "get", "--help"])
        assert help_result.exit_code == 0
        assert "Stable mount id  jira-get-issue" in help_result.output

        mount_show = runner.invoke(
            main,
            ["--config", str(config_path), "manage", "mount", "show", "jira-get-issue", "--format", "json"],
        )
        assert mount_show.exit_code == 0
        mount_show_payload = json.loads(mount_show.output)
        assert ["issue", "get"] in mount_show_payload["aliases"]


def test_import_mcp_apply_persists_source_and_mounts(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"

    def fake_bridge(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        assert command == "list-primitives"
        return {
            "ok": True,
            "server": "demo-server",
            "transport_type": "sse",
            "primitives": [
                {
                    "primitive_type": "tool",
                    "name": "query_train",
                    "description": "Query train tickets",
                    "input_schema": {
                        "type": "object",
                        "properties": {"from": {"type": "string"}},
                    },
                }
            ],
        }

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "mcp",
            "cn12306",
            "--server-config",
            '{"type":"sse","url":"https://example.com/sse"}',
            "--apply",
            "--format",
            "json",
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["tools_count"] == 1
    assert payload["mounts_created"] == 1

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["sources"]["cn12306"]["type"] == "mcp"
    assert raw["sources"]["cn12306"]["config_file"] == str(config_path.parent / "servers.json")
    assert raw["sources"]["cn12306"]["imported_cli_groups"] == [
        {
            "path": ["cn12306"],
            "summary": "MCP tools for 'cn12306' from 'cn12306-server'",
            "description": "Tools imported from MCP source 'cn12306' using server 'cn12306-server'.",
        }
    ]
    assert raw["mounts"][0]["id"] == "cn12306-query_train"
    assert raw["mounts"][0]["command"]["path"] == ["cn12306", "query_train"]

    help_result = runner.invoke(main, ["--config", str(config_path), "cn12306", "--help"])
    assert help_result.exit_code == 0
    assert "Tools imported from MCP source 'cn12306' using server 'cn12306-server'." in help_result.output
    assert "query_train  Query train tickets" in help_result.output
    assert "Query train tickets" in help_result.output


def test_import_mcp_apply_filters_mounts_with_include_and_exclude(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"

    def fake_bridge(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        assert command == "list-primitives"
        return {
            "ok": True,
            "server": "demo-server",
            "transport_type": "sse",
            "primitives": [
                {
                    "primitive_type": "tool",
                    "name": "query_train",
                    "description": "Query train tickets",
                    "input_schema": {"type": "object", "properties": {"from": {"type": "string"}}},
                },
                {
                    "primitive_type": "tool",
                    "name": "cancel_order",
                    "description": "Cancel order",
                    "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
                },
            ],
        }

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "mcp",
            "cn12306",
            "--server-config",
            '{"type":"sse","url":"https://example.com/sse"}',
            "--include",
            "query_*",
            "--exclude",
            "cancel_*",
            "--apply",
            "--format",
            "json",
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["tools_count"] == 2
    assert payload["mounts_created"] == 1

    app = build_app(str(config_path))
    assert "query_train" in app.source_operations["cn12306"]
    assert "cancel_order" in app.source_operations["cn12306"]
    assert app.catalog.find_by_path(["cn12306", "query_train"]) is not None
    assert app.catalog.find_by_path(["cn12306", "cancel_order"]) is None


def test_mount_short_help_prefers_description_when_summary_is_command_label():
    mount = SimpleNamespace(
        summary="query_train",
        description="Query train tickets",
        command_path=["cn12306", "query_train"],
        operation=SimpleNamespace(id="query_train", title="query_train", description="Query train tickets"),
    )

    assert _mount_short_help(mount, help_content={"summary": "query_train"}) == "Query train tickets"


def test_mount_short_help_keeps_meaningful_summary():
    mount = SimpleNamespace(
        summary="Train Search",
        description="Query train tickets",
        command_path=["cn12306", "query_train"],
        operation=SimpleNamespace(id="query_train", title="query_train", description="Query train tickets"),
    )

    assert _mount_short_help(mount, help_content={"summary": "Train Search"}) == "Train Search"


def test_import_shell_apply_persists_source_and_mount_and_executes(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "shell",
            "hello",
            "--exec",
            "echo Hello cts!",
            "--apply",
            "--format",
            "json",
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "import_shell_apply"
    assert payload["mount_id"] == "hello"
    assert payload["command_path"] == ["hello"]

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["sources"]["hello"]["type"] == "shell"
    assert raw["sources"]["hello"]["operations"]["run"]["provider_config"]["argv_template"] == [
        "/bin/sh",
        "-c",
        "echo Hello cts!",
    ]
    assert raw["mounts"][0]["id"] == "hello"
    assert raw["mounts"][0]["command"]["path"] == ["hello"]

    run_result = runner.invoke(main, ["--config", str(config_path), "hello"])
    assert run_result.exit_code == 0
    assert "Hello cts!" in run_result.output


def test_import_shell_apply_supports_under_prefix(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "shell",
            "hello",
            "--exec",
            "echo Hello cts!",
            "--under",
            "tools",
            "--apply",
            "--format",
            "json",
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command_path"] == ["tools", "hello"]

    run_result = runner.invoke(main, ["--config", str(config_path), "tools", "hello"])
    assert run_result.exit_code == 0
    assert "Hello cts!" in run_result.output


def test_import_shell_apply_supports_script_file(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    script_path = tmp_path / "hello.sh"
    script_path.write_text("echo Hello from file!\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "shell",
            "hello-file",
            "--script-file",
            str(script_path),
            "--apply",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "import_shell_apply"
    assert payload["script_file"] == str(script_path.resolve())
    assert payload["exec"] is None

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["sources"]["hello-file"]["operations"]["run"]["provider_config"]["argv_template"] == [
        "/bin/sh",
        str(script_path.resolve()),
    ]

    run_result = runner.invoke(main, ["--config", str(config_path), "hello-file"])
    assert run_result.exit_code == 0
    assert "Hello from file!" in run_result.output


def test_import_shell_requires_exactly_one_source(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    script_path = tmp_path / "hello.sh"
    script_path.write_text("echo Hello from file!\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "shell",
            "hello",
            "--exec",
            "echo Hello cts!",
            "--script-file",
            str(script_path),
            "--apply",
            "--format",
            "json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "provider_error"
    assert "mutually exclusive" in payload["error"]["message"]


def test_import_mcp_apply_surfaces_discovery_error(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"

    def fake_bridge(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        raise mcp_cli.ProviderError("bridge missing dependency")

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "mcp",
            "cn12306",
            "--server-config",
            '{"type":"sse","url":"https://example.com/sse"}',
            "--apply",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["tools_import_error"] == "MCP discovery failed for source 'cn12306': bridge missing dependency"
    assert payload["discovery"]["ok"] is False
    assert payload["discovery_report_path"]


def test_import_mcp_apply_updates_progress_for_each_mount(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"
    captured = {}

    class RecordingProgress:
        def __init__(self, output_format, title, steps):
            captured["title"] = title
            captured["steps"] = list(steps)
            captured["advanced"] = []
            captured["updated"] = []
            self.index = 0

        def __enter__(self):
            return self

        def advance(self, label=None):
            self.index += 1
            captured["advanced"].append(label)

        def update_current(self, label):
            captured["updated"].append(label)

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_bridge(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        assert command == "list-primitives"
        return {
            "ok": True,
            "server": "demo-server",
            "transport_type": "sse",
            "primitives": [
                {"primitive_type": "tool", "name": "query_train", "description": "Query train tickets"},
                {"primitive_type": "tool", "name": "refund_ticket", "description": "Refund ticket"},
            ],
        }

    monkeypatch.setattr(root_module, "_ProgressSteps", RecordingProgress)
    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "mcp",
            "cn12306",
            "--server-config",
            '{"type":"sse","url":"https://example.com/sse"}',
            "--apply",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["mounts_created"] == 2
    assert captured["title"] == "Importing MCP source 'cn12306'"
    assert captured["steps"] == [
        "Prepare import plan",
        "Writing server config",
        "Compiling source config",
        "Discovering tools",
        "Creating mounts",
    ]
    assert captured["advanced"] == [
        "Preparing import plan",
        "Writing server config",
        "Compiling source config",
        "Discovering tools",
        "Creating mounts",
    ]
    assert captured["updated"] == [
        "Discovering tools (syncing source 'cn12306')",
        "Discovering tools (2 discovered)",
        "Creating mounts (1/2: query_train)",
        "Creating mounts (2/2: refund_ticket)",
    ]
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    mounts = [item for item in raw["mounts"] if item["source"] == "cn12306"]
    assert {item["id"] for item in mounts} == {"cn12306-query_train", "cn12306-refund_ticket"}


def test_import_mcp_default_servers_file_uses_default_config_dir(monkeypatch):
    def fake_bridge(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        assert command == "list-primitives"
        return {
            "ok": True,
            "server": "demo-server",
            "transport_type": "sse",
            "primitives": [],
        }

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge)

    runner = CliRunner()
    with runner.isolated_filesystem():
        home_dir = Path.cwd() / "home"
        home_dir.mkdir()

        result = runner.invoke(
            main,
            [
                "import",
                "mcp",
                "cn12306",
                "--server-config",
                '{"type":"sse","url":"https://example.com/sse"}',
                "--apply",
                "--format",
                "json",
            ],
            env={"HOME": str(home_dir)},
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        config_path = home_dir / ".cts" / "config.yaml"
        servers_path = home_dir / ".cts" / "servers.json"

        assert payload["file"] == str(config_path)
        assert payload["servers_file"] == str(servers_path)
        assert config_path.exists()
        assert servers_path.exists()


def test_source_add_and_mount_add_can_target_loaded_split_files():
    runner = CliRunner()
    with runner.isolated_filesystem():
        root_config = Path("cts.yaml")
        sources_file = Path("sources.yaml")
        mounts_file = Path("mounts.yaml")

        root_config.write_text("imports:\n  - sources.yaml\n  - mounts.yaml\n", encoding="utf-8")
        sources_file.write_text("sources: {}\n", encoding="utf-8")
        mounts_file.write_text("mounts: []\n", encoding="utf-8")

        source_result = runner.invoke(
            main,
            [
                "--config",
                str(root_config),
                "manage", "source",
                "add",
                "http",
                "jira",
                "--base-url",
                "https://jira.example.com",
                "--file",
                str(sources_file),
                "--format",
                "json",
            ],
        )
        assert source_result.exit_code == 0

        mount_result = runner.invoke(
            main,
            [
                "--config",
                str(root_config),
                "manage", "mount",
                "add",
                "jira",
                "get_issue",
                "--id",
                "jira-get-issue",
                "--path",
                "ops jira issue get",
                "--file",
                str(mounts_file),
                "--format",
                "json",
            ],
        )
        assert mount_result.exit_code == 0
        assert "jira:" in sources_file.read_text(encoding="utf-8")
        assert "jira-get-issue" in mounts_file.read_text(encoding="utf-8")


def test_completion_script_outputs_shell_source():
    runner = CliRunner()
    result = runner.invoke(main, ["manage", "completion", "script", "--shell", "zsh"])

    assert result.exit_code == 0
    assert "_CTS_COMPLETE" in result.output


def test_doctor_includes_reliability_status():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        config_path.write_text(
            """
version: 1
sources: {}
reliability:
  defaults:
    timeout_seconds: 15
  budgets:
    demo:
      requests_per_minute: 60
""".strip()
            + "\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            ["--config", str(config_path), "manage", "doctor", "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "reliability" in payload
        assert payload["reliability"]["defaults"]["timeout_seconds"] == 15
        assert payload["reliability"]["configured_budget_count"] == 1
        assert "status" in payload["reliability"]


def test_source_remove_deletes_source():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        
        # Add a source
        add_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "source",
                "add",
                "http",
                "test-api",
                "--base-url",
                "https://api.example.com",
                "--format",
                "json",
            ],
        )
        assert add_result.exit_code == 0
        
        # Verify source exists
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "test-api" in raw["sources"]
        
        # Remove the source
        remove_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "source",
                "remove",
                "test-api",
                "--format",
                "json",
            ],
        )
        assert remove_result.exit_code == 0
        payload = json.loads(remove_result.output)
        assert payload["ok"] is True
        assert payload["action"] == "source_remove"
        assert payload["source_name"] == "test-api"
        
        # Verify source is removed
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "test-api" not in raw.get("sources", {})


def test_source_remove_fails_if_not_found():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")
        
        result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "source",
                "remove",
                "nonexistent",
                "--format",
                "json",
            ],
        )
        assert result.exit_code != 0


def test_source_remove_with_dependent_mounts():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        
        # Add source
        runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "source",
                "add",
                "http",
                "test-api",
                "--base-url",
                "https://api.example.com",
            ],
        )
        
        # Add mount
        runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "mount",
                "add",
                "test-api",
                "get_item",
                "--id",
                "test-api-get-item",
            ],
        )
        
        # Try to remove source without --force (should fail)
        remove_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "source",
                "remove",
                "test-api",
                "--format",
                "json",
            ],
        )
        assert remove_result.exit_code != 0
        
        # Remove with --force
        force_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "source",
                "remove",
                "test-api",
                "--force",
                "--format",
                "json",
            ],
        )
        assert force_result.exit_code == 0
        payload = json.loads(force_result.output)
        assert payload["ok"] is True
        assert len(payload["removed_mounts"]) == 1


def test_mount_remove_deletes_mount():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        
        # Add source and mount
        runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "source",
                "add",
                "http",
                "test-api",
                "--base-url",
                "https://api.example.com",
            ],
        )
        runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "mount",
                "add",
                "test-api",
                "get_item",
                "--id",
                "test-mount",
            ],
        )
        
        # Verify mount exists
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        mounts = raw.get("mounts", [])
        assert any(m.get("id") == "test-mount" for m in mounts)
        
        # Remove mount
        remove_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "mount",
                "remove",
                "test-mount",
                "--format",
                "json",
            ],
        )
        assert remove_result.exit_code == 0
        payload = json.loads(remove_result.output)
        assert payload["ok"] is True
        assert payload["action"] == "mount_remove"
        assert payload["mount_id"] == "test-mount"
        
        # Verify mount is removed
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        mounts = raw.get("mounts", [])
        assert not any(m.get("id") == "test-mount" for m in mounts)


def test_mount_import_dry_run():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        
        # Add source with operations
        config_content = """
version: 1
sources:
  test-api:
    type: http
    base_url: https://api.example.com
    operations:
      get_item:
        title: Get Item
        risk: read
        provider_config:
          method: GET
          path: /items/{id}
      list_items:
        title: List Items
        risk: read
        provider_config:
          method: GET
          path: /items
      create_item:
        title: Create Item
        risk: write
        provider_config:
          method: POST
          path: /items
"""
        config_path.write_text(config_content, encoding="utf-8")
        
        # Dry run import
        result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "mount",
                "import",
                "test-api",
                "--dry-run",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["action"] == "mount_import_dry_run"
        assert payload["total_operations"] == 3
        assert payload["mounts_to_create"] == 3


def test_mount_import_with_filter():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        
        config_content = """
version: 1
sources:
  test-api:
    type: http
    base_url: https://api.example.com
    operations:
      get_item:
        title: Get Item
        risk: read
        provider_config:
          method: GET
          path: /items/{id}
      list_items:
        title: List Items
        risk: read
        provider_config:
          method: GET
          path: /items
"""
        config_path.write_text(config_content, encoding="utf-8")
        
        # Import with filter
        result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "manage", "mount",
                "import",
                "test-api",
                "--filter",
                "get_*",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["filtered_operations"] == 1
        assert payload["mounts_created"] == 1
        assert payload["mount_ids"] == ["test-api-get-item"]


def test_mount_import_uses_multistep_progress(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        """
version: 1
sources:
  test-api:
    type: http
    base_url: https://api.example.com
    operations:
      get_item:
        title: Get Item
        risk: read
        provider_config:
          method: GET
          path: /items/{id}
      list_items:
        title: List Items
        risk: read
        provider_config:
          method: GET
          path: /items
""",
        encoding="utf-8",
    )
    captured = {}

    class RecordingProgress:
        def __init__(self, output_format, title, steps):
            captured["title"] = title
            captured["steps"] = list(steps)
            captured["advanced"] = []
            captured["updated"] = []

        def __enter__(self):
            return self

        def advance(self, label=None):
            captured["advanced"].append(label)

        def update_current(self, label):
            captured["updated"].append(label)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(root_module, "_ProgressSteps", RecordingProgress)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage", "mount",
            "import",
            "test-api",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert captured["title"] == "Importing mounts from 'test-api'"
    assert captured["steps"] == ["Prepare mounts", "Compile config"]
    assert captured["advanced"] == [
        "Preparing 2 operation(s)",
        "Creating 2 mount(s)",
    ]
    assert captured["updated"] == [
        "Preparing mounts (1/2: get_item)",
        "Preparing mounts (2/2: list_items)",
    ]


CLI_IMPORT_SCRIPT = """
import json
import click


@click.group()
def cli():
    pass


@cli.command()
@click.option("--name", required=True, help="User name")
def greet(name):
    click.echo(json.dumps({"name": name}))


if __name__ == "__main__":
    cli()
"""


def test_import_cli_preview_uses_inline_operation_and_auto_mount():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        script_path = Path("demo_cli.py")
        config_path.write_text("version: 1\n", encoding="utf-8")
        script_path.write_text(CLI_IMPORT_SCRIPT, encoding="utf-8")

        result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "import",
                "cli",
                "demo_cli",
                sys.executable,
                str(script_path),
                "greet",
                "--from",
                "help",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["action"] == "import_cli_preview"
        assert payload["source"]["stores_operation_inline"] is True
        assert payload["source"]["operation_id"] == "greet"
        assert payload["mount"]["id"] == "demo-cli-greet"
        assert payload["mount"]["command"]["path"] == ["demo", "cli", "greet"]


def test_import_cli_apply_writes_source_operation_and_mount_without_manifest():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        script_path = Path("demo_cli.py")
        config_path.write_text("version: 1\n", encoding="utf-8")
        script_path.write_text(CLI_IMPORT_SCRIPT, encoding="utf-8")

        result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "import",
                "cli",
                "demo_cli",
                sys.executable,
                str(script_path),
                "greet",
                "--from",
                "help",
                "--apply",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["action"] == "import_cli_apply"

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert raw["sources"]["demo_cli"]["operations"]["greet"]["provider_config"]["command_argv"][-1] == "greet"
        assert raw["mounts"][0]["id"] == "demo-cli-greet"
        assert raw["mounts"][0]["command"]["path"] == ["demo", "cli", "greet"]


def test_import_wizard_preview_guides_cli_import_flow():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        script_path = Path("demo_cli.py")
        config_path.write_text("version: 1\n", encoding="utf-8")
        script_path.write_text(CLI_IMPORT_SCRIPT, encoding="utf-8")

        result = runner.invoke(
            main,
            ["--config", str(config_path), "import", "wizard", "--format", "json"],
            input=f"cli\ndemo_cli\n{sys.executable} {script_path} greet\nhelp\ngreet\n\nread\njson\n\n\nn\n",
        )

        assert result.exit_code == 0
        payload = _load_trailing_json(result.output)
        assert payload["action"] == "import_cli_preview"
        assert payload["source"]["name"] == "demo_cli"
        assert payload["operation_id"] == "greet"


def test_import_wizard_preview_guides_mcp_import_flow():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        config_path.write_text("version: 1\n", encoding="utf-8")

        result = runner.invoke(
            main,
            ["--config", str(config_path), "import", "wizard", "--format", "json"],
            input='mcp\ncn12306\n{"type":"sse","url":"https://example.com/sse"}\n\n\ntravel rail\nn\n',
        )

        assert result.exit_code == 0
        payload = _load_trailing_json(result.output)
        assert payload["action"] == "import_mcp_preview"
        assert payload["source_name"] == "cn12306"
        assert payload["under"] == ["travel", "rail"]


def test_import_wizard_apply_supports_mcp(monkeypatch):
    def fake_bridge(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        assert command == "list-primitives"
        return {
            "ok": True,
            "server": "demo-server",
            "transport_type": "sse",
            "primitives": [
                {
                    "primitive_type": "tool",
                    "name": "query_train",
                    "description": "Query train tickets",
                    "input_schema": {
                        "type": "object",
                        "properties": {"from": {"type": "string"}},
                    },
                }
            ],
        }

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge)

    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        config_path.write_text("version: 1\n", encoding="utf-8")

        result = runner.invoke(
            main,
            ["--config", str(config_path), "import", "wizard", "--apply", "--format", "json"],
            input='mcp\ncn12306\n{"type":"sse","url":"https://example.com/sse"}\n\n\ntravel rail\n',
            env={"HOME": str(Path.cwd())},
        )

        assert result.exit_code == 0
        payload = _load_trailing_json(result.output)
        assert payload["action"] == "import_mcp_apply"
        assert payload["tools_count"] == 1
        assert payload["mounts_created"] == 1

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert raw["sources"]["cn12306"]["type"] == "mcp"
        assert raw["mounts"][0]["id"] == "cn12306-query_train"
        assert raw["mounts"][0]["command"]["path"] == ["travel", "rail", "query_train"]


def test_completion_install_zsh():
    runner = CliRunner()
    with runner.isolated_filesystem():
        import os
        os.environ["HOME"] = str(Path.cwd())
        
        result = runner.invoke(
            main,
            [
                "manage", "completion",
                "install",
                "--shell",
                "zsh",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["shell"] == "zsh"
        assert "completion_script" in payload


def test_completion_bootstrap_zsh():
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "manage", "completion",
            "bootstrap",
            "--shell",
            "zsh",
        ],
    )
    assert result.exit_code == 0
    # Should output completion-related content
    assert len(result.output) > 0


def test_completion_bootstrap_text_mode_is_user_friendly():
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "manage", "completion",
            "bootstrap",
            "--shell",
            "zsh",
            "--format",
            "text",
        ],
    )
    assert result.exit_code == 0
    assert "Completion Bootstrap (zsh)" in result.output
    assert "Copy Command" in result.output


def test_show_commands_default_to_text():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_path = Path("cts.yaml")
        config_path.write_text(
            """
version: 1
sources:
  demo:
    type: http
    base_url: https://api.example.com
    operations:
      ping:
        title: Ping
        provider_config:
          method: GET
          path: /ping
mounts:
  - id: demo-ping
    source: demo
    operation: ping
auth_profiles:
  demo-auth:
    type: bearer
secrets:
  demo_token:
    provider: env
    env: DEMO_TOKEN
""".strip()
            + "\n",
            encoding="utf-8",
        )

        source_result = runner.invoke(main, ["--config", str(config_path), "manage", "source", "show", "demo"])
        mount_result = runner.invoke(main, ["--config", str(config_path), "manage", "mount", "show", "demo-ping"])
        auth_result = runner.invoke(main, ["--config", str(config_path), "manage", "auth", "status"])
        secret_result = runner.invoke(main, ["--config", str(config_path), "manage", "secret", "show", "demo_token"])
        doctor_result = runner.invoke(main, ["--config", str(config_path), "manage", "doctor"])

        assert source_result.exit_code == 0
        assert "demo (http)" in source_result.output or "Source demo" in source_result.output
        assert "Next Suggested Command" in source_result.output
        assert mount_result.exit_code == 0
        assert "Mount demo-ping" in mount_result.output
        assert "Next Suggested Command" in mount_result.output
        assert auth_result.exit_code == 0
        assert "Auth Profiles" in auth_result.output
        detail_auth_result = runner.invoke(main, ["--config", str(config_path), "manage", "auth", "status", "demo-auth"])
        assert detail_auth_result.exit_code == 0
        assert "Next Suggested Command" in detail_auth_result.output
        assert secret_result.exit_code == 0
        assert "Secret demo_token" in secret_result.output
        assert "Next Suggested Command" in secret_result.output
        assert doctor_result.exit_code == 0
        assert "Doctor" in doctor_result.output
