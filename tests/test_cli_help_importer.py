import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import click
from click.testing import CliRunner

import cts.cli.execution_runtime as execution_runtime
from cts.cli.command_registry import should_load_drift_governance
import cts.cli.root as root_module
from cts.app import build_app
from cts.cli.root import main
from cts.execution.help_compiler import build_click_params, extract_request_args


CLI_SCRIPT = """
import json
import click


@click.group()
def cli():
    pass


@cli.command()
@click.option("--name", required=True, help="User name")
@click.option("--count", type=int, default=1, show_default=True, help="Repeat count")
@click.option("--verbose", is_flag=True, help="Verbose output")
def greet(name, count, verbose):
    click.echo(json.dumps({"name": name, "count": count, "verbose": verbose}))


if __name__ == "__main__":
    cli()
"""


def test_source_import_help_generates_manifest_and_compiled_operation(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-manifest.yaml"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
sources:
  demo_cli:
    type: cli
    executable: {sys.executable}
    discovery:
      manifest: {manifest_path}
mounts:
  - id: demo
    source: demo_cli
    select:
      include: ["*"]
    command:
      under: [demo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage",
            "source",
            "import-help",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "source_import_help"
    assert payload["compiled_operation"]["id"] == "greet"
    assert payload["compiled_operation"]["input_schema"]["properties"]["name"]["type"] == "string"
    assert payload["compiled_operation"]["input_schema"]["properties"]["count"]["type"] == "integer"
    assert payload["compiled_operation"]["input_schema"]["properties"]["verbose"]["type"] == "boolean"

    raw_manifest = manifest_path.read_text(encoding="utf-8")
    assert "command_argv:" in raw_manifest
    assert "option_bindings:" in raw_manifest
    assert "strategy: cli_help" in raw_manifest

    app = build_app(str(config_path))
    mount = app.catalog.find_by_id("demo.greet")
    assert mount is not None
    assert mount.command_path == ["demo", "greet"]


def test_imported_cli_manifest_supports_dynamic_command_dry_run(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-manifest.yaml"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
sources:
  demo_cli:
    type: cli
    executable: {sys.executable}
    discovery:
      manifest: {manifest_path}
mounts:
  - id: demo
    source: demo_cli
    select:
      include: ["*"]
    command:
      under: [demo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    import_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage",
            "source",
            "import-help",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--format",
            "json",
        ],
    )
    assert import_result.exit_code == 0

    help_result = runner.invoke(main, ["--config", str(config_path), "demo", "greet", "--help"])
    assert help_result.exit_code == 0
    assert "Schema provenance:" in " ".join(help_result.output.split())

    dry_run = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "demo",
            "greet",
            "--name",
            "Alice",
            "--count",
            "2",
            "--verbose",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert dry_run.exit_code == 0
    payload = json.loads(dry_run.output)
    argv = payload["data"]["plan"]["rendered_request"]["argv"]
    assert argv[:3] == [sys.executable, str(script_path), "greet"]
    assert "--name" in argv and "Alice" in argv
    assert "--count" in argv and "2" in argv
    assert "--verbose" in argv


def test_imported_cli_leaf_help_uses_static_direct_path(tmp_path: Path, monkeypatch):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-manifest.yaml"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
sources:
  demo_cli:
    type: cli
    executable: {sys.executable}
    discovery:
      manifest: {manifest_path}
mounts:
  - id: demo
    source: demo_cli
    select:
      include: ["*"]
    command:
      under: [demo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    import_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage",
            "source",
            "import-help",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--format",
            "json",
        ],
    )
    assert import_result.exit_code == 0

    def fail_build_app(*args, **kwargs):
        raise AssertionError("leaf --help should not build the full app")

    monkeypatch.setattr(root_module, "build_app", fail_build_app)
    monkeypatch.setattr(
        root_module,
        "_parse_root_argv",
        lambda argv: {
            "help_requested": True,
            "command_path": ["demo", "greet"],
            "config_path": config_path,
            "profile": None,
            "global_output": "text",
        },
    )

    help_result = runner.invoke(main, ["--config", str(config_path), "demo", "greet", "--help"])
    assert help_result.exit_code == 0
    assert "--name TEXT" in help_result.output


def test_imported_cli_group_help_uses_static_catalog_without_building_app(tmp_path: Path, monkeypatch):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-manifest.yaml"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
sources:
  demo_cli:
    type: cli
    executable: {sys.executable}
    discovery:
      manifest: {manifest_path}
mounts:
  - id: demo
    source: demo_cli
    select:
      include: ["*"]
    command:
      under: [demo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    import_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage",
            "source",
            "import-help",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--format",
            "json",
        ],
    )
    assert import_result.exit_code == 0

    def fail_build_app(*args, **kwargs):
        raise AssertionError("group --help should not build the full app")

    monkeypatch.setattr(root_module, "build_app", fail_build_app)
    monkeypatch.setattr(
        root_module,
        "_parse_root_argv",
        lambda argv: {
            "help_requested": True,
            "command_path": ["demo"],
            "config_path": config_path,
            "profile": None,
            "global_output": "text",
        },
    )

    help_result = runner.invoke(main, ["--config", str(config_path), "demo", "--help"])
    assert help_result.exit_code == 0
    assert "greet" in help_result.output


