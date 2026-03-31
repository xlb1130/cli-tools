import json
from pathlib import Path

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main
from cts.providers import mcp_cli


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples" / "demo" / "echo-manifest.yaml"


def _write_manifest(path: Path, operations: list[dict]) -> None:
    payload = {"version": 1, "operations": operations}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _cli_manifest_operation(operation_id: str, input_schema: dict) -> dict:
    return {
        "id": operation_id,
        "title": operation_id.title(),
        "description": f"Operation {operation_id}",
        "risk": "read",
        "input_schema": input_schema,
        "argv_template": [
            "python3",
            "-c",
            "import json,sys; print(json.dumps({'argv': sys.argv[1:]}))",
            "{name}",
        ],
        "output": {"mode": "json"},
    }


def test_sync_writes_report_and_capability_snapshot(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
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
    result = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert result.exit_code == 0

    payload = json.loads(result.output)
    report_path = Path(payload["report_path"])
    capability_snapshot_path = Path(payload["capability_snapshot_path"])

    assert report_path.exists()
    assert capability_snapshot_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    capability_snapshot = json.loads(capability_snapshot_path.read_text(encoding="utf-8"))

    assert report["kind"] == "sync_report"
    assert report["items"][0]["source"] == "demo_cli"
    assert report["items"][0]["ok"] is True
    assert report["capability_snapshot_path"] == str(capability_snapshot_path)

    assert capability_snapshot["kind"] == "capability_snapshot"
    assert capability_snapshot["sources"][0]["name"] == "demo_cli"
    assert capability_snapshot["mounts"][0]["mount_id"] == "demo-echo"


def test_discovery_cache_fallback_preserves_mounts_and_schema_provenance(tmp_path: Path, monkeypatch):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
sources:
  remote_mcp:
    type: mcp
    url: https://example.com/mcp
    server: demo
    discovery:
      mode: live
mounts:
  - id: demo
    source: remote_mcp
    select:
      include: ["*"]
    command:
      under: [demo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def fake_bridge_success(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        assert command == "list-primitives"
        return {
            "ok": True,
            "server": "demo",
            "transport_type": "streamable_http",
            "primitives": [
                {
                    "primitive_type": "tool",
                    "name": "bing_search",
                    "description": "Search the web",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                }
            ],
        }

    def fake_bridge_failure(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        raise RuntimeError("bridge offline")

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge_success)
    first_app = build_app(str(config_path))
    assert first_app.catalog.find_by_id("demo.bing_search") is not None

    snapshot_path = cache_dir / "discovery" / "remote_mcp.json"
    assert snapshot_path.exists()

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge_failure)
    second_app = build_app(str(config_path))
    assert second_app.catalog.find_by_id("demo.bing_search") is not None
    assert second_app.discovery_state["remote_mcp"]["fallback"] == "cache"
    assert second_app.discovery_state["remote_mcp"]["usable"] is True
    assert second_app.discovery_state["remote_mcp"]["ok"] is False

    runner = CliRunner()

    inspect_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "inspect", "operation", "remote_mcp", "bing_search", "--format", "json"],
    )
    assert inspect_result.exit_code == 0
    inspect_payload = json.loads(inspect_result.output)
    assert inspect_payload["schema_provenance"]["strategy"] == "probed"
    assert inspect_payload["schema_provenance"]["origin"] == "demo"

    help_result = runner.invoke(main, ["--config", str(config_path), "demo", "bing", "search", "--help"])
    assert help_result.exit_code == 0
    assert "Schema provenance: probed" in help_result.output


def test_live_discovery_uses_fresh_cache_when_cache_ttl_is_valid(tmp_path: Path, monkeypatch):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
sources:
  remote_mcp:
    type: mcp
    url: https://example.com/mcp
    server: demo
    discovery:
      mode: live
      cache_ttl: 3600
