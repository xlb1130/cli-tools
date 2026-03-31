from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main
from cts.models import InvokeRequest, OperationDescriptor
from cts.providers import mcp_cli


def test_mcp_bridge_script_path_exists():
    assert mcp_cli._bridge_script_path().exists()


def test_bridge_launch_script_path_prefers_existing_node_modules(tmp_path: Path):
    repo_root = tmp_path / "repo"
    script_dir = repo_root / "scripts"
    node_pkg_dir = repo_root / "node_modules" / "@modelcontextprotocol" / "sdk"
    script_dir.mkdir(parents=True)
    node_pkg_dir.mkdir(parents=True)
    script_path = script_dir / "mcp_bridge.mjs"
    script_path.write_text("console.log('ok')\n", encoding="utf-8")

    assert mcp_cli._bridge_dependency_available(script_path) is True
    assert mcp_cli._find_bridge_dependency_dir(script_path) == repo_root


def test_bridge_launch_script_path_bootstraps_runtime(tmp_path: Path, monkeypatch):
    source_dir = tmp_path / "site-packages" / "cts" / "scripts"
    source_dir.mkdir(parents=True)
    script_path = source_dir / "mcp_bridge.mjs"
    script_path.write_text("console.log('bridge')\n", encoding="utf-8")
    (source_dir / "package.json").write_text(
        '{"private":true,"type":"module","dependencies":{"@modelcontextprotocol/sdk":"^1.28.0"}}\n',
        encoding="utf-8",
    )
    runtime_dir = tmp_path / "runtime"
    calls = []

    def fake_run(argv, cwd, capture_output, text, check):
        calls.append((argv, Path(cwd)))
        (Path(cwd) / "node_modules" / "@modelcontextprotocol" / "sdk").mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mcp_cli, "_bridge_script_path", lambda: script_path)
    monkeypatch.setattr(mcp_cli, "_bridge_runtime_root", lambda: runtime_dir)
    monkeypatch.setattr(mcp_cli.shutil, "which", lambda cmd: "/usr/bin/npm" if cmd == "npm" else None)
    monkeypatch.setattr(mcp_cli.subprocess, "run", fake_run)

    launch_script = mcp_cli._bridge_launch_script_path()

    assert launch_script == runtime_dir / "mcp_bridge.mjs"
    assert launch_script.exists()
    assert (runtime_dir / "package.json").exists()
    assert calls == [(['/usr/bin/npm', 'install', '--no-audit', '--no-fund', '--omit=dev'], runtime_dir)]


def test_mcp_live_discovery_compiles_generated_mounts(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        """
version: 1
sources:
  remote_mcp:
    type: mcp
    config_file: ./servers.json
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

    def fake_bridge(source_config, app, command, primitive_type=None, target=None, args=None, timeout_seconds=None):
        assert command == "list-primitives"
        return {
            "ok": True,
            "server": "demo",
            "transport_type": "streamable_http",
            "primitives": [
                {
                    "primitive_type": "tool",
                    "name": "bing_search",
                    "description": "search",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
                {
                    "primitive_type": "tool",
                    "name": "crawl_webpage",
                    "description": "crawl",
                    "input_schema": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            ],
        }

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fake_bridge)

    app = build_app(str(config_path))
    mounts = {mount.mount_id: mount for mount in app.catalog.mounts}

    assert "demo.bing_search" in mounts
    assert "demo.crawl_webpage" in mounts
    assert mounts["demo.bing_search"].command_path == ["demo", "bing", "search"]
    assert mounts["demo.crawl_webpage"].command_path == ["demo", "crawl", "webpage"]


def test_mcp_help_uses_manifest_without_live_discovery(tmp_path: Path, monkeypatch):
    manifest_path = tmp_path / "mcp-manifest.json"
    config_path = tmp_path / "cts.yaml"
    manifest_path.write_text(
        """
{
  "version": 1,
  "operations": [
    {
      "id": "bing_search",
      "title": "Bing Search",
      "description": "Search from imported MCP manifest",
      "risk": "read",
      "input_schema": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
      },
      "provider_config": {
        "mcp_primitive_type": "tool",
        "discovered_origin": "demo"
      }
    }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config_path.write_text(
        f"""
version: 1
sources:
  remote_mcp:
    type: mcp
    config_file: ./servers.json
    server: demo
    discovery:
      mode: live
      manifest: {manifest_path}
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

    def fail_bridge(*args, **kwargs):
        calls["count"] += 1
        raise AssertionError("live MCP discovery should not run for --help when manifest data exists")

    monkeypatch.setattr(mcp_cli, "_run_bridge_command", fail_bridge)

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(config_path), "demo", "bing", "search", "--help"])

    assert result.exit_code == 0
    assert calls["count"] == 0
    assert "Search from imported MCP manifest" in result.output
    assert "--query TEXT" in result.output


def test_mcp_invoke_falls_back_to_node_bridge_on_cli_server_parse_error(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"
    servers_path = tmp_path / "servers.json"
    servers_path.write_text('{"mcpServers":{"demo":{"command":"demo-server"}}}\n', encoding="utf-8")
    config_path.write_text(
        """
version: 1
sources:
  remote_mcp:
    type: mcp
    config_file: ./servers.json
    server: demo
    operations:
      query_recent_workitem_list:
        title: Query Recent Workitem List
        description: Query workitems from MCP
        provider_config:
          mcp_primitive_type: tool
mounts: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app = build_app(str(config_path))
    app.source_operations["remote_mcp"] = {
        "query_recent_workitem_list": OperationDescriptor(
            id="query_recent_workitem_list",
            source="remote_mcp",
            provider_type="mcp",
            title="Query Recent Workitem List",
            description="Query workitems from MCP",
            kind="action",
            risk="read",
            input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
            provider_config={"mcp_primitive_type": "tool"},
        )
    }
    provider = mcp_cli.MCPCLIProvider()
    calls = []

    def fake_run(argv, capture_output, text, timeout, check):
        calls.append(list(argv))
        if argv[0] == "mcp-cli":
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr='Error [SERVER_NOT_FOUND]: Server "call-tool" not found in config\nAvailable servers: demo',
            )
        return SimpleNamespace(
            returncode=0,
            stdout='{"ok": true, "result": {"items": [1, 2, 3]}}\n',
            stderr="",
        )

    monkeypatch.setattr(mcp_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(mcp_cli, "_resolve_mcp_cli_binary", lambda source_config: "mcp-cli")
    monkeypatch.setattr(mcp_cli, "_build_bridge_argv", lambda *args, **kwargs: ["node", "bridge.mjs", "call-tool"])

    result = provider.invoke(
        "remote_mcp",
        app.config.sources["remote_mcp"],
        InvokeRequest(source="remote_mcp", operation_id="query_recent_workitem_list", args={"limit": 10}),
        app,
    )

    assert result.ok is True
    assert result.data == {"items": [1, 2, 3]}
    assert result.metadata["strategy"] == "node-bridge"
    assert calls[0][:4] == ["mcp-cli", "-c", str(servers_path), "call-tool"]
    assert calls[1] == ["node", "bridge.mjs", "call-tool"]
