import json
from pathlib import Path
from threading import Thread

import httpx
from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main
from cts.surfaces.http import create_http_server


def test_auth_cli_workflow_and_http_surface_inventory(tmp_path: Path):
    state_dir = tmp_path / "state"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  state_dir: {state_dir}
auth_profiles:
  demo:
    type: bearer
    source: session
sources:
  secured_http:
    type: http
    base_url: https://api.example.com
    auth_ref: demo
    operations:
      ping:
        title: Ping
        input_schema:
          type: object
          properties: {{}}
        provider_config:
          method: GET
          path: /ping
mounts:
  - id: secure-ping
    source: secured_http
    operation: ping
    command:
      path: [secure, ping]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()

    status_before = runner.invoke(main, ["--config", str(config_path), "manage", "auth", "status", "demo", "--format", "json"])
    assert status_before.exit_code == 0
    assert json.loads(status_before.output)["state"] == "configured"

    login_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage", "auth",
            "login",
            "demo",
            "--token",
            "super-secret-token",
            "--refresh-token",
            "refresh-secret",
            "--expires-at",
            "2099-01-01T00:00:00+00:00",
            "--format",
            "json",
        ],
    )
    assert login_result.exit_code == 0
    login_payload = json.loads(login_result.output)
    assert login_payload["profile"]["state"] == "active"
    assert login_payload["profile"]["session"]["access_token"] == "***"
    assert login_payload["profile"]["session"]["refresh_token"] == "***"
    assert login_payload["profile"]["resolved_credentials"]["present"] is True
    assert "super-secret-token" not in login_result.output

    dry_run_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "secure",
            "ping",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert dry_run_result.exit_code == 0
    dry_run_payload = json.loads(dry_run_result.output)
    assert dry_run_payload["data"]["plan"]["rendered_request"]["headers"]["Authorization"] == "***"
    assert "super-secret-token" not in dry_run_result.output

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        inventory_response = httpx.get(f"{base_url}/api/auth/profiles", timeout=5.0)
        assert inventory_response.status_code == 200
        inventory_payload = inventory_response.json()
        assert inventory_payload["summary"]["profile_count"] == 1
        assert inventory_payload["items"][0]["name"] == "demo"
        assert inventory_payload["items"][0]["state"] == "active"

        detail_response = httpx.get(f"{base_url}/api/auth/profiles/demo", timeout=5.0)
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["source_names"] == ["secured_http"]
        assert detail_payload["session"]["access_token"] == "***"

        sources_response = httpx.get(f"{base_url}/api/sources", timeout=5.0)
        assert sources_response.status_code == 200
        source_payload = sources_response.json()["items"][0]
        assert source_payload["auth"]["state"] == "active"
        assert source_payload["health"]["auth"]["state"] == "active"

        logout_response = httpx.post(f"{base_url}/api/auth/logout", json={"name": "demo"}, timeout=5.0)
        assert logout_response.status_code == 200
        assert logout_response.json()["profile"]["state"] == "revoked"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_auth_manager_refresh_updates_session(tmp_path: Path):
    state_dir = tmp_path / "state"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  state_dir: {state_dir}
auth_profiles:
  demo:
    type: bearer
    source: session
sources:
  secured_http:
    type: http
    base_url: https://api.example.com
    auth_ref: demo
    operations:
      ping:
        title: Ping
        input_schema:
          type: object
          properties: {{}}
        provider_config:
          method: GET
          path: /ping
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app = build_app(str(config_path))
    app.auth_manager.login("demo", token="old-token", refresh_token="refresh-token")

    provider = app.provider_registry.get("http")

    def fake_refresh(source_name, source_config, current_app):
        assert source_name == "secured_http"
        assert current_app is app
        return {
            "access_token": "fresh-token",
            "refresh_token": "fresh-refresh",
            "expires_at": "2099-01-02T00:00:00+00:00",
        }

    provider.refresh_auth = fake_refresh

    payload = app.auth_manager.refresh("demo")
    assert payload["state"] == "active"
    assert payload["session"]["access_token"] == "***"
    assert payload["session"]["refresh_token"] == "***"

    sessions = app.auth_manager._load_sessions()
    assert sessions["demo"]["access_token"] == "fresh-token"
    assert sessions["demo"]["refresh_token"] == "fresh-refresh"


