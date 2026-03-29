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


@cli.command("schema-greet")
def schema_greet():
    click.echo(json.dumps({
        "title": "Greet",
        "description": "Schema-defined greet command",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "User name"},
                "count": {"type": "integer", "default": 1, "description": "Repeat count"},
                "verbose": {"type": "boolean", "description": "Verbose output"}
            },
            "required": ["name"]
        },
        "option_bindings": {
            "name": {"flags": ["--name"], "emit_flag": "--name", "kind": "value", "repeatable": False},
            "count": {"flags": ["--count"], "emit_flag": "--count", "kind": "value", "repeatable": False},
            "verbose": {"flags": ["--verbose"], "emit_flag": "--verbose", "kind": "flag", "repeatable": False}
        },
        "option_order": ["name", "count", "verbose"],
        "output_mode": "json"
    }))


if __name__ == "__main__":
    cli()
"""


def test_source_import_schema_generates_manifest_and_compiled_operation(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-schema-manifest.yaml"
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
            "source",
            "import-schema",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--schema-command",
            f"{sys.executable} {script_path} schema-greet",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "source_import_schema"
    assert payload["compiled_operation"]["id"] == "greet"
    assert payload["compiled_operation"]["input_schema"]["properties"]["name"]["type"] == "string"
    assert payload["compiled_operation"]["input_schema"]["properties"]["count"]["type"] == "integer"
    assert payload["compiled_operation"]["input_schema"]["properties"]["verbose"]["type"] == "boolean"

    raw_manifest = manifest_path.read_text(encoding="utf-8")
    assert "strategy: cli_schema" in raw_manifest
    assert "schema_format: auto" in raw_manifest

    app = build_app(str(config_path))
    mount = app.catalog.find_by_id("demo.greet")
    assert mount is not None


def test_imported_cli_schema_manifest_supports_dynamic_command_invoke(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-schema-manifest.yaml"
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
            "source",
            "import-schema",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--schema-command",
            f"{sys.executable} {script_path} schema-greet",
            "--format",
            "json",
        ],
    )
    assert import_result.exit_code == 0

    invoke_result = runner.invoke(
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
            "--output",
            "json",
        ],
    )
    assert invoke_result.exit_code == 0
    payload = json.loads(invoke_result.output)
    assert payload["data"]["name"] == "Alice"
    assert payload["data"]["count"] == 2
    assert payload["data"]["verbose"] is True
