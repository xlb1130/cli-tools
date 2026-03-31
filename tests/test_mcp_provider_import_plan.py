from pathlib import Path

from cts.app import build_app
from cts.imports.models import ImportRequest
from cts.providers.mcp_cli import MCPCLIProvider, build_mcp_group_help, build_mcp_group_help_from_discovery


def test_mcp_unified_import_group_help_is_not_generic(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text("version: 1\n", encoding="utf-8")
    app = build_app(str(config_path))

    plan = MCPCLIProvider().plan_import(
        ImportRequest(
            provider_type="mcp",
            source_name="coop",
            values={
                "source_name": "coop",
                "server_name": "coop-server",
                "__target_dir__": str(tmp_path),
            },
        ),
        app,
    )

    group_help = plan.source_patch["imported_cli_groups"][0]
    assert group_help["summary"] == "MCP tools for 'coop' from 'coop-server'"
    assert group_help["description"] == "Tools imported from MCP source 'coop' using server 'coop-server'."
    assert group_help["summary"] != "Imported MCP tools"


def test_build_mcp_group_help_prefers_server_instructions():
    group_help = build_mcp_group_help(
        "coop",
        "coop-server",
        server_info={"name": "Alibaba Coop"},
        instructions="Alibaba Coop MCP\nProject and workitem collaboration tools.",
    )

    assert group_help["summary"] == "Alibaba Coop MCP"
    assert group_help["description"] == "Alibaba Coop MCP\nProject and workitem collaboration tools."


def test_build_mcp_group_help_from_discovery_uses_sync_metadata():
    group_help = build_mcp_group_help_from_discovery(
        "coop",
        {"server": "coop-server"},
        {
            "ok": True,
            "server_info": {"name": "Alibaba Coop"},
            "instructions": "Alibaba Coop MCP",
        },
    )

    assert group_help["summary"] == "Alibaba Coop MCP"
    assert group_help["description"] == "Alibaba Coop MCP"
