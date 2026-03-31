import os
import subprocess
from pathlib import Path

from click.testing import CliRunner

from cts.cli.root import main


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "examples" / "demo" / "cts.yaml"


def test_catalog_export_contains_demo_mount():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(CONFIG), "manage", "catalog", "export", "--format", "json"])
    assert result.exit_code == 0
    assert "demo-echo" in result.output


def test_dynamic_command_executes():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "demo", "echo", "--text", "hello", "--upper", "--format", "json"],
    )
    assert result.exit_code == 0
    assert '"text": "HELLO"' in result.output


def test_dynamic_command_supports_legacy_output_alias():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "demo", "echo", "--text", "hello", "--upper", "--output", "json"],
    )
    assert result.exit_code == 0
    assert '"text": "HELLO"' in result.output


def test_root_level_format_alias_sets_default_for_dynamic_command():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "--format", "json", "demo", "echo", "--text", "hello", "--upper"],
    )
    assert result.exit_code == 0
    assert result.output.lstrip().startswith("{")
    assert '"text": "HELLO"' in result.output


def test_explain_works():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "manage", "explain", "demo-echo", "--input-json", '{"text":"hello"}', "--format", "json"],
    )
    assert result.exit_code == 0
    assert '"operation_id": "echo_json"' in result.output


def test_dynamic_help_includes_provider_details():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(CONFIG), "demo", "echo", "--help"])
    assert result.exit_code == 0
    assert "Run a local CLI-backed operation and return JSON output." in result.output
    assert "Details:" in result.output
    assert "Provider" in result.output
    assert "cli" in result.output
    assert "Risk" in result.output
    assert "read" in result.output
    assert "Notes:" in result.output
    assert "Examples:" in result.output
    assert "References:" in result.output
    assert "Stable mount id" in result.output
    assert "demo-echo" in result.output
    assert "Request Parameters:" in result.output
    assert "Runtime Options:" in result.output
    assert "--text TEXT" in result.output
    assert "--input-json TEXT" in result.output
    assert "--format, --output [text|json]" in result.output
    assert "Defaults to the active CLI output mode" in result.output


def test_dynamic_group_help_uses_summary_in_command_list():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(CONFIG), "demo", "--help"])
    assert result.exit_code == 0
    assert "echo  Run a local CLI-backed operation and return JSON output." in result.output
    assert "echo  Details:" not in result.output


def test_source_test_reports_health():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(CONFIG), "manage", "source", "test", "demo_cli", "--format", "json"])
    assert result.exit_code == 0
    assert '"source": "demo_cli"' in result.output
    assert '"ok": true' in result.output


def test_invalid_json_input_uses_validation_exit_code():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "manage", "invoke", "demo-echo", "--input-json", "{bad", "--format", "json"],
    )
    assert result.exit_code == 3
    assert '"code": "invalid_json_input"' in result.output


def test_config_lint_reports_invalid_config(tmp_path: Path):
    broken = tmp_path / "broken.yaml"
    broken.write_text("sources: [\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(broken), "manage", "config", "lint", "--format", "json"])
    assert result.exit_code == 2
    assert '"code": "invalid_config"' in result.output


def test_version_matches_project_metadata():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    expected = next(
        line.split("=", 1)[1].strip().strip('"')
        for line in pyproject.splitlines()
        if line.startswith("version = ")
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        ["python3", "-m", "cts.main", "--version"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert f"cts, version {expected}" in result.stdout
