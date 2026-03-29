from pathlib import Path

from click.testing import CliRunner

from cts.cli.root import main


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "examples" / "demo" / "cts.yaml"


def test_catalog_export_contains_demo_mount():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(CONFIG), "catalog", "export", "--format", "json"])
    assert result.exit_code == 0
    assert "demo-echo" in result.output


def test_dynamic_command_executes():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "demo", "echo", "--text", "hello", "--upper", "--output", "json"],
    )
    assert result.exit_code == 0
    assert '"text": "HELLO"' in result.output


def test_explain_works():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "explain", "demo-echo", "--input-json", '{"text":"hello"}', "--format", "json"],
    )
    assert result.exit_code == 0
    assert '"operation_id": "echo_json"' in result.output


def test_dynamic_help_includes_provider_details():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(CONFIG), "demo", "echo", "--help"])
    assert result.exit_code == 0
    assert "Provider: cli" in result.output
    assert "Risk: read" in result.output
    assert "Stable mount id: demo-echo" in result.output


def test_source_test_reports_health():
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(CONFIG), "source", "test", "demo_cli", "--format", "json"])
    assert result.exit_code == 0
    assert '"source": "demo_cli"' in result.output
    assert '"ok": true' in result.output


def test_invalid_json_input_uses_validation_exit_code():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "invoke", "demo-echo", "--input-json", "{bad", "--format", "json"],
    )
    assert result.exit_code == 3
    assert '"code": "invalid_json_input"' in result.output


def test_config_lint_reports_invalid_config(tmp_path: Path):
    broken = tmp_path / "broken.yaml"
    broken.write_text("sources: [\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(broken), "config", "lint", "--format", "json"])
    assert result.exit_code == 2
    assert '"code": "invalid_config"' in result.output
