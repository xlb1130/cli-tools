import json
import sys
from pathlib import Path

from click.testing import CliRunner

import cts.cli.root as root_module
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


MANPAGE_TEXT = """
DEMO-GREET(1)

NAME
    demo-greet - Greet users from terminal

SYNOPSIS
    demo-greet greet --name NAME [--count COUNT] [--verbose]

OPTIONS
    --name NAME
        User name. (required)

    --count COUNT
        Repeat count. (default: 1)

    --verbose
        Verbose output.
"""


def test_source_import_manpage_generates_manifest_and_compiled_operation(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manpage_path = tmp_path / "demo-greet.man.txt"
    manpage_path.write_text(MANPAGE_TEXT.strip() + "\n", encoding="utf-8")
    manifest_path = tmp_path / "demo-manpage-manifest.yaml"
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
            "import-manpage",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--man-file",
            str(manpage_path),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "source_import_manpage"
    assert payload["compiled_operation"]["id"] == "greet"
    assert payload["compiled_operation"]["input_schema"]["properties"]["name"]["type"] == "string"
    assert payload["compiled_operation"]["input_schema"]["properties"]["count"]["type"] == "integer"
    assert payload["compiled_operation"]["input_schema"]["properties"]["verbose"]["type"] == "boolean"

    raw_manifest = manifest_path.read_text(encoding="utf-8")
    assert "strategy: cli_manpage" in raw_manifest
    assert "man_file:" in raw_manifest

    app = build_app(str(config_path))
    mount = app.catalog.find_by_id("demo.greet")
    assert mount is not None
    assert mount.command_path == ["demo", "greet"]


def test_imported_cli_manpage_manifest_supports_dynamic_command_dry_run(tmp_path: Path):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manpage_path = tmp_path / "demo-greet.man.txt"
    manpage_path.write_text(MANPAGE_TEXT.strip() + "\n", encoding="utf-8")
    manifest_path = tmp_path / "demo-manpage-manifest.yaml"
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
            "import-manpage",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--man-file",
            str(manpage_path),
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


def test_source_import_manpage_uses_multistep_progress(tmp_path: Path, monkeypatch):
    script_path = tmp_path / "demo_cli.py"
    script_path.write_text(CLI_SCRIPT, encoding="utf-8")
    manpage_path = tmp_path / "demo-greet.man.txt"
    manpage_path.write_text(MANPAGE_TEXT.strip() + "\n", encoding="utf-8")
    manifest_path = tmp_path / "demo-manpage-manifest.yaml"
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
            "source",
            "import-manpage",
            "demo_cli",
            "greet",
            str(script_path),
            "greet",
            "--man-file",
            str(manpage_path),
            "--format",
            "text",
        ],
    )

    assert result.exit_code == 0
    assert captured["title"] == "Importing man page for 'demo_cli.greet'"
    assert captured["steps"] == ["Read man page", "Write manifest", "Rebuild catalog"]
    assert captured["advanced"] == ["Reading man page", "Writing manifest", "Rebuilding catalog"]
