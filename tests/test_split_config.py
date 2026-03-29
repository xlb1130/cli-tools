from pathlib import Path

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "examples" / "split-demo" / "cts.yaml"


def test_split_config_loads_imported_files():
    app = build_app(str(CONFIG))
    assert app.catalog.find_by_id("demo-echo") is not None
    assert any(path.name == "demo.yaml" for path in app.config_paths)
    assert app.config.sources["demo_cli"].discovery.manifest == "../echo-manifest.yaml"


def test_split_config_dynamic_command_executes():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--config", str(CONFIG), "demo", "echo", "--text", "hello", "--upper", "--output", "json"],
    )
    assert result.exit_code == 0
    assert '"text": "HELLO"' in result.output


def test_config_paths_and_build_work_for_split_config():
    runner = CliRunner()
    paths_result = runner.invoke(main, ["--config", str(CONFIG), "config", "paths", "--format", "json"])
    assert paths_result.exit_code == 0
    assert "sources/demo.yaml" in paths_result.output

    build_result = runner.invoke(main, ["--config", str(CONFIG), "config", "build", "--format", "json"])
    assert build_result.exit_code == 0
    assert '"mounts"' in build_result.output
    assert '"demo-echo"' in build_result.output


def test_source_show_and_mount_show_include_origin_files():
    runner = CliRunner()

    source_result = runner.invoke(main, ["--config", str(CONFIG), "source", "show", "demo_cli", "--format", "json"])
    assert source_result.exit_code == 0
    assert '"origin_file"' in source_result.output
    assert "sources/demo.yaml" in source_result.output

    mount_result = runner.invoke(main, ["--config", str(CONFIG), "mount", "show", "demo-echo", "--format", "json"])
    assert mount_result.exit_code == 0
    assert '"origin_file"' in mount_result.output
    assert "mounts/demo.yaml" in mount_result.output
