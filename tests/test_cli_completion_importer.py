import json
import sys
from pathlib import Path

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main


CLI_SCRIPT = """
import click
import json


@click.group()
def cli():
    pass


@cli.command()
@click.option("--name", required=True, help="User name")
@click.option("--count", type=int, default=1, show_default=True, help="Repeat count")
@click.option("--verbose", is_flag=True, help="Verbose output")
def greet(name, count, verbose):
    click.echo(json.dumps({"name": name, "count": count, "verbose": verbose}))


@cli.command("complete-greet")
def complete_greet():
    click.echo("--name NAME\\tUser name\\trequired=true")
    click.echo("--count INT\\tRepeat count\\tdefault=1")
    click.echo("--verbose\\tVerbose output")


if __name__ == "__main__":
    cli()
"""


def test_source_import_completion_generates_manifest_and_compiled_operation(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-completion-manifest.yaml"
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
            "import-completion",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--completion-command",
            f"{sys.executable} {script_path} complete-greet",
            "--completion-format",
            "lines",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "source_import_completion"
    assert payload["compiled_operation"]["id"] == "greet"
    assert payload["compiled_operation"]["input_schema"]["properties"]["name"]["type"] == "string"
    assert payload["compiled_operation"]["input_schema"]["properties"]["count"]["type"] == "integer"
    assert payload["compiled_operation"]["input_schema"]["properties"]["verbose"]["type"] == "boolean"

    raw_manifest = manifest_path.read_text(encoding="utf-8")
    assert "strategy: cli_completion" in raw_manifest
    assert "completion_format: lines" in raw_manifest

    app = build_app(str(config_path))
    mount = app.catalog.find_by_id("demo.greet")
    assert mount is not None


def test_imported_cli_completion_manifest_supports_dynamic_command_dry_run(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manifest_path = tmp_path / "demo-completion-manifest.yaml"
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
            "import-completion",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--completion-command",
            f"{sys.executable} {script_path} complete-greet",
            "--completion-format",
            "lines",
            "--format",
            "json",
        ],
    )
    assert import_result.exit_code == 0

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