mounts:
  - id: demo
    source: remote_mcp
    select:
      include: ["*"]
    command:
      under: [demo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    calls = {"count": 0}

    def fake_bridge_success(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        calls["count"] += 1
        return {
            "ok": True,
            "server": "demo",
            "transport_type": "streamable_http",
            "primitives": [
                {
                    "primitive_type": "tool",
                    "name": "bing_search",
                    "description": "Search the web",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                }
            ],
        }

    def fake_bridge_failure(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        raise RuntimeError("bridge should not be called when cache is fresh")

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge_success)
    first_app = build_app(str(config_path))
    assert first_app.discovery_state["remote_mcp"]["discovery_strategy"] == "live"
    assert calls["count"] == 1

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge_failure)
    second_app = build_app(str(config_path))
    assert second_app.catalog.find_by_id("demo.bing_search") is not None
    assert second_app.discovery_state["remote_mcp"]["ok"] is True
    assert second_app.discovery_state["remote_mcp"]["discovery_strategy"] == "cache"
    assert second_app.discovery_state["remote_mcp"]["cache_status"] == "cache_ttl"
    assert second_app.discovery_state["remote_mcp"]["cache_age_seconds"] is not None


def test_cache_only_mode_uses_snapshot_without_live_discovery(tmp_path: Path, monkeypatch):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
sources:
  remote_mcp:
    type: mcp
    url: https://example.com/mcp
    server: demo
    discovery:
      mode: cache_only
mounts:
  - id: demo
    source: remote_mcp
    select:
      include: ["*"]
    command:
      under: [demo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app = build_app(str(config_path))
    assert app.discovery_state["remote_mcp"]["ok"] is False
    assert app.discovery_state["remote_mcp"]["cache_status"] == "miss"
    assert app.catalog.find_by_id("demo.bing_search") is None

    snapshot_path = cache_dir / "discovery" / "remote_mcp.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "discovery_snapshot",
                "source": "remote_mcp",
                "provider_type": "mcp",
                "mode": "sync",
                "generated_at": "2026-03-28T16:00:00+00:00",
                "operation_count": 1,
                "schema_count": 1,
                "operations": [
                    {
                        "id": "bing_search",
                        "source": "remote_mcp",
                        "provider_type": "mcp",
                        "title": "bing_search",
                        "stable_name": "demo.bing.search",
                        "description": "Search the web",
                        "kind": "action",
                        "tags": [],
                        "group": None,
                        "risk": "read",
                        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                        "output_schema": None,
                        "examples": [],
                        "supported_surfaces": ["cli", "invoke", "mcp"],
                        "transport_hints": {},
                        "provider_config": {},
                    }
                ],
                "schema_index": {
                    "bing_search": {
                        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                        "provenance": {"strategy": "probed", "origin": "demo", "confidence": 0.95},
                    }
                },
                "operation_fingerprints": {"bing_search": "sha256:test"},
                "snapshot_fingerprint": "sha256:test",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_bridge_failure(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        raise RuntimeError("cache_only should not call live discovery")

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge_failure)
    cached_app = build_app(str(config_path))
    assert cached_app.catalog.find_by_id("demo.bing_search") is not None
    assert cached_app.discovery_state["remote_mcp"]["ok"] is True
    assert cached_app.discovery_state["remote_mcp"]["discovery_strategy"] == "cache"
    assert cached_app.discovery_state["remote_mcp"]["cache_status"] == "cache_only"


def test_sync_classifies_additive_drift_from_manifest_change(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
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

    operation_v1 = {
        "id": "greet",
        "title": "Greet",
        "description": "Demo greet",
        "risk": "read",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    }
    operation_v2 = {
        **operation_v1,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer", "default": 1},
            },
            "required": ["name"],
        },
    }
    _write_manifest(manifest_path, [operation_v1])

    runner = CliRunner()
    first = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert first.exit_code == 0
    first_payload = json.loads(first.output)
    assert first_payload["items"][0]["drift"]["status"] == "initial"

    _write_manifest(manifest_path, [operation_v2])
    second = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert second.exit_code == 0
    payload = json.loads(second.output)
    item = payload["items"][0]
    assert item["drift"]["changed"] is True
    assert item["drift"]["severity"] == "additive"
    assert "optional_param_added:count" in item["drift"]["changes"][0]["reasons"]
    assert payload["drift_summary"]["severity"] == "additive"
    assert payload["drift_summary"]["changed_sources"] == 1

    report = json.loads(Path(payload["report_path"]).read_text(encoding="utf-8"))
    assert report["drift_summary"]["severity"] == "additive"

    inspect_result = runner.invoke(main, ["--config", str(config_path), "manage", "inspect", "drift", "demo_cli", "--format", "json"])
    assert inspect_result.exit_code == 0
    inspect_payload = json.loads(inspect_result.output)
    assert inspect_payload["drift_summary"]["severity"] == "additive"
    assert inspect_payload["items"][0]["drift"]["severity"] == "additive"


def test_additive_drift_can_auto_accept_via_default_policy(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
drift:
  defaults:
    on_additive_change: auto_accept
sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
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

    _write_manifest(
        manifest_path,
        [
            _cli_manifest_operation(
                "greet",
                {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            )
        ],
    )

    runner = CliRunner()
    first = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert first.exit_code == 0

    _write_manifest(
        manifest_path,
        [
            _cli_manifest_operation(
                "greet",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "count": {"type": "integer", "default": 1}},
                    "required": ["name"],
                },
            )
        ],
    )
    second = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert second.exit_code == 0
    payload = json.loads(second.output)

    source_state = payload["drift_governance"]["sources"]["demo_cli"]
    mount_state = payload["drift_governance"]["mounts"]["demo.greet"]
    assert source_state["status"] == "accepted"
    assert source_state["accepted_by_policy"] is True
    assert source_state["accepted_mount_count"] == 1
    assert mount_state["status"] == "accepted"
    assert mount_state["action"] == "auto_accept"
    assert mount_state["severity"] == "additive"
    assert mount_state["blocked"] is False

    inspect_mount = runner.invoke(main, ["--config", str(config_path), "manage", "inspect", "mount", "demo.greet", "--format", "json"])
    assert inspect_mount.exit_code == 0
    assert json.loads(inspect_mount.output)["drift_state"]["status"] == "accepted"

    help_result = runner.invoke(main, ["--config", str(config_path), "demo", "greet", "--help"])
    assert help_result.exit_code == 0
    assert "status=accepted" in help_result.output

    invoke_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "invoke", "demo.greet", "--input-json", '{"name":"Alice","count":2}', "--format", "json"],
    )
    assert invoke_result.exit_code == 0