def test_imported_cli_group_help_shows_original_command_description(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(
        """
import click


@click.group()
def cli():
    pass


@cli.command()
@click.option("--name", required=True, help="User name")
def greet(name):
    \"\"\"Friendly greeting command.\"\"\"
    click.echo(name)


if __name__ == "__main__":
    cli()
""".strip()
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "demo-manifest.yaml"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
sources:
  demo_cli:
    type: cli
    executable: {sys.executable}
    discovery:
      manifest: {manifest_path}
mounts:
  - id: demo
    source: demo_cli
    select:
      include: ["*"]
    command:
      under: [demo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    import_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage",
            "source",
            "import-help",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--format",
            "json",
        ],
    )
    assert import_result.exit_code == 0

    help_result = runner.invoke(main, ["--config", str(config_path), "demo", "--help"])
    assert help_result.exit_code == 0
    assert "Friendly greeting command." in help_result.output


def test_source_import_help_uses_multistep_progress(tmp_path: Path, monkeypatch):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-manifest.yaml"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
sources:
  demo_cli:
    type: cli
    executable: {sys.executable}
    discovery:
      manifest: {manifest_path}
mounts: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    captured = {}

    class RecordingProgress:
        def __init__(self, output_format, title, steps):
            captured["output_format"] = output_format
            captured["title"] = title
            captured["steps"] = list(steps)
            captured["advanced"] = []

        def __enter__(self):
            return self

        def advance(self, label=None):
            captured["advanced"].append(label)

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(root_module, "_ProgressSteps", RecordingProgress)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage",
            "source",
            "import-help",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--format",
            "text",
        ],
    )

    assert result.exit_code == 0
    assert captured["title"] == "Importing help for 'demo_cli.greet'"
    assert captured["steps"] == ["Inspect help output", "Write manifest", "Rebuild catalog"]
    assert captured["advanced"] == ["Inspecting help output", "Writing manifest", "Rebuilding catalog"]


