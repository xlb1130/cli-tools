from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import click

from cts.cli.lazy import render_payload
from cts.execution.errors import ConfigError, RegistryError


def register_catalog_workflow_commands(
    manage_group,
    *,
    pass_app,
    pass_help_app,
    get_state: Callable,
    fail: Callable,
) -> None:
    @manage_group.group()
    def catalog() -> None:
        """Catalog export commands."""

    @catalog.command(name="export", help="Export the compiled catalog.", short_help="Export the compiled catalog.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def catalog_export(app, output_format: str) -> None:
        click.echo(render_payload(app.export_catalog(), output_format))

    @manage_group.command(name="docs", help="Generate documentation from CTS configuration.", short_help="Generate documentation from CTS configuration.")
    @click.argument("output_dir", type=click.Path(path_type=Path), default=Path("docs/generated"))
    @click.option("--title", default="CTS Documentation", help="Documentation title.")
    @click.option("--format", "doc_format", type=click.Choice(["markdown", "html", "json"]), default="markdown")
    @click.option("--no-sources", is_flag=True, help="Skip sources documentation.")
    @click.option("--no-mounts", is_flag=True, help="Skip mounts documentation.")
    @click.option("--no-catalog", is_flag=True, help="Skip catalog documentation.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", hidden=True)
    @pass_app
    def docs_generate(
        app,
        output_dir: Path,
        title: str,
        doc_format: str,
        no_sources: bool,
        no_mounts: bool,
        no_catalog: bool,
        output_format: str,
    ) -> None:
        """Generate documentation from CTS configuration."""
        from cts.docs import DocsConfig, DocsGenerator

        config = DocsConfig(
            output_dir=output_dir,
            format=doc_format,
            title=title,
            include_sources=not no_sources,
            include_mounts=not no_mounts,
            include_catalog=not no_catalog,
        )

        generator = DocsGenerator(app, config)
        generated = generator.generate()

        payload = {
            "ok": True,
            "action": "docs_generate",
            "output_dir": str(output_dir),
            "generated_files": {key: str(value) for key, value in generated.items()},
        }
        click.echo(render_payload(payload, output_format))

    @manage_group.group()
    def workflow() -> None:
        """Workflow management commands."""

    @workflow.command(name="list", help="List all configured workflows.", short_help="List all configured workflows.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_help_app
    def workflow_list(app, output_format: str) -> None:
        """List all configured workflows."""
        workflows = [
            workflow_item.model_dump(mode="json") if hasattr(workflow_item, "model_dump") else workflow_item
            for workflow_item in getattr(app.config, "workflows", [])
        ]
        payload = {"workflows": workflows, "count": len(workflows)}
        click.echo(render_payload(payload, output_format))

    @workflow.command(name="execute", help="Execute a workflow.", short_help="Execute a workflow.")
    @click.argument("workflow_id")
    @click.option("--input-json", default=None, help="JSON input for the workflow.")
    @click.option("--dry-run", is_flag=True, help="Preview execution without running.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def workflow_execute(
        ctx: click.Context,
        workflow_id: str,
        input_json: Optional[str],
        dry_run: bool,
        output_format: str,
    ) -> None:
        """Execute a workflow."""
        state = get_state(ctx)
        app = state.get_app()

        workflows = [
            workflow_item.model_dump(mode="json") if hasattr(workflow_item, "model_dump") else workflow_item
            for workflow_item in getattr(app.config, "workflows", [])
        ]
        workflow_config = next((item for item in workflows if item.get("id") == workflow_id), None)
        if not workflow_config:
            fail(ctx, RegistryError(f"workflow not found: {workflow_id}", code="workflow_not_found"), "workflow_execute", output_format)
            return

        from cts.workflow import WorkflowConfig, WorkflowExecutor

        workflow_obj = WorkflowConfig.from_dict(workflow_config)
        executor = WorkflowExecutor(app)

        args = {}
        if input_json:
            try:
                args = json.loads(input_json)
            except json.JSONDecodeError as exc:
                fail(ctx, ConfigError(f"Invalid JSON input: {exc}"), "workflow_execute", output_format)
                return

        result = executor.execute(workflow_obj, args, dry_run=dry_run)
        payload = {
            "ok": result.success,
            "workflow_id": workflow_id,
            "run_id": result.run_id,
            "trace_id": result.trace_id,
            "steps": [
                {
                    "step_id": step.step_id,
                    "success": step.success,
                    "skipped": step.skipped,
                    "error": step.error,
                }
                for step in result.steps
            ],
            "output": result.output,
            "error": result.error,
        }
        click.echo(render_payload(payload, output_format))