def test_compatible_drift_can_auto_accept_via_mount_policy_alias(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
      manifest: {manifest_path}
mounts:
  - id: demo
    source: demo_cli
    select:
      include: ["*"]
    command:
      under: [demo]
    drift_policy:
      accept_compatible_changes: true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    first_operation = _cli_manifest_operation(
        "greet",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    second_operation = {
        **first_operation,
        "description": "Updated greet description",
    }
    _write_manifest(manifest_path, [first_operation])

    runner = CliRunner()
    first = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert first.exit_code == 0

    _write_manifest(manifest_path, [second_operation])
    second = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert second.exit_code == 0
    payload = json.loads(second.output)

    item = payload["items"][0]
    source_state = payload["drift_governance"]["sources"]["demo_cli"]
    mount_state = payload["drift_governance"]["mounts"]["demo.greet"]
    assert item["drift"]["severity"] == "compatible"
    assert "description_changed" in item["drift"]["changes"][0]["reasons"]
    assert source_state["status"] == "accepted"
    assert mount_state["status"] == "accepted"
    assert mount_state["action"] == "auto_accept"
    assert mount_state["severity"] == "compatible"
    assert mount_state["blocked"] is False


def test_sync_classifies_breaking_drift_from_required_param_addition(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
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

    operation_v1 = {
        "id": "greet",
        "title": "Greet",
        "description": "Demo greet",
        "risk": "read",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    }
    operation_v2 = {
        **operation_v1,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "region": {"type": "string"},
            },
            "required": ["name", "region"],
        },
    }
    _write_manifest(manifest_path, [operation_v1])

    runner = CliRunner()
    first = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert first.exit_code == 0

    _write_manifest(manifest_path, [operation_v2])
    second = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert second.exit_code == 0
    payload = json.loads(second.output)
    item = payload["items"][0]
    assert item["drift"]["changed"] is True
    assert item["drift"]["severity"] == "breaking"
    assert "required_param_added:region" in item["drift"]["changes"][0]["reasons"]
    assert payload["drift_summary"]["severity"] == "breaking"


def test_breaking_drift_freezes_mount_execution_by_default_policy(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
drift:
  defaults:
    on_breaking_change: freeze_mount
sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
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

    _write_manifest(
        manifest_path,
        [
            _cli_manifest_operation(
                "greet",
                {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            )
        ],
    )
    runner = CliRunner()
    first = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert first.exit_code == 0

    _write_manifest(
        manifest_path,
        [
            _cli_manifest_operation(
                "greet",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "region": {"type": "string"}},
                    "required": ["name", "region"],
                },
            )
        ],
    )
    second = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert second.exit_code == 0

    inspect_result = runner.invoke(main, ["--config", str(config_path), "manage", "inspect", "mount", "demo.greet", "--format", "json"])
    assert inspect_result.exit_code == 0
    inspect_payload = json.loads(inspect_result.output)
    assert inspect_payload["drift_state"]["status"] == "frozen"
    assert inspect_payload["drift_state"]["action"] == "freeze_mount"
    assert inspect_payload["drift_state"]["blocked"] is True

    help_result = runner.invoke(main, ["--config", str(config_path), "demo", "greet", "--help"])
    assert help_result.exit_code == 0
    assert "Drift status:" in help_result.output
    assert "status=frozen" in help_result.output

    invoke_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "invoke", "demo.greet", "--input-json", '{"name":"Alice","region":"cn"}', "--format", "json"],
    )
    assert invoke_result.exit_code == 5
    assert '"type": "PolicyError"' in invoke_result.output
    assert '"code": "mount_frozen_by_drift"' in invoke_result.output

    explain_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "explain", "demo.greet", "--input-json", '{"name":"Alice","region":"cn"}', "--format", "json"],
    )
    assert explain_result.exit_code == 0

    reconcile_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "reconcile", "drift", "demo_cli", "--format", "json"],
    )
    assert reconcile_result.exit_code == 0
    reconcile_payload = json.loads(reconcile_result.output)
    assert reconcile_payload["reconcile_action"] == "accept_breaking"
    assert reconcile_payload["source_drift_state"]["status"] == "accepted"
    assert reconcile_payload["mount_drift_states"][0]["status"] == "accepted"
    assert reconcile_payload["mount_drift_states"][0]["blocked"] is False

    invoke_after_reconcile = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "invoke", "demo.greet", "--input-json", '{"name":"Alice","region":"cn"}', "--format", "json"],
    )
    assert invoke_after_reconcile.exit_code == 0

    inspect_after_reconcile = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "inspect", "mount", "demo.greet", "--format", "json"],
    )
    assert inspect_after_reconcile.exit_code == 0
    assert json.loads(inspect_after_reconcile.output)["drift_state"]["status"] == "accepted"


