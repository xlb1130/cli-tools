from __future__ import annotations

import json
from typing import Any, Callable, Dict

import click
import yaml

from cts.cli.lazy import build_app, lint_loaded_config, render_payload
from cts.config.loader import load_config
from cts.execution.errors import exit_code_for_exception


def register_config_group(
    manage_group,
    *,
    pass_app,
    pass_help_app,
    get_state: Callable,
    fail: Callable,
    serialize_error: Callable,
    strip_internal_metadata: Callable,
) -> None:
    @manage_group.group()
    def config() -> None:
        """Configuration inspection commands."""

    @config.command(name="paths", help="Show root and loaded config paths.", short_help="Show root and loaded config paths.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_help_app
    def config_paths(app, output_format: str) -> None:
        payload = {
            "root_paths": [str(path) for path in app.loaded_config.root_paths],
            "loaded_paths": [str(path) for path in app.config_paths],
        }
        click.echo(render_payload(payload, output_format))

    @config.command(name="build", help="Render the merged config payload.", short_help="Render the merged config payload.")
    @click.option("--format", "output_format", type=click.Choice(["json", "yaml"]), default="yaml")
    @pass_help_app
    def config_build(app, output_format: str) -> None:
        payload = {
            "root_paths": [str(path) for path in app.loaded_config.root_paths],
            "loaded_paths": [str(path) for path in app.config_paths],
            "config": strip_internal_metadata(app.config.model_dump(mode="json", by_alias=True)),
        }
        if output_format == "json":
            click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        click.echo(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))

    @config.command(name="lint", help="Lint config files and optional runtime state.", short_help="Lint config files and optional runtime state.")
    @click.option("--compile", "compile_runtime", is_flag=True, help="Compile the runtime and surface conflicts/discovery errors.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def config_lint(ctx: click.Context, compile_runtime: bool, output_format: str) -> None:
        state = get_state(ctx)
        payload: Dict[str, Any] = {
            "ok": True,
            "config_path": str(state.config_path) if state.config_path else None,
            "root_paths": [],
            "loaded_paths": [],
            "warnings": [],
            "errors": [],
        }

        try:
            loaded = load_config(str(state.config_path) if state.config_path else None)
            payload["root_paths"] = [str(path) for path in loaded.root_paths]
            payload["loaded_paths"] = [str(path) for path in loaded.paths]
            payload["config_version"] = loaded.config.version
            lint_result = lint_loaded_config(loaded)
            payload["warnings"].extend(lint_result["warnings"])
            payload["errors"].extend(lint_result["errors"])
            if not loaded.paths:
                payload["warnings"].append(
                    {
                        "type": "ConfigWarning",
                        "code": "no_config_files",
                        "message": "No config files were loaded; cts will run with default empty config.",
                    }
                )

            if compile_runtime:
                app = build_app(str(state.config_path) if state.config_path else None, profile=state.profile)
                payload["conflicts"] = app.catalog.conflicts
                payload["discovery_errors"] = dict(app.discovery_errors)
                if app.catalog.conflicts:
                    payload["errors"].extend(
                        {
                            "type": "RegistryError",
                            "code": "catalog_conflict",
                            "message": f"Catalog conflict detected for {item.get('type')}.",
                            "details": item,
                        }
                        for item in app.catalog.conflicts
                    )
                if app.discovery_errors:
                    payload["warnings"].extend(
                        {
                            "type": "DiscoveryWarning",
                            "code": "source_discovery_failed",
                            "message": f"Discovery failed for source '{name}'.",
                            "details": {"source": name, "error": error},
                        }
                        for name, error in app.discovery_errors.items()
                    )
        except Exception as exc:
            payload["ok"] = False
            payload["errors"] = [serialize_error(exc, "config_lint")]
            click.echo(render_payload(payload, output_format))
            ctx.exit(exit_code_for_exception(exc, "config_lint"))
            return

        payload["ok"] = not payload["errors"]
        click.echo(render_payload(payload, output_format))
        if not payload["ok"]:
            ctx.exit(2)

    @config.command(name="migrate", help="Migrate configuration to the latest version.", short_help="Migrate configuration to the latest version.")
    @click.option("--dry-run", is_flag=True, help="Preview changes without applying them.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def config_migrate(ctx: click.Context, dry_run: bool, output_format: str) -> None:
        """Migrate configuration to the latest version.

        This command analyzes the current configuration and applies
        any necessary migrations to bring it up to the latest version.

        Use --dry-run to preview what changes would be made.
        """
        from cts.config.migration import MigrationManager

        state = get_state(ctx)
        config_path = str(state.config_path) if state.config_path else None

        try:
            loaded = load_config(config_path)
            raw_config = loaded.raw if hasattr(loaded, "raw") else loaded.config.model_dump()

            manager = MigrationManager(config_path=config_path)
            plan = manager.analyze(raw_config)

            if plan.from_version == plan.to_version:
                payload = {
                    "ok": True,
                    "message": f"Configuration is already at the latest version ({plan.to_version})",
                    "from_version": plan.from_version,
                    "to_version": plan.to_version,
                    "actions_needed": False,
                }
                click.echo(render_payload(payload, output_format))
                return

            result = manager.apply(raw_config, plan=plan, dry_run=dry_run)

            payload = {
                "ok": result.success,
                "from_version": result.from_version,
                "to_version": result.to_version,
                "dry_run": dry_run,
                "applied_actions": len(result.applied_actions),
                "skipped_actions": len(result.skipped_actions),
                "errors": result.errors,
                "warnings": result.warnings,
                "plan": plan.to_dict() if dry_run else None,
            }
            click.echo(render_payload(payload, output_format))

            if not result.success:
                ctx.exit(1)
        except Exception as exc:
            fail(ctx, exc, "config_migrate", output_format)
