import json
import sys
from pathlib import Path

import yaml
from click.testing import CliRunner

from cts.cli.root import main


def test_source_add_creates_default_root_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Use explicit config path to avoid writing to user's home directory
        config_path = Path("cts.yaml")
        
        result = runner.invoke(
            main,
            ["--config", str(config_path), "source", "add", "http", "jira", "--base-url", "https://jira.example.com", "--format", "json"],
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
                "source",
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
                "mount",
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
                "alias",
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
        assert "Stable mount id: jira-get-issue" in help_result.output

        mount_show = runner.invoke(
            main,
            ["--config", str(config_path), "mount", "show", "jira-get-issue", "--format", "json"],
        )
        assert mount_show.exit_code == 0
        mount_show_payload = json.loads(mount_show.output)
        assert ["issue", "get"] in mount_show_payload["aliases"]


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
                "source",
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
                "mount",
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
    result = runner.invoke(main, ["completion", "script", "--shell", "zsh"])

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
            ["--config", str(config_path), "doctor", "--format", "json"],
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
                "source",
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
                "source",
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
                "source",
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
                "source",
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
                "mount",
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
                "source",
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
                "source",
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
                "source",
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
                "mount",
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
                "mount",
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
                "mount",
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
                "mount",
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
        payload = json.loads(result.output.splitlines()[-1])
        assert payload["action"] == "import_cli_preview"
        assert payload["source"]["name"] == "demo_cli"
        assert payload["operation_id"] == "greet"


def test_completion_install_zsh():
    runner = CliRunner()
    with runner.isolated_filesystem():
        import os
        os.environ["HOME"] = str(Path.cwd())
        
        result = runner.invoke(
            main,
            [
                "completion",
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
            "completion",
            "bootstrap",
            "--shell",
            "zsh",
        ],
    )
    assert result.exit_code == 0
    # Should output completion-related content
    assert len(result.output) > 0