def test_breaking_drift_can_require_manual_review_via_source_policy(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  cache_dir: {cache_dir}
  state_dir: {state_dir}
drift:
  defaults:
    on_breaking_change: freeze_mount
sources:
  demo_cli:
    type: cli
    executable: python3
    discovery:
      mode: manifest
      manifest: {manifest_path}
    drift_policy:
      on_breaking_change: require_manual_review
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

    _write_manifest(
        manifest_path,
        [
            _cli_manifest_operation(
                "greet",
                {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            )
        ],
    )
    runner = CliRunner()
    first = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert first.exit_code == 0

    _write_manifest(
        manifest_path,
        [
            _cli_manifest_operation(
                "greet",
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "region": {"type": "string"}},
                    "required": ["name", "region"],
                },
            )
        ],
    )
    second = runner.invoke(main, ["--config", str(config_path), "manage", "sync", "--format", "json"])
    assert second.exit_code == 0

    inspect_result = runner.invoke(main, ["--config", str(config_path), "manage", "inspect", "mount", "demo.greet", "--format", "json"])
    assert inspect_result.exit_code == 0
    inspect_payload = json.loads(inspect_result.output)
    assert inspect_payload["drift_state"]["status"] == "review_required"
    assert inspect_payload["drift_state"]["action"] == "require_manual_review"
    assert inspect_payload["drift_state"]["blocked"] is True

    invoke_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "invoke", "demo.greet", "--input-json", '{"name":"Alice","region":"cn"}', "--format", "json"],
    )
    assert invoke_result.exit_code == 5
    assert '"code": "mount_requires_drift_review"' in invoke_result.output

    inspect_drift_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "inspect", "drift", "demo_cli", "--format", "json"],
    )
    assert inspect_drift_result.exit_code == 0
    inspect_drift_payload = json.loads(inspect_drift_result.output)
    assert inspect_drift_payload["items"][0]["governance_state"]["status"] == "breaking"
    assert inspect_drift_payload["items"][0]["governance_state"]["affected_mount_count"] == 1
    assert inspect_drift_payload["items"][0]["governance_state"]["blocked_mount_count"] == 1
