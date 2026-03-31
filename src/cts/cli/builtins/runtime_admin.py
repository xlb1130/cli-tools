from __future__ import annotations

import time
from typing import Callable, Optional

import click

from cts.cli.lazy import (
    build_auth_inventory,
    build_auth_profile,
    build_secret_detail,
    build_secret_inventory,
    render_payload,
)
from cts.execution.errors import RegistryError
from cts.execution.logging import get_run, list_app_events, list_runs


def register_runtime_admin_commands(
    manage_group,
    *,
    pass_app,
    fail: Callable,
    maybe_confirm: Callable,
) -> None:
    @manage_group.group()
    def auth() -> None:
        """Authentication status commands."""

    @auth.command("list")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def auth_list(app, output_format: str) -> None:
        click.echo(render_payload(build_auth_inventory(app), output_format))

    @auth.command("status")
    @click.argument("name", required=False)
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def auth_status(app, name: Optional[str], output_format: str) -> None:
        try:
            if name:
                payload = build_auth_profile(app, name)
                payload["next_commands"] = [
                    f"cts auth validate {name}",
                    f"cts auth refresh {name}",
                ]
            else:
                payload = build_auth_inventory(app)
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "auth_status", output_format)

    @auth.command("login")
    @click.argument("name")
    @click.option("--token", default=None)
    @click.option("--api-key", default=None)
    @click.option("--username", default=None)
    @click.option("--password", default=None)
    @click.option("--expires-at", default=None, help="ISO8601 expiration timestamp.")
    @click.option("--refresh-token", default=None)
    @click.option("--header-name", default=None, help="Header name for api_key profiles.")
    @click.option("--in", "location", type=click.Choice(["header", "query"]), default=None, help="API key location override.")
    @click.option("--query-name", default=None, help="Query parameter name for api_key profiles.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def auth_login(
        app,
        name: str,
        token: Optional[str],
        api_key: Optional[str],
        username: Optional[str],
        password: Optional[str],
        expires_at: Optional[str],
        refresh_token: Optional[str],
        header_name: Optional[str],
        location: Optional[str],
        query_name: Optional[str],
        output_format: str,
    ) -> None:
        try:
            payload = {
                "ok": True,
                "action": "auth_login",
                "profile": app.auth_manager.login(
                    name,
                    token=token,
                    api_key=api_key,
                    username=username,
                    password=password,
                    expires_at=expires_at,
                    refresh_token=refresh_token,
                    header_name=header_name,
                    location=location,
                    query_name=query_name,
                ),
            }
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "auth_login", output_format)

    @auth.command("refresh")
    @click.argument("name")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def auth_refresh(app, name: str, output_format: str) -> None:
        try:
            payload = {"ok": True, "action": "auth_refresh", "profile": app.auth_manager.refresh(name)}
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "auth_refresh", output_format)

    @auth.command("logout")
    @click.argument("name")
    @click.option("--yes", is_flag=True, help="Skip interactive confirmation.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def auth_logout(app, name: str, yes: bool, output_format: str) -> None:
        try:
            maybe_confirm(f"Log out auth profile '{name}'?", assume_yes=yes, output_format=output_format)
            payload = {"ok": True, "action": "auth_logout", "profile": app.auth_manager.logout(name)}
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "auth_logout", output_format)

    @auth.command("validate")
    @click.argument("name", required=False)
    @click.option("--all", "validate_all", is_flag=True, help="Validate all auth profiles.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def auth_validate(app, name: Optional[str], validate_all: bool, output_format: str) -> None:
        try:
            payload = app.auth_manager.validate_all() if validate_all or not name else app.auth_manager.validate(name)
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "auth_validate", output_format)

    @manage_group.group()
    def secret() -> None:
        """Secret inventory commands."""

    @secret.command("list")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def secret_list(app, output_format: str) -> None:
        click.echo(render_payload(build_secret_inventory(app), output_format))

    @secret.command("show")
    @click.argument("name")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def secret_show(app, name: str, output_format: str) -> None:
        try:
            payload = build_secret_detail(app, name)
            payload["next_commands"] = ["cts secret list", "cts auth status"]
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(click.get_current_context(), exc, "secret_show", output_format)

    @manage_group.group()
    def runs() -> None:
        """Run history inspection commands."""

    @runs.command("list")
    @click.option("--limit", type=click.IntRange(1, 200), default=20, show_default=True)
    @click.option("--mount-id", default=None, help="Filter by mount id.")
    @click.option("--source", default=None, help="Filter by source name.")
    @click.option("--ok", "ok_only", type=click.Choice(["true", "false"]), default=None, help="Filter by success state.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def runs_list(app, limit: int, mount_id: Optional[str], source: Optional[str], ok_only: Optional[str], output_format: str) -> None:
        items = list_runs(app, limit=max(limit * 5, limit))
        if mount_id:
            items = [item for item in items if str(item.get("mount_id") or "") == mount_id]
        if source:
            items = [item for item in items if str(item.get("source") or "") == source]
        if ok_only is not None:
            expected = ok_only == "true"
            items = [item for item in items if bool(item.get("ok")) is expected]
        payload = {
            "items": items[:limit],
            "summary": {"count": len(items[:limit]), "mount_id": mount_id, "source": source, "ok": ok_only},
        }
        click.echo(render_payload(payload, output_format))

    @runs.command("show")
    @click.argument("run_id")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def runs_show(app, run_id: str, output_format: str) -> None:
        payload = get_run(app, run_id)
        if payload is None:
            fail(click.get_current_context(), RegistryError(f"run not found: {run_id}", code="run_not_found"), "show_run", output_format)
            return
        click.echo(render_payload(payload, output_format))

    @runs.command("watch")
    @click.option("--limit", type=click.IntRange(1, 200), default=20, show_default=True)
    @click.option("--interval", type=click.FloatRange(0.2, 60.0), default=2.0, show_default=True)
    @click.option("--iterations", type=click.IntRange(1, 1000), default=None, help="Stop after N refresh cycles.")
    @click.option("--mount-id", default=None, help="Filter by mount id.")
    @click.option("--source", default=None, help="Filter by source name.")
    @click.option("--ok", "ok_only", type=click.Choice(["true", "false"]), default=None, help="Filter by success state.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def runs_watch(app, limit: int, interval: float, iterations: Optional[int], mount_id: Optional[str], source: Optional[str], ok_only: Optional[str], output_format: str) -> None:
        seen: set[str] = set()
        cycle = 0
        while iterations is None or cycle < iterations:
            items = list_runs(app, limit=max(limit * 5, limit))
            if mount_id:
                items = [item for item in items if str(item.get("mount_id") or "") == mount_id]
            if source:
                items = [item for item in items if str(item.get("source") or "") == source]
            if ok_only is not None:
                expected = ok_only == "true"
                items = [item for item in items if bool(item.get("ok")) is expected]
            new_items = []
            for item in reversed(items[:limit]):
                run_id = str(item.get("run_id") or "")
                if not run_id or run_id in seen:
                    continue
                seen.add(run_id)
                new_items.append(item)
            if new_items:
                click.echo(render_payload({"items": new_items, "summary": {"mode": "watch", "count": len(new_items), "mount_id": mount_id, "source": source, "ok": ok_only}}, output_format))
            cycle += 1
            if iterations is None or cycle < iterations:
                time.sleep(interval)

    @manage_group.group()
    def logs() -> None:
        """Application log inspection commands."""

    @logs.command("recent")
    @click.option("--limit", type=click.IntRange(1, 200), default=20, show_default=True)
    @click.option("--level", default=None, help="Filter by log level.")
    @click.option("--source", default=None, help="Filter by source name.")
    @click.option("--mount-id", default=None, help="Filter by mount id.")
    @click.option("--event", "event_name", default=None, help="Filter by exact event name.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def logs_recent(app, limit: int, level: Optional[str], source: Optional[str], mount_id: Optional[str], event_name: Optional[str], output_format: str) -> None:
        items = list_app_events(app, limit=limit, events=[event_name] if event_name else None, level=level, source=source, mount_id=mount_id)
        payload = {
            "items": items,
            "summary": {"count": len(items), "level": level, "source": source, "mount_id": mount_id, "event": event_name},
        }
        click.echo(render_payload(payload, output_format))

    @logs.command("watch")
    @click.option("--limit", type=click.IntRange(1, 200), default=20, show_default=True)
    @click.option("--interval", type=click.FloatRange(0.2, 60.0), default=2.0, show_default=True)
    @click.option("--iterations", type=click.IntRange(1, 1000), default=None, help="Stop after N refresh cycles.")
    @click.option("--level", default=None, help="Filter by log level.")
    @click.option("--source", default=None, help="Filter by source name.")
    @click.option("--mount-id", default=None, help="Filter by mount id.")
    @click.option("--event", "event_name", default=None, help="Filter by exact event name.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @pass_app
    def logs_watch(app, limit: int, interval: float, iterations: Optional[int], level: Optional[str], source: Optional[str], mount_id: Optional[str], event_name: Optional[str], output_format: str) -> None:
        seen: set[tuple[str, str, str, str]] = set()
        cycle = 0
        while iterations is None or cycle < iterations:
            items = list_app_events(app, limit=limit, events=[event_name] if event_name else None, level=level, source=source, mount_id=mount_id)
            new_items = []
            for item in reversed(items):
                event_key = (
                    str(item.get("ts") or ""),
                    str(item.get("event") or ""),
                    str(item.get("run_id") or ""),
                    str(item.get("mount_id") or ""),
                )
                if event_key in seen:
                    continue
                seen.add(event_key)
                new_items.append(item)
            if new_items:
                click.echo(render_payload({"items": new_items, "summary": {"mode": "watch", "count": len(new_items)}}, output_format))
            cycle += 1
            if iterations is None or cycle < iterations:
                time.sleep(interval)
