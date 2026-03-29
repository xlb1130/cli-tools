import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from cts.cli.root import main


def test_source_add_creates_default_root_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            main,
            ["source", "add", "http", "jira", "--base-url", "https://jira.example.com", "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["created_file"] is True

        config_path = Path(".cts/config.yaml")
        assert config_path.exists()

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
