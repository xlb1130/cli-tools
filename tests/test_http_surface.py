from pathlib import Path
from threading import Thread
import json
import time

import httpx
from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main
from cts.surfaces.http import create_http_server


ROOT = Path(__file__).resolve().parents[1]
DEMO_CONFIG = ROOT / "examples" / "demo" / "cts.yaml"
MANIFEST = ROOT / "examples" / "demo" / "echo-manifest.yaml"
PLUGIN_SOURCE = """
from cts.models import ExecutionPlan, HelpDescriptor, InvokeResult, OperationDescriptor


class EchoProvider:
    provider_type = "plugin_echo"

    def discover(self, source_name, source_config, app):
        operations = []
        for operation_id, operation in source_config.operations.items():
            operations.append(
                OperationDescriptor(
                    id=operation_id,
                    source=source_name,
                    provider_type=self.provider_type,
                    title=operation.title or operation_id,
                    stable_name=f"{source_name}.{operation_id}".replace("_", "."),
                    description=operation.description,
                    kind=operation.kind,
                    risk=operation.risk,
                    input_schema=dict(operation.input_schema),
                    output_schema=operation.output_schema,
                    examples=list(operation.examples),
                    supported_surfaces=list(operation.supported_surfaces),
                    provider_config=dict(operation.provider_config),
                )
            )
        return operations

    def get_operation(self, source_name, source_config, operation_id, app):
        return app.source_operations.get(source_name, {}).get(operation_id)

    def get_schema(self, source_name, source_config, operation_id, app):
        operation = self.get_operation(source_name, source_config, operation_id, app)
        if operation is None:
            return None
        return operation.input_schema, {"strategy": "declared", "origin": "plugin", "confidence": 1.0}

    def get_help(self, source_name, source_config, operation_id, app):
        operation = self.get_operation(source_name, source_config, operation_id, app)
        if operation is None:
            return None
        return HelpDescriptor(summary=operation.title, description=operation.description)

    def refresh_auth(self, source_name, source_config, app):
        return None

    def plan(self, source_name, source_config, request, app):
        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk="read",
            rendered_request={"provider": self.provider_type, "args": dict(request.args)},
        )

    def invoke(self, source_name, source_config, request, app):
        return InvokeResult(
            ok=True,
            status_code=0,
            data={"provider": self.provider_type, "args": dict(request.args)},
            metadata={"provider_type": self.provider_type},
        )

    def healthcheck(self, source_name, source_config, app):
        return {"ok": True, "provider_type": self.provider_type}


class Plugin:
    def __init__(self, plugin_name=None, config=None):
        self.plugin_name = plugin_name or "demo"
        self.config = config or {}

    def register_providers(self):
        return {"plugin_echo": EchoProvider()}

    def get_hook_handlers(self):
        return {
            "suffix_text": self.suffix_text,
            "append_help_note": self.append_help_note,
        }

    def suffix_text(self, ctx):
        payload = dict(ctx.payload)
        args = dict(payload.get("args", {}))
        if "text" in args:
            args["text"] = args["text"] + self.config.get("suffix", "")
        payload["args"] = args
        return payload

    def append_help_note(self, ctx):
        payload = dict(ctx.payload)
        help_payload = dict(payload.get("help", {}))
        description = help_payload.get("description") or ""
        note = self.config.get("help_note", "plugin hook active")
        help_payload["description"] = (description + "\\n\\n" + note).strip()
        payload["help"] = help_payload
        return payload
"""