def test_progress_steps_reports_failed_step_and_timing(monkeypatch):
    class TTYBuffer:
        def write(self, data):
            return len(data)

        def flush(self):
            return None

        def isatty(self):
            return True

    times = iter([10.0, 10.2, 10.6, 11.1, 11.4, 11.7])
    monkeypatch.setattr(root_module.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(root_module.sys, "stderr", TTYBuffer())
    messages = []
    monkeypatch.setattr(root_module.click, "echo", lambda message, err=False: messages.append((message, err)))

    with pytest.raises(RuntimeError):
        with root_module._ProgressSteps("text", "Demo Progress", ["alpha", "beta"]) as progress:
            progress.advance("Step Alpha")
            raise RuntimeError("boom")

    output = "\n".join(message for message, _ in messages)
    assert "Failed at step 1/2: Step Alpha" in output
    assert "step 0.40s" in output
    assert "total 1.10s" in output
    assert "Failed Demo Progress in 1.40s" in output
    assert "1. Step Alpha: 0.40s" in output


def test_progress_steps_reports_total_and_per_step_on_success(monkeypatch):
    class TTYBuffer:
        def write(self, data):
            return len(data)

        def flush(self):
            return None

        def isatty(self):
            return True

    times = iter([20.0, 20.1, 20.5, 20.8, 21.4, 21.8])
    monkeypatch.setattr(root_module.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(root_module.sys, "stderr", TTYBuffer())
    messages = []
    monkeypatch.setattr(root_module.click, "echo", lambda message, err=False: messages.append((message, err)))

    with root_module._ProgressSteps("text", "Demo Progress", ["alpha", "beta"]) as progress:
        progress.advance("Step Alpha")
        progress.advance("Step Beta")

    output = "\n".join(message for message, _ in messages)
    assert "Completed Demo Progress in 1.80s" in output
    assert "1. Step Alpha: 0.40s" in output
    assert "2. Step Beta: 0.60s" in output


def test_elapsed_status_updates_message_with_elapsed_time(monkeypatch):
    class TTYBuffer:
        def write(self, data):
            return len(data)

        def flush(self):
            return None

        def isatty(self):
            return True

    updates = []

    class FakeStatus:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, message):
            updates.append(message)

    class FakeConsole:
        def __init__(self, stderr=True):
            self.stderr = stderr

        def status(self, message):
            updates.append(message)
            return FakeStatus()

    monkeypatch.setattr(root_module.sys, "stderr", TTYBuffer())
    monkeypatch.setitem(sys.modules, "rich.console", type("FakeRichConsoleModule", (), {"Console": FakeConsole}))

    with root_module._elapsed_status("text", "Invoking demo", interval=0.01):
        time.sleep(0.03)

    assert any("Invoking demo" in item for item in updates)
    assert any("elapsed" in item for item in updates)


def test_dynamic_callback_starts_elapsed_status_before_loading_app():
    events = []
    mount = type(
        "Mount",
        (),
        {
            "mount_id": "demo.greet",
            "source_name": "demo_cli",
            "operation": type("Operation", (), {"id": "greet"})(),
        },
    )()
    app = type(
        "App",
        (),
        {
            "catalog": type("Catalog", (), {"find_by_id": lambda self, mount_id: None})(),
        },
    )()

    class RecordingStatus:
        def __enter__(self):
            events.append("status_enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("status_exit")
            return False

    command = click.Command(
        "demo",
        params=[click.Option(["--output-format"], default="text")],
        callback=execution_runtime.build_dynamic_callback(
            mount,
            get_app=lambda ctx, mode="invoke", progress_callback=None: events.append("get_app") or app,
            fail=lambda ctx, exc, stage, output_format: (_ for _ in ()).throw(exc),
            error_output_format=lambda ctx, output_format: output_format or "text",
            elapsed_status=lambda output_format, label: RecordingStatus(),
            run_mount_command=lambda app, runtime_mount, kwargs, mode, **extra: events.append(
                ("run_mount_command", mode, extra.get("show_elapsed_status"))
            ),
        ),
    )

    result = CliRunner().invoke(command, ["--output-format", "text"])

    assert result.exit_code == 0
    assert events == [
        "status_enter",
        "get_app",
        ("run_mount_command", "invoke", False),
        "status_exit",
    ]


def test_pass_app_starts_elapsed_status_before_loading_app(monkeypatch):
    events = []

    class RecordingStatus:
        def __enter__(self):
            events.append("status_enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("status_exit")
            return False

    monkeypatch.setattr(root_module, "_elapsed_status", lambda output_format, label: RecordingStatus())
    monkeypatch.setattr(root_module, "_get_app", lambda ctx, mode="full", progress_callback=None: events.append(("get_app", mode)) or object())

    @click.command()
    @click.option("--output-format", default="text")
    @root_module.pass_app
    def demo(app, output_format):
        events.append("command_body")

    result = CliRunner().invoke(demo, ["--output-format", "text"])

    assert result.exit_code == 0
    assert events == [
        "status_enter",
        ("get_app", "full"),
        "status_exit",
        "command_body",
    ]


def test_pass_app_updates_loading_message_from_build_progress(monkeypatch):
    updates = []

    class RecordingStatus:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, message):
            updates.append(message)

    def fake_get_app(ctx, mode="full", progress_callback=None):
        if progress_callback is not None:
            progress_callback("Discovering sources (1/2): demo")
            progress_callback("Compiling mounts (2/3): demo.mount")
        return object()

    monkeypatch.setattr(root_module, "_elapsed_status", lambda output_format, label: RecordingStatus())
    monkeypatch.setattr(root_module, "_get_app", fake_get_app)

    @click.command()
    @click.option("--output-format", default="text")
    @root_module.pass_app
    def demo(app, output_format):
        return None

    result = CliRunner().invoke(demo, ["--output-format", "text"])

    assert result.exit_code == 0
    assert any("Loading demo: Discovering sources (1/2): demo" == item for item in updates)
    assert any("Loading demo: Compiling mounts (2/3): demo.mount" == item for item in updates)


def test_pass_help_app_uses_help_mode(monkeypatch):
    events = []

    class RecordingStatus:
        def __enter__(self):
            events.append("status_enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("status_exit")
            return False

    monkeypatch.setattr(root_module, "_elapsed_status", lambda output_format, label: RecordingStatus())
    monkeypatch.setattr(root_module, "_get_app", lambda ctx, mode="full", progress_callback=None: events.append(("get_app", mode)) or object())

    @click.command()
    @click.option("--output-format", default="text")
    @root_module.pass_help_app
    def demo(app, output_format):
        events.append("command_body")

    result = CliRunner().invoke(demo, ["--output-format", "text"])

    assert result.exit_code == 0
    assert events == [
        "status_enter",
        ("get_app", "help"),
        "status_exit",
        "command_body",
    ]


def test_pass_minimal_app_uses_minimal_mode(monkeypatch):
    events = []

    class RecordingStatus:
        def __enter__(self):
            events.append("status_enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("status_exit")
            return False

    monkeypatch.setattr(root_module, "_elapsed_status", lambda output_format, label: RecordingStatus())
    monkeypatch.setattr(root_module, "_get_app", lambda ctx, mode="full", progress_callback=None: events.append(("get_app", mode)) or object())

    @click.command()
    @click.option("--output-format", default="text")
    @root_module.pass_minimal_app
    def demo(app, output_format):
        events.append("command_body")

    result = CliRunner().invoke(demo, ["--output-format", "text"])

    assert result.exit_code == 0
    assert events == [
        "status_enter",
        ("get_app", "minimal"),
        "status_exit",
        "command_body",
    ]


def test_run_mount_command_can_reuse_outer_elapsed_timer(monkeypatch):
    seen = {}

    monkeypatch.setattr(execution_runtime.time, "perf_counter", lambda: 103.2)
    monkeypatch.setattr(execution_runtime, "utc_now_iso", lambda: "2026-03-31T00:00:00Z")
    monkeypatch.setattr(execution_runtime, "extract_request_args", lambda kwargs: ({}, {}))
    monkeypatch.setattr(execution_runtime, "invoke_mount", lambda app, mount, payload, runtime: {"ok": True})
    monkeypatch.setattr(execution_runtime, "render_payload", lambda payload, output_format: payload)
    monkeypatch.setattr(execution_runtime, "click", type("FakeClick", (), {"echo": lambda message: None, "get_current_context": lambda: None}))
    monkeypatch.setattr(execution_runtime, "emit_app_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(execution_runtime, "emit_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(execution_runtime, "record_run", lambda app, payload: seen.setdefault("run", payload))
    monkeypatch.setattr(execution_runtime, "summarize_result", lambda result: result)

    app = type("App", (), {"active_profile": None})()
    mount = type(
        "Mount",
        (),
        {
            "mount_id": "demo.greet",
            "stable_name": "demo.greet",
            "source_name": "demo_cli",
            "provider_type": "cli",
            "summary": "Demo greet",
            "command_path": ["demo", "greet"],
            "operation": type("Operation", (), {"id": "greet", "risk": "read"})(),
        },
    )()
    setattr(app, "ensure_mount_execution_allowed", lambda *args, **kwargs: None)

    execution_runtime.run_mount_command(
        app,
        mount,
        {"output_format": "text"},
        "invoke",
        fail=lambda *args, **kwargs: None,
        elapsed_status=lambda output_format, label: (_ for _ in ()).throw(AssertionError("elapsed_status should be skipped")),
        start_perf=100.0,
        show_elapsed_status=False,
    )

    assert seen["run"]["metadata"]["duration_ms"] == 3200


def test_dynamic_click_params_preserve_camel_case_argument_names():
    mount = SimpleNamespace(
        operation=SimpleNamespace(
            input_schema={
                "type": "object",
                "properties": {
                    "organizationId": {"type": "string"},
                    "perPage": {"type": "integer"},
                    "orderBy": {"type": "string"},
                },
                "required": ["organizationId"],
            }
        ),
        mount_config=None,
    )

    command = click.Command(
        "demo",
        params=build_click_params(mount),
        callback=lambda **kwargs: click.echo(json.dumps(extract_request_args(kwargs)[0], sort_keys=True)),
    )

    result = CliRunner().invoke(
        command,
        [
            "--organizationId",
            "org-1",
            "--perPage",
            "30",
            "--orderBy",
            "created_at",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {
        "organizationId": "org-1",
        "orderBy": "created_at",
        "perPage": 30,
    }


def test_should_load_drift_governance_skips_auth_and_runs_commands():
    assert should_load_drift_governance(("manage", "auth", "list"), help_requested=False) is False
    assert should_load_drift_governance(("manage", "runs", "list"), help_requested=False) is False
    assert should_load_drift_governance(("manage", "logs", "recent"), help_requested=False) is False
    assert should_load_drift_governance(("manage", "source", "list"), help_requested=False) is True


def test_progress_steps_update_current_emits_text_progress(monkeypatch):
    class TTYBuffer:
        def __init__(self):
            self.buffer = []

        def write(self, data):
            self.buffer.append(data)
            return len(data)

        def flush(self):
            return None

        def isatty(self):
            return True

    stderr = TTYBuffer()
    monkeypatch.setattr(root_module.sys, "stderr", stderr)
    monkeypatch.setattr(root_module.time, "perf_counter", lambda: 42.0)
    monkeypatch.setattr(root_module.click, "echo", lambda message, err=False: None)

    with root_module._ProgressSteps("text", "Demo Progress", ["alpha", "beta"]) as progress:
        progress.advance("Discovering subcommands")
        progress.update_current("Discovering subcommands (3 visited, 2 queued, 1 leaves)")

    output = "".join(stderr.buffer)
    assert "[1/2] Discovering subcommands" in output
    assert "3 visited, 2 queued, 1 leaves" in output
    assert "\r" in output


CLI_TREE_SCRIPT = """
import json
import click


@click.group()
def cli():
    \"\"\"AAC root command.\"\"\"


@cli.group()
def admin():
    \"\"\"Administrative commands.\"\"\"


@admin.command()
@click.option("--name", required=True, help="User name")
def add_user(name):
    click.echo(json.dumps({"action": "add_user", "name": name}))


@admin.command()
@click.option("--name", required=True, help="User name")
def remove_user(name):
    click.echo(json.dumps({"action": "remove_user", "name": name}))


if __name__ == "__main__":
    cli()
"""


def test_import_cli_all_recursively_imports_leaf_commands(tmp_path: Path):
    script_path = tmp_path / "aac_cli.py"
    script_path.write_text(CLI_TREE_SCRIPT, encoding="utf-8")
    config_path = tmp_path / "cts.yaml"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "cli",
            "aac",
            sys.executable,
            str(script_path),
            "--all",
            "--apply",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "import_cli_tree_apply"
    assert payload["operation_count"] == 2
    assert payload["mount_count"] == 2

    app = build_app(str(config_path))
    add_mount = app.catalog.find_by_path(["aac", "admin", "add-user"])
    remove_mount = app.catalog.find_by_path(["aac", "admin", "remove-user"])
    assert add_mount is not None
    assert remove_mount is not None
    assert add_mount.operation.id == "admin_add_user"
    assert remove_mount.operation.id == "admin_remove_user"


def test_import_cli_all_uses_multistep_progress(tmp_path: Path, monkeypatch):
    script_path = tmp_path / "aac_cli.py"
    script_path.write_text(CLI_TREE_SCRIPT, encoding="utf-8")
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

    monkeypatch.setattr(root_module, "_ProgressSteps", RecordingProgress)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "cli",
            "aac",
            sys.executable,
            str(script_path),
            "--all",
            "--apply",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "import_cli_tree_apply"
    assert payload["operation_count"] == 2
    assert payload["mount_count"] == 2
    assert payload["tree"]["leaf_count"] == 2
    assert captured["title"] == "Importing CLI tree 'aac'"
    assert captured["steps"] == [
        "Inspect root command",
        "Discover subcommands",
        "Import leaf operations",
        "Prepare mounts",
        "Write manifest",
        "Compile config",
    ]
    assert captured["advanced"][:6] == [
        "Inspecting root command",
        "Discovering subcommands",
        "Importing leaf operations",
        "Preparing mounts",
        "Writing manifest",
        "Compiling config",
    ]
    assert any("Discovering subcommands" in item for item in captured["updated"])
    assert any("Importing leaf operations" in item for item in captured["updated"])
    assert any("Preparing mounts" in item for item in captured["updated"])


def test_import_cli_all_group_help_uses_original_descriptions(tmp_path: Path):
    script_path = tmp_path / "aac_cli.py"
    script_path.write_text(CLI_TREE_SCRIPT, encoding="utf-8")
    config_path = tmp_path / "cts.yaml"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "cli",
            "aac",
            sys.executable,
            str(script_path),
            "--all",
            "--apply",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0

    root_help = runner.invoke(main, ["--config", str(config_path), "aac", "--help"])
    assert root_help.exit_code == 0
    assert "AAC root command." in root_help.output

    admin_help = runner.invoke(main, ["--config", str(config_path), "aac", "admin", "--help"])
    assert admin_help.exit_code == 0
    assert "Administrative commands." in admin_help.output
