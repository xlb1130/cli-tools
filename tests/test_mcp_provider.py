from pathlib import Path

from cts.app import build_app
from cts.providers import mcp_cli


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