def test_auth_status_env_profile_is_active_and_redacted(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        """
version: 1
auth_profiles:
  env_demo:
    type: bearer
    source: env
    token_env: DEMO_BEARER_TOKEN
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEMO_BEARER_TOKEN", "env-secret-token")

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(config_path), "manage", "auth", "status", "env_demo", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["state"] == "active"
    assert payload["resolved_credentials"]["type"] == "bearer"
    assert payload["resolved_credentials"]["present"] is True
    assert "env-secret-token" not in result.output


def test_secret_inventory_and_secret_backed_auth_profile(tmp_path: Path):
    state_dir = tmp_path / "state"
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
app:
  state_dir: {state_dir}
secrets:
  github_token:
    provider: literal
    value: gh-secret-token
auth_profiles:
  github:
    type: bearer
    source: secret
    secret_ref: github_token
sources:
  github_http:
    type: http
    base_url: https://api.example.com
    auth_ref: github
    operations:
      whoami:
        title: Who Am I
        input_schema:
          type: object
          properties: {{}}
        provider_config:
          method: GET
          path: /me
mounts:
  - id: github-me
    source: github_http
    operation: whoami
    command:
      path: [github, me]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()

    secret_list = runner.invoke(main, ["--config", str(config_path), "manage", "secret", "list", "--format", "json"])
    assert secret_list.exit_code == 0
    secret_list_payload = json.loads(secret_list.output)
    assert secret_list_payload["summary"]["secret_count"] == 1
    assert secret_list_payload["items"][0]["state"] == "active"
    assert secret_list_payload["items"][0]["config"]["value"] == "***"
    assert "gh-secret-token" not in secret_list.output

    secret_show = runner.invoke(main, ["--config", str(config_path), "manage", "secret", "show", "github_token", "--format", "json"])
    assert secret_show.exit_code == 0
    secret_show_payload = json.loads(secret_show.output)
    assert secret_show_payload["value_present"] is True
    assert secret_show_payload["config"]["value"] == "***"

    auth_status = runner.invoke(main, ["--config", str(config_path), "manage", "auth", "status", "github", "--format", "json"])
    assert auth_status.exit_code == 0
    auth_payload = json.loads(auth_status.output)
    assert auth_payload["state"] == "active"
    assert auth_payload["reason"] == "secret_credentials_available"

    dry_run = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "github",
            "me",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert dry_run.exit_code == 0
    dry_run_payload = json.loads(dry_run.output)
    assert dry_run_payload["data"]["plan"]["rendered_request"]["headers"]["Authorization"] == "***"
    assert "gh-secret-token" not in dry_run.output

    app = build_app(str(config_path))
    server = create_http_server(app, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"

        inventory_response = httpx.get(f"{base_url}/api/secrets", timeout=5.0)
        assert inventory_response.status_code == 200
        inventory_payload = inventory_response.json()
        assert inventory_payload["summary"]["active_count"] == 1
        assert inventory_payload["items"][0]["config"]["value"] == "***"

        detail_response = httpx.get(f"{base_url}/api/secrets/github_token", timeout=5.0)
        assert detail_response.status_code == 200
        assert detail_response.json()["state"] == "active"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_request_supports_secret_ref_in_headers_query_and_body(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        """
version: 1
secrets:
  tenant_id:
    provider: literal
    value: tenant-secret
  trace_token:
    provider: literal
    value: trace-secret
  body_token:
    provider: literal
    value: body-secret
  query_token:
    provider: literal
    value: query-secret
sources:
  secured_http:
    type: http
    base_url: https://api.example.com
    headers:
      X-Tenant-Id:
        secret_ref: tenant_id
    operations:
      create_item:
        title: Create Item
        input_schema:
          type: object
          properties:
            name:
              type: string
            secret_token:
              type: object
              default:
                secret_ref: body_token
          required: [name]
        provider_config:
          method: POST
          path: /items
          headers:
            X-Trace-Token:
              secret_ref: trace_token
          body_fields: [name, secret_token]
      search_items:
        title: Search Items
        input_schema:
          type: object
          properties:
            q:
              type: string
            api_token:
              type: object
              default:
                secret_ref: query_token
          required: [q]
        provider_config:
          method: GET
          path: /items/search
mounts:
  - id: create-item
    source: secured_http
    operation: create_item
    command:
      path: [items, create]
  - id: search-items
    source: secured_http
    operation: search_items
    command:
      path: [items, search]
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
            "manage", "invoke",
            "create-item",
            "--input-json",
            '{"name":"demo"}',
            "--dry-run",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    request = payload["data"]["plan"]["rendered_request"]
    assert request["headers"]["X-Tenant-Id"] == "***"
    assert request["headers"]["X-Trace-Token"] == "***"
    assert request["json"]["name"] == "demo"
    assert request["json"]["secret_token"] == "***"
    assert "tenant-secret" not in result.output
    assert "trace-secret" not in result.output
    assert "body-secret" not in result.output

    search_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage", "invoke",
            "search-items",
            "--input-json",
            '{"q":"demo"}',
            "--dry-run",
            "--format",
            "json",
        ],
    )
    assert search_result.exit_code == 0
    search_payload = json.loads(search_result.output)
    search_request = search_payload["data"]["plan"]["rendered_request"]
    assert search_request["params"]["q"] == "demo"
    assert search_request["params"]["api_token"] == "***"
    assert "query-secret" not in search_result.output
