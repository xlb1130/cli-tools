from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import click

from cts.cli.lazy import build_app, render_payload
from cts.execution.errors import RegistryError


def register_execution_ops_commands(
    manage_group,
    *,
    pass_app,
    pass_invoke_app,
    fail: Callable,
    maybe_confirm: Callable,
    progress_steps: Callable,
    status: Callable,
    emit_app_event: Callable,
    run_mount_command: Callable,
) -> None:
    @manage_group.command(
        help="Invoke a mounted capability with validated input.",
        short_help="Invoke a mounted capability with validated input.",
    )
    @click.argument("mount_id")
    @click.option("--input-json", default=None, help="Raw JSON object input.")
    @click.option(
        "--input-file",
        type=click.Path(path_type=Path, exists=True, dir_okay=False),
        default=None,
        help="Path to a JSON file containing operation input.",
    )
    @click.option("--dry-run", is_flag=True, help="Plan without executing.")
    @click.option("--non-interactive", is_flag=True, help="Disable interactive prompts.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_invoke_app
    def invoke(
        app,
        mount_id: str,
        input_json: Optional[str],
        input_file: Optional[Path],
        dry_run: bool,
        non_interactive: bool,
        output_format: str,
    ) -> None:
        mount = app.catalog.find_by_id(mount_id)
        if not mount:
            fail(click.get_current_context(), RegistryError(f"mount not found: {mount_id}", code="mount_not_found"), "invoke", output_format)
            return

        kwargs = {
            "input_json": input_json,
            "input_file": input_file,
            "dry_run": dry_run,
            "non_interactive": non_interactive,
            "output_format": output_format,
        }
        start_perf = click.get_current_context().meta.get("cts_app_load_started_at")
        run_mount_command(
            app,
            mount,
            kwargs,
            mode="invoke",
            start_perf=start_perf,
        )

    @manage_group.command(
        help="Explain how a mounted capability would execute without running it.",
        short_help="Explain how a mounted capability would execute without running it.",
    )
    @click.argument("mount_id")
    @click.option("--input-json", default=None, help="Raw JSON object input.")
    @click.option(
        "--input-file",
        type=click.Path(path_type=Path, exists=True, dir_okay=False),
        default=None,
        help="Path to a JSON file containing operation input.",
    )
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_invoke_app
    def explain(app, mount_id: str, input_json: Optional[str], input_file: Optional[Path], output_format: str) -> None:
        mount = app.catalog.find_by_id(mount_id)
        if not mount:
            fail(click.get_current_context(), RegistryError(f"mount not found: {mount_id}", code="mount_not_found"), "explain", output_format)
            return

        kwargs = {
            "input_json": input_json,
            "input_file": input_file,
            "output_format": output_format,
            "dry_run": False,
            "non_interactive": True,
        }
        start_perf = click.get_current_context().meta.get("cts_app_load_started_at")
        run_mount_command(
            app,
            mount,
            kwargs,
            mode="explain",
            start_perf=start_perf,
        )

    @manage_group.command(
        help="Run discovery sync for one source or the whole registry.",
        short_help="Run discovery sync for one source or the whole registry.",
    )
    @click.argument("source_name", required=False)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def sync(app, source_name: Optional[str], output_format: str) -> None:
        label = f"Syncing source '{source_name}'..." if source_name else "Syncing all sources..."
        with status(output_format, label):
            payload = app.sync(source_name)
        click.echo(render_payload(payload, output_format))

    @manage_group.group()
    def reconcile() -> None:
        """Drift reconciliation commands."""

    @reconcile.command("drift")
    @click.argument("source_name")
    @click.option("--action", "reconcile_action", type=click.Choice(["accept-breaking"]), default="accept-breaking", show_default=True)
    @click.option("--yes", is_flag=True, help="Skip interactive confirmation.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def reconcile_drift(app, source_name: str, reconcile_action: str, yes: bool, output_format: str) -> None:
        report = app.discovery_store.load_latest_sync_report(source_name)
        if not report:
            fail(
                click.get_current_context(),
                RegistryError(
                    "no sync report available",
                    code="drift_report_not_found",
                    suggestions=["先执行 `cts manage sync`，再执行 drift reconcile。"],
                ),
                "reconcile_drift",
                output_format,
            )
            return

        source_state = app.get_source_drift_state(source_name)
        blocked_mounts = [
            state for state in app.mount_drift_state.values() if state.get("source") == source_name and state.get("blocked")
        ]
        if not source_state or (source_state.get("status") not in {"breaking", "review_required", "accepted"} and not blocked_mounts):
            fail(
                click.get_current_context(),
                RegistryError(
                    f"no blocking drift found for source: {source_name}",
                    code="drift_not_reconcilable",
                    suggestions=["先执行 `cts manage inspect drift " + source_name + "` 查看当前 drift 状态。"],
                ),
                "reconcile_drift",
                output_format,
            )
            return

        maybe_confirm(
            f"Apply drift reconciliation '{reconcile_action}' for source '{source_name}'?",
            assume_yes=yes,
            output_format=output_format,
        )

        normalized_action = reconcile_action.replace("-", "_")
        with progress_steps(
            output_format,
            f"Reconciling drift for '{source_name}'",
            ["Write reconciliation", "Reload app state"],
        ) as progress:
            report_generated_at = str(source_state.get("report_generated_at") or report.get("generated_at") or "")
            progress.advance("Writing reconciliation")
            entry = app.discovery_store.upsert_drift_reconciliation(
                source_name=source_name,
                report_generated_at=report_generated_at,
                action=normalized_action,
                metadata={"surface": "cli"},
            )
            emit_app_event(
                app,
                event="drift_reconciled",
                source=source_name,
                data={"action": normalized_action, "report_generated_at": report_generated_at},
            )
            progress.advance("Reloading app state")
            next_app = build_app(app.explicit_config_path, profile=app.requested_profile)

        payload = {
            "ok": True,
            "action": "reconcile_drift",
            "source": source_name,
            "reconcile_action": normalized_action,
            "reconciliation": entry,
            "source_drift_state": next_app.get_source_drift_state(source_name),
            "mount_drift_states": [
                next_app.get_mount_drift_state(mount)
                for mount in next_app.catalog.mounts
                if mount.source_name == source_name and next_app.get_mount_drift_state(mount)
            ],
        }
        click.echo(render_payload(payload, output_format))