def test_http_surface_readonly_routes():
    app = build_app(str(DEMO_CONFIG))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        summary = httpx.get(f"{base_url}/api/app/summary", timeout=5.0)
        assert summary.status_code == 200
        assert summary.json()["app"] == "cts"
        assert "reliability" in summary.json()

        sources = httpx.get(f"{base_url}/api/sources", timeout=5.0)
        assert sources.status_code == 200
        assert sources.json()["items"][0]["name"] == "demo_cli"

        reliability = httpx.get(f"{base_url}/api/reliability", timeout=5.0)
        assert reliability.status_code == 200
        reliability_payload = reliability.json()
        assert "status" in reliability_payload
        assert "rate_limits" in reliability_payload["status"]
        assert "concurrency" in reliability_payload["status"]
        assert "idempotency" in reliability_payload["status"]

        mounts = httpx.get(f"{base_url}/api/mounts?q=demo", timeout=5.0)
        assert mounts.status_code == 200
        assert mounts.json()["items"][0]["mount_id"] == "demo-echo"

        mount_detail = httpx.get(f"{base_url}/api/mounts/demo-echo", timeout=5.0)
        assert mount_detail.status_code == 200
        assert mount_detail.json()["stable_name"] == "demo.echo"

        source_detail = httpx.get(f"{base_url}/api/sources/demo_cli", timeout=5.0)
        assert source_detail.status_code == 200
        assert source_detail.json()["name"] == "demo_cli"

        source_test = httpx.post(
            f"{base_url}/api/sources/demo_cli/test",
            json={"discover": False},
            timeout=5.0,
        )
        assert source_test.status_code == 200
        assert source_test.json()["source"] == "demo_cli"
        assert "ok" in source_test.json()

        mount_help = httpx.get(f"{base_url}/api/mounts/demo-echo/help", timeout=5.0)
        assert mount_help.status_code == 200
        assert mount_help.json()["summary"] == "Echo structured JSON"

        explain = httpx.post(
            f"{base_url}/api/mounts/demo-echo/explain",
            json={"input": {"text": "hello"}},
            timeout=5.0,
        )
        assert explain.status_code == 200
        assert explain.json()["operation_id"] == "echo_json"

        invoke = httpx.post(
            f"{base_url}/api/mounts/demo-echo/invoke",
            json={"input": {"text": "hello"}},
            timeout=5.0,
        )
        assert invoke.status_code == 200
        assert invoke.json()["ok"] is True
        assert invoke.json()["operation_id"] == "echo_json"
        assert invoke.json()["run_id"]

        bad_explain = httpx.post(
            f"{base_url}/api/mounts/demo-echo/explain",
            json={"input": "not-an-object"},
            timeout=5.0,
        )
        assert bad_explain.status_code == 400
        assert bad_explain.json()["ok"] is False

        bad_invoke = httpx.post(
            f"{base_url}/api/mounts/demo-echo/invoke",
            json={"input": "not-an-object"},
            timeout=5.0,
        )
        assert bad_invoke.status_code == 400
        assert bad_invoke.json()["ok"] is False

        not_found = httpx.get(f"{base_url}/api/mounts/nope", timeout=5.0)
        assert not_found.status_code == 404
        assert not_found.json()["ok"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_exposes_auto_accepted_additive_drift(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    state_dir = tmp_path / "state"
    manifest_path = tmp_path / "manifest.json"
    config_path = tmp_path / "cts.yaml"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "operations": [
                    {
                        "id": "greet",
                        "title": "Greet",
                        "description": "Demo greet",
                        "risk": "read",
                        "input_schema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                        "argv_template": [
                            "python3",
                            "-c",
                            "import json,sys; print(json.dumps({'argv': sys.argv[1:]}))",
                            "{name}",
                        ],
                        "output": {"mode": "json"},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
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

    runner = CliRunner()
    first_sync = runner.invoke(main, ["--config", str(config_path), "sync", "--format", "json"])
    assert first_sync.exit_code == 0

    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "operations": [
                    {
                        "id": "greet",
                        "title": "Greet",
                        "description": "Demo greet",
                        "risk": "read",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "count": {"type": "integer", "default": 1},
                            },
                            "required": ["name"],
                        },
                        "argv_template": [
                            "python3",
                            "-c",
                            "import json,sys; print(json.dumps({'argv': sys.argv[1:]}))",
                            "{name}",
                        ],
                        "output": {"mode": "json"},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    second_sync = runner.invoke(main, ["--config", str(config_path), "sync", "--format", "json"])
    assert second_sync.exit_code == 0

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        drift_response = httpx.get(f"{base_url}/api/drift/demo_cli", timeout=5.0)
        assert drift_response.status_code == 200
        drift_payload = drift_response.json()
        assert drift_payload["source_drift_state"]["status"] == "accepted"
        assert drift_payload["source_drift_state"]["accepted_mount_count"] == 1

        catalog_response = httpx.get(f"{base_url}/api/catalog", timeout=5.0)
        assert catalog_response.status_code == 200
        catalog_payload = catalog_response.json()
        assert catalog_payload["drift_summary"]["severity"] == "additive"
        assert catalog_payload["mounts"][0]["drift_state"]["status"] == "accepted"
        assert catalog_payload["mounts"][0]["drift_state"]["action"] == "auto_accept"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_auto_reloads_when_config_changes(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        """version: 1
sources:
  demo:
    type: shell
    description: before
    operations:
      run:
        title: Run
        input_schema:
          type: object
mounts:
  - id: demo-run
    source: demo
    operation: run
    command:
      path: [demo, run]
""",
        encoding="utf-8",
    )

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        before = httpx.get(f"{base_url}/api/sources/demo", timeout=5.0)
        assert before.status_code == 200
        assert before.json()["description"] == "before"

        time.sleep(0.02)
        config_path.write_text(
            """version: 1
sources:
  demo:
    type: shell
    description: after
    operations:
      run:
        title: Run
        input_schema:
          type: object
mounts:
  - id: demo-run
    source: demo
    operation: run
    command:
      path: [demo, run]
""",
            encoding="utf-8",
        )

        after = httpx.get(f"{base_url}/api/sources/demo", timeout=5.0)
        assert after.status_code == 200
        assert after.json()["description"] == "after"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_management_routes_can_add_and_remove_source(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        """
version: 1
sources: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        create_response = httpx.post(
            f"{base_url}/api/sources",
            json={
                "provider_type": "cli",
                "source_name": "demo_cli",
                "description": "Demo source",
                "executable": "python3",
                "surfaces": ["cli", "invoke"],
            },
            timeout=5.0,
        )
        assert create_response.status_code == 200
        assert create_response.json()["source_name"] == "demo_cli"

        sources_response = httpx.get(f"{base_url}/api/sources", timeout=5.0)
        assert sources_response.status_code == 200
        assert any(item["name"] == "demo_cli" for item in sources_response.json()["items"])

        remove_response = httpx.post(f"{base_url}/api/sources/demo_cli/remove", json={"force": True}, timeout=5.0)
        assert remove_response.status_code == 200
        assert remove_response.json()["source_name"] == "demo_cli"

        sources_after = httpx.get(f"{base_url}/api/sources", timeout=5.0)
        assert sources_after.status_code == 200
        assert not any(item["name"] == "demo_cli" for item in sources_after.json()["items"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_runs_endpoints(tmp_path: Path):
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
        ["--config", str(config_path), "invoke", "demo-echo", "--input-json", '{"text":"hello"}', "--format", "json"],
    )
    assert invoke_result.exit_code == 0
    run_id = json.loads(invoke_result.output)["run_id"]

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        runs = httpx.get(f"{base_url}/api/runs", timeout=5.0)
        assert runs.status_code == 200
        assert runs.json()["items"][0]["run_id"] == run_id

        run_detail = httpx.get(f"{base_url}/api/runs/{run_id}", timeout=5.0)
        assert run_detail.status_code == 200
        assert run_detail.json()["mount_id"] == "demo-echo"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_exposes_extension_debug_inventory_and_events(tmp_path: Path):
    log_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    plugin_path = tmp_path / "demo_plugin.py"
    plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
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
plugins:
  demo:
    path: {plugin_path}
    config:
      suffix: "!"
      help_note: "Plugin hook note"
hooks:
  - event: help.after
    plugin: demo
    handler: append_help_note
  - event: explain.before
    plugin: demo
    handler: suffix_text
    when:
      mount_id: plugin-echo
sources:
  plugin_source:
    type: plugin_echo
    operations:
      echo:
        title: Plugin Echo
        description: Echo from plugin provider.
        input_schema:
          type: object
          properties:
            text:
              type: string
          required: [text]
mounts:
  - id: plugin-echo
    source: plugin_source
    operation: echo
    command:
      path: [plugin, echo]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        summary_response = httpx.get(f"{base_url}/api/extensions/summary", timeout=5.0)
        assert summary_response.status_code == 200
        summary_payload = summary_response.json()
        assert summary_payload["plugin_count"] == 1
        assert summary_payload["plugin_provider_count"] == 1
        assert summary_payload["enabled_hook_count"] == 2

        plugins_response = httpx.get(f"{base_url}/api/extensions/plugins", timeout=5.0)
        assert plugins_response.status_code == 200
        plugins_payload = plugins_response.json()
        assert plugins_payload["items"][0]["name"] == "demo"
        assert plugins_payload["items"][0]["provider_types"][0]["provider_type"] == "plugin_echo"

        providers_response = httpx.get(f"{base_url}/api/extensions/providers", timeout=5.0)
        assert providers_response.status_code == 200
        providers_payload = providers_response.json()
        plugin_provider = next(item for item in providers_payload["items"] if item["provider_type"] == "plugin_echo")
        assert plugin_provider["owner_type"] == "plugin"
        assert plugin_provider["owner_name"] == "demo"
        assert plugin_provider["mount_count"] == 1

        hooks_response = httpx.get(f"{base_url}/api/extensions/hooks?plugin=demo", timeout=5.0)
        assert hooks_response.status_code == 200
        hooks_payload = hooks_response.json()
        assert len(hooks_payload["items"]) == 2
        assert hooks_payload["items"][0]["plugin"] == "demo"

        contracts_response = httpx.get(f"{base_url}/api/extensions/contracts", timeout=5.0)
        assert contracts_response.status_code == 200
        contracts_payload = contracts_response.json()
        explain_contract = next(item for item in contracts_payload["items"] if item["event"] == "explain.before")
        assert "args" in [field["name"] for field in explain_contract["payload_fields"]]
        assert "runtime" in explain_contract["may_mutate"]
        assert explain_contract["sample_payload"]["args"]["text"] == "hello"
        assert explain_contract["simulation"]["risk_level"] == "low"

        help_response = httpx.get(f"{base_url}/api/mounts/plugin-echo/help", timeout=5.0)
        assert help_response.status_code == 200
        assert "Plugin hook note" in help_response.json()["description"]

        explain_response = httpx.post(
            f"{base_url}/api/mounts/plugin-echo/explain",
            json={"input": {"text": "hello"}},
            timeout=5.0,
        )
        assert explain_response.status_code == 200
        assert explain_response.json()["plan"]["normalized_args"]["text"] == "hello!"

        hook_explain_response = httpx.post(
            f"{base_url}/api/extensions/hooks/explain",
            json={
                "event": "explain.before",
                "mount_id": "plugin-echo",
                "payload": {"args": {"text": "hello"}, "runtime": {}},
            },
            timeout=5.0,
        )
        assert hook_explain_response.status_code == 200
        hook_explain_payload = hook_explain_response.json()
        assert hook_explain_payload["context"]["mount_id"] == "plugin-echo"
        assert hook_explain_payload["hooks"][0]["matched"] is True
        assert hook_explain_payload["hooks"][0]["criteria"][0]["key"] == "mount_id"
        assert hook_explain_payload["hooks"][0]["criteria"][0]["matched"] is True

        hook_simulate_response = httpx.post(
            f"{base_url}/api/extensions/hooks/simulate",
            json={
                "event": "explain.before",
                "mount_id": "plugin-echo",
                "payload": {"args": {"text": "hello"}, "runtime": {}},
                "execute_handlers": True,
            },
            timeout=5.0,
        )
        assert hook_simulate_response.status_code == 200
        hook_simulate_payload = hook_simulate_response.json()
        assert hook_simulate_payload["execute_handlers"] is True
        assert hook_simulate_payload["simulation"]["provider_calls_blocked"] is True
        assert hook_simulate_payload["simulation"]["mount_execution_blocked"] is True
        assert hook_simulate_payload["steps"][0]["status"] == "applied"
        assert hook_simulate_payload["final_payload"]["args"]["text"] == "hello!"

        events_response = httpx.get(f"{base_url}/api/extensions/events?limit=20", timeout=5.0)
        assert events_response.status_code == 200
        events_payload = events_response.json()
        event_names = [item["event"] for item in events_payload["items"]]
        assert "hook_dispatch_start" in event_names
        assert "hook_dispatch_complete" in event_names
        hook_event = next(item for item in events_payload["items"] if item["event"] == "hook_dispatch_start")
        assert hook_event["data"]["plugin"] == "demo"
        assert hook_event["mount_id"] == "plugin-echo"
        assert events_payload["next_before_ts"] is not None

        filtered_events_response = httpx.get(
            f"{base_url}/api/extensions/events?plugin=demo&event=hook_dispatch_start&mount_id=plugin-echo&limit=5",
            timeout=5.0,
        )
        assert filtered_events_response.status_code == 200
        filtered_events_payload = filtered_events_response.json()
        assert filtered_events_payload["filters"]["plugin"] == "demo"
        assert filtered_events_payload["filters"]["event"] == "hook_dispatch_start"
        assert all(item["event"] == "hook_dispatch_start" for item in filtered_events_payload["items"])
        assert all(item["mount_id"] == "plugin-echo" for item in filtered_events_payload["items"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_can_serve_static_ui(tmp_path: Path):
    ui_dir = tmp_path / "dist"
    assets_dir = ui_dir / "assets"
    assets_dir.mkdir(parents=True)
    (ui_dir / "index.html").write_text("<!doctype html><html><body>cts ui</body></html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('cts')", encoding="utf-8")

    app = build_app(str(DEMO_CONFIG))
    server = create_http_server(app, host="127.0.0.1", port=0, ui_dir=ui_dir)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        index_response = httpx.get(f"{base_url}/", timeout=5.0)
        assert index_response.status_code == 200
        assert "cts ui" in index_response.text

        asset_response = httpx.get(f"{base_url}/assets/app.js", timeout=5.0)
        assert asset_response.status_code == 200
        assert "console.log" in asset_response.text

        spa_route_response = httpx.get(f"{base_url}/mounts/demo-echo", timeout=5.0)
        assert spa_route_response.status_code == 200
        assert "cts ui" in spa_route_response.text
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_explain_not_found_returns_404():
    app = build_app(str(DEMO_CONFIG))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        response = httpx.post(f"{base_url}/api/mounts/no-such-mount/explain", json={"input": {}}, timeout=5.0)
        assert response.status_code == 404
        assert response.json()["ok"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_sync_and_reload_actions(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  default_profile: dev
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

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        sync_response = httpx.post(f"{base_url}/api/sync", json={}, timeout=5.0)
        assert sync_response.status_code == 200
        assert sync_response.json()["action"] == "sync"
        assert sync_response.json()["ok"] is True

        config_path.write_text(
            f"""
version: 1
app:
  default_profile: dev
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
  - id: demo-echo-2
    source: demo_cli
    operation: echo_json
    command:
      path: [demo, echo2]
    machine:
      stable_name: demo.echo2
""".strip()
            + "\n",
            encoding="utf-8",
        )

        reload_response = httpx.post(f"{base_url}/api/reload", json={}, timeout=5.0)
        assert reload_response.status_code == 200
        assert reload_response.json()["action"] == "reload"
        assert reload_response.json()["summary"]["mount_count"] == 2

        mounts_response = httpx.get(f"{base_url}/api/mounts", timeout=5.0)
        assert mounts_response.status_code == 200
        assert len(mounts_response.json()["items"]) == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_surface_exposes_drift_and_catalog_governance(tmp_path: Path):
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

    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "operations": [
                    {
                        "id": "greet",
                        "title": "Greet",
                        "description": "Demo greet",
                        "risk": "read",
                        "input_schema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                        "argv_template": [
                            "python3",
                            "-c",
                            "import json,sys; print(json.dumps({'argv': sys.argv[1:]}))",
                            "{name}",
                        ],
                        "output": {"mode": "json"},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    first_sync = runner.invoke(main, ["--config", str(config_path), "sync", "--format", "json"])
    assert first_sync.exit_code == 0

    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "operations": [
                    {
                        "id": "greet",
                        "title": "Greet",
                        "description": "Demo greet",
                        "risk": "read",
                        "input_schema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}, "region": {"type": "string"}},
                            "required": ["name", "region"],
                        },
                        "argv_template": [
                            "python3",
                            "-c",
                            "import json,sys; print(json.dumps({'argv': sys.argv[1:]}))",
                            "{name}",
                        ],
                        "output": {"mode": "json"},
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    second_sync = runner.invoke(main, ["--config", str(config_path), "sync", "--format", "json"])
    assert second_sync.exit_code == 0

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        drift_response = httpx.get(f"{base_url}/api/drift/demo_cli", timeout=5.0)
        assert drift_response.status_code == 200
        drift_payload = drift_response.json()
        assert drift_payload["source_drift_state"]["blocked_mount_count"] == 1
        assert "demo.greet" in drift_payload["source_drift_state"]["affected_mount_ids"]

        catalog_response = httpx.get(f"{base_url}/api/catalog", timeout=5.0)
        assert catalog_response.status_code == 200
        catalog_payload = catalog_response.json()
        assert catalog_payload["drift_summary"]["severity"] == "breaking"
        assert catalog_payload["mounts"][0]["drift_state"]["status"] == "frozen"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
