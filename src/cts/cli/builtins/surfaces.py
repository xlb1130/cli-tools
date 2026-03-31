from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Callable, Optional

import click

from cts.cli.lazy import (
    build_app_summary,
    build_reliability_status,
    build_source_check_result,
    create_http_server,
    default_ui_dist_dir,
    render_payload,
)
from cts.execution.errors import RegistryError


def register_surface_commands(
    manage_group,
    *,
    pass_app,
    fail: Callable,
    progress_steps: Callable,
) -> None:
    @manage_group.group()
    def serve() -> None:
        """Northbound surface commands."""

    def resolve_http_ui_dir(ctx: click.Context, serve_ui: bool, ui_dir: Optional[Path]) -> Optional[Path]:
        if ui_dir is not None:
            return ui_dir.resolve()
        if not serve_ui:
            return None

        candidate = default_ui_dist_dir()
        if not candidate.exists():
            fail(
                ctx,
                RegistryError(
                    f"ui dist directory not found: {candidate}",
                    code="ui_dist_not_found",
                    suggestions=["先在 frontend/app 下执行 `npm run build`，或显式传入 `--ui-dir`。"],
                ),
                "serve_http",
                "json",
            )
            return None
        return candidate.resolve()

    def serve_http_surface(
        app,
        host: str,
        port: int,
        serve_ui: bool,
        ui_dir: Optional[Path],
        open_browser: bool,
        output_format: str,
    ) -> None:
        ctx = click.get_current_context()
        resolved_ui_dir = resolve_http_ui_dir(ctx, serve_ui=serve_ui, ui_dir=ui_dir)
        if serve_ui and resolved_ui_dir is None:
            return

        server = create_http_server(app, host=host, port=port, ui_dir=resolved_ui_dir)
        actual_host, actual_port = server.server_address
        base_url = f"http://{actual_host}:{actual_port}"
        browser_url = base_url if resolved_ui_dir is not None else f"{base_url}/api/app/summary"
        click.echo(
            render_payload(
                {
                    "ok": True,
                    "surface": "http",
                    "base_url": base_url,
                    "browser_url": browser_url,
                    "ui_enabled": resolved_ui_dir is not None,
                    "ui_dir": str(resolved_ui_dir) if resolved_ui_dir else None,
                    "next_command": f"curl {base_url}/api/app/summary",
                },
                output_format,
            )
        )
        if open_browser:
            try:
                webbrowser.open(browser_url)
            except Exception:
                pass
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

    @serve.command("http")
    @click.option("--host", default="127.0.0.1", show_default=True)
    @click.option("--port", type=int, default=8787, show_default=True)
    @click.option("--ui", "serve_ui", is_flag=True, help="Also serve the built frontend UI if available.")
    @click.option("--ui-dir", type=click.Path(path_type=Path, file_okay=False), default=None, help="Explicit frontend dist directory.")
    @click.option("--open", "open_browser", is_flag=True, help="Open the server URL in the default browser after startup.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def serve_http_command(app, host: str, port: int, serve_ui: bool, ui_dir: Optional[Path], open_browser: bool, output_format: str) -> None:
        serve_http_surface(
            app,
            host=host,
            port=port,
            serve_ui=serve_ui,
            ui_dir=ui_dir,
            open_browser=open_browser,
            output_format=output_format,
        )

    @manage_group.command("ui")
    @click.option("--host", default="127.0.0.1", show_default=True)
    @click.option("--port", type=int, default=8787, show_default=True)
    @click.option("--ui-dir", type=click.Path(path_type=Path, file_okay=False), default=None, help="Explicit frontend dist directory.")
    @click.option("--open", "open_browser", is_flag=True, help="Open the UI in the default browser after startup.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def ui_command(app, host: str, port: int, ui_dir: Optional[Path], open_browser: bool, output_format: str) -> None:
        """Start the HTTP API together with the bundled frontend UI."""
        serve_http_surface(
            app,
            host=host,
            port=port,
            serve_ui=True,
            ui_dir=ui_dir,
            open_browser=open_browser,
            output_format=output_format,
        )

    @serve.command("jsonrpc")
    @click.option("--host", default="127.0.0.1", show_default=True)
    @click.option("--port", type=int, default=8788, show_default=True)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def serve_jsonrpc_command(app, host: str, port: int, output_format: str) -> None:
        """Start JSON-RPC 2.0 server for CTS API."""
        from cts.surfaces.jsonrpc import serve_jsonrpc

        click.echo(
            render_payload(
                {
                    "ok": True,
                    "surface": "jsonrpc",
                    "base_url": f"http://{host}:{port}",
                    "next_command": f"curl -X POST http://{host}:{port}",
                },
                output_format,
            )
        )
        serve_jsonrpc(app, host=host, port=port)

    @serve.command("mcp")
    @click.option("--host", default="127.0.0.1", show_default=True)
    @click.option("--port", type=int, default=8789, show_default=True)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def serve_mcp_command(app, host: str, port: int, output_format: str) -> None:
        """Start MCP (Model Context Protocol) server exposing CTS mounts as tools."""
        from cts.surfaces.mcp import serve_mcp

        click.echo(
            render_payload(
                {
                    "ok": True,
                    "surface": "mcp",
                    "base_url": f"http://{host}:{port}",
                    "tools_count": len([m for m in app.catalog.mounts if "mcp" in getattr(m, "supported_surfaces", ["invoke"])]),
                    "next_command": f"Use this URL in your MCP client: http://{host}:{port}",
                },
                output_format,
            )
        )
        serve_mcp(app, host=host, port=port)

    @manage_group.command(
        help="Run health, config, and runtime diagnostics.",
        short_help="Run health, config, and runtime diagnostics.",
    )
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.option("--compatibility", is_flag=True, help="Also run compatibility checks.")
    @click.option("--auth", "check_auth", is_flag=True, help="Also validate auth profiles.")
    @pass_app
    def doctor(app, output_format: str, compatibility: bool, check_auth: bool) -> None:
        steps = ["Run source checks", "Build runtime summary"]
        if compatibility:
            steps.append("Run compatibility checks")
        if check_auth:
            steps.append("Validate auth profiles")
        with progress_steps(output_format, "Running doctor", steps) as progress:
            progress.advance("Running source checks")
            checks = [build_source_check_result(app, source_name, source) for source_name, source in app.config.sources.items()]
            progress.advance("Building runtime summary")
            summary = build_app_summary(app)
            payload = {
                "config_paths": [str(path) for path in app.config_paths],
                "conflicts": app.catalog.conflicts,
                "plugin_provider_conflicts": summary["plugin_provider_conflicts"],
                "discovery_errors": app.discovery_errors,
                "checks": checks,
                "runtime_paths": summary["runtime_paths"],
                "reliability": build_reliability_status(app),
            }

            if compatibility:
                from cts.config.compatibility import doctor_compatibility

                progress.advance("Running compatibility checks")
                payload["compatibility"] = doctor_compatibility(app)

            if check_auth:
                progress.advance("Validating auth profiles")
                payload["auth"] = app.auth_manager.validate_all()

        click.echo(render_payload(payload, output_format))
