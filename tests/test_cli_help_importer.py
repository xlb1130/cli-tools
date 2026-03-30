import json
import sys
from pathlib import Path

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main


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


CLI_TREE_SCRIPT = """
import json
import click


@click.group()
def cli():
    pass


@cli.group()
def admin():
    pass


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
