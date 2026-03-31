from pathlib import Path

from click.testing import CliRunner

from cts.cli.root import main


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples" / "demo" / "echo-manifest.yaml"


def test_config_lint_static_checks(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  default_profile: missing
sources:
  broken:
    type: unknown
    auth_ref: no-such-auth
    discovery:
      manifest: ./missing-manifest.yaml
mounts:
  - id: bad-mount
    source: missing-source
    command:
      path: [bad, mount]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(config_path), "manage", "config", "lint", "--format", "json"])
    assert result.exit_code == 2
    assert '"default_profile_not_found"' in result.output
    assert '"unsupported_provider_type"' in result.output
    assert '"auth_profile_not_found"' in result.output
    assert '"manifest_not_found"' in result.output
    assert '"mount_source_not_found"' in result.output


def test_invoke_writes_logs_and_run_history(tmp_path: Path):
    log_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  default_profile: dev
  log_dir: {log_dir}
  state_dir: {state_dir}
profiles:
  dev: {{}}
sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
      manifest: {MANIFEST}
mounts:
  - id: demo-echo
    source: demo_cli
    operation: echo_json
    command:
      path: [demo, echo]
    machine:
      stable_name: demo.echo
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    invoke_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "invoke", "demo-echo", "--input-json", '{"text":"hello"}', "--format", "json"],
    )
    assert invoke_result.exit_code == 0
    assert '"run_id"' in invoke_result.output

    runs_result = runner.invoke(main, ["--config", str(config_path), "manage", "runs", "list", "--format", "json"])
    assert runs_result.exit_code == 0
    assert '"mount_id": "demo-echo"' in runs_result.output

    runs_filtered_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "runs", "list", "--mount-id", "demo-echo", "--ok", "true", "--format", "json"],
    )
    assert runs_filtered_result.exit_code == 0
    assert '"mount_id": "demo-echo"' in runs_filtered_result.output

    doctor_result = runner.invoke(main, ["--config", str(config_path), "manage", "doctor", "--format", "json"])
    assert doctor_result.exit_code == 0
    assert '"runtime_paths"' in doctor_result.output

    logs_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "logs", "recent", "--limit", "10", "--event", "invoke_complete", "--format", "json"],
    )
    assert logs_result.exit_code == 0
    assert '"event": "invoke_complete"' in logs_result.output

    watch_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "logs", "watch", "--limit", "10", "--iterations", "1", "--event", "invoke_start", "--format", "json"],
    )
    assert watch_result.exit_code == 0
    assert '"event": "invoke_start"' in watch_result.output

    runs_watch_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "runs", "watch", "--limit", "10", "--iterations", "1", "--mount-id", "demo-echo", "--format", "json"],
    )
    assert runs_watch_result.exit_code == 0
    assert '"run_id"' in runs_watch_result.output

    app_log = log_dir / "app.jsonl"
    audit_log = log_dir / "audit.jsonl"
    history_db = state_dir / "history.db"
    assert app_log.exists()
    assert audit_log.exists()
    assert history_db.exists()

    app_log_text = app_log.read_text(encoding="utf-8")
    audit_log_text = audit_log.read_text(encoding="utf-8")
    assert "invoke_start" in app_log_text
    assert "invoke_complete" in app_log_text
    assert "invoke_complete" in audit_log_text
