from __future__ import annotations

from typing import Callable, Optional

import click

from cts.cli.lazy import build_mount_details, build_source_details, render_payload
from cts.execution.errors import RegistryError


def register_inspect_commands(
    inspect_group,
    *,
    pass_app,
    fail: Callable,
    path_to_str: Callable,
) -> None:
    @inspect_group.command(name="mount", help="Inspect the compiled details of a mount.", short_help="Inspect the compiled details of a mount.")
    @click.argument("mount_id")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def inspect_mount(app, mount_id: str, output_format: str) -> None:
        mount = app.catalog.find_by_id(mount_id)
        if not mount:
            fail(click.get_current_context(), RegistryError(f"mount not found: {mount_id}", code="mount_not_found"), "inspect_mount", output_format)
            return
        click.echo(render_payload(build_mount_details(app, mount), output_format))

    @inspect_group.command(name="source", help="Inspect the compiled details of a source.", short_help="Inspect the compiled details of a source.")
    @click.argument("source_name")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def inspect_source(app, source_name: str, output_format: str) -> None:
        source = app.config.sources.get(source_name)
        if not source:
            fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "inspect_source", output_format)
            return
        click.echo(render_payload(build_source_details(app, source_name, source), output_format))

    @inspect_group.command(name="operation", help="Inspect a compiled operation and schema provenance.", short_help="Inspect a compiled operation and schema provenance.")
    @click.argument("source_name")
    @click.argument("operation_id")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def inspect_operation(app, source_name: str, operation_id: str, output_format: str) -> None:
        source = app.config.sources.get(source_name)
        operation = app.source_operations.get(source_name, {}).get(operation_id)
        if not operation:
            fail(
                click.get_current_context(),
                RegistryError(f"operation not found: {source_name}.{operation_id}", code="operation_not_found"),
                "inspect_operation",
                output_format,
            )
            return
        schema_info = app.get_schema_info(source_name, source, operation_id) if source else None
        payload = operation.model_dump(mode="json")
        payload["source_origin_file"] = path_to_str(app.origin_file_for(source))
        payload["schema_provenance"] = schema_info[1] if schema_info else None
        click.echo(render_payload(payload, output_format))

    @inspect_group.command(name="drift", help="Inspect the latest discovery drift report.", short_help="Inspect the latest discovery drift report.")
    @click.argument("source_name", required=False)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def inspect_drift(app, source_name: Optional[str], output_format: str) -> None:
        report = app.discovery_store.load_latest_sync_report(source_name)
        if not report:
            fail(
                click.get_current_context(),
                RegistryError(
                    "no sync report available",
                    code="drift_report_not_found",
                    suggestions=["先执行 `cts manage sync`，再查看 drift 结果。"],
                ),
                "inspect_drift",
                output_format,
            )
            return
        items = list(report.get("items") or [])
        if source_name:
            items = [item for item in items if item.get("source") == source_name]
            if not items:
                fail(
                    click.get_current_context(),
                    RegistryError(f"drift report not found for source: {source_name}", code="drift_source_not_found"),
                    "inspect_drift",
                    output_format,
                )
                return
        payload = {
            "ok": True,
            "requested_source": source_name,
            "generated_at": report.get("generated_at"),
            "report_path": str(app.discovery_store.latest_sync_report_path(source_name)),
            "drift_summary": report.get("drift_summary"),
            "items": [
                {
                    "source": item.get("source"),
                    "provider_type": item.get("provider_type"),
                    "ok": item.get("ok"),
                    "usable": item.get("usable"),
                    "operation_count": item.get("operation_count"),
                    "drift": item.get("drift"),
                    "governance_state": app.get_source_drift_state(str(item.get("source") or "")),
                    "snapshot_path": item.get("snapshot_path"),
                }
                for item in items
            ],
        }
        click.echo(render_payload(payload, output_format))
