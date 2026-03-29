from __future__ import annotations

import json
import shlex
import sys
import uuid
from dataclasses import dataclass, field
from functools import update_wrapper
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import yaml
from click.shell_completion import get_completion_class

from cts import __version__
from cts.app import CTSApp, build_app, tokenize_identifier
from cts.config.editor import (
    ConfigEditError,
    apply_assignment,
    apply_update,
    conflict_signatures,
    ensure_list,
    ensure_mapping,
    parse_assignment,
    parse_string_map_item,
    prepare_edit_session,
)
from cts.config.lint import lint_loaded_config
from cts.config.loader import load_config
from cts.execution.errors import RegistryError, exit_code_for_exception
from cts.execution.help_compiler import build_click_params, extract_request_args
from cts.execution.logging import (
    emit_app_event,
    emit_audit_event,
    get_run,
    list_runs,
    record_run,
    summarize_result,
    utc_now_iso,
)
from cts.importers import import_cli_completion, import_cli_help, import_cli_manpage, import_cli_schema, merge_operation_into_manifest
from cts.execution.runtime import build_error_envelope, explain_mount, invoke_mount, render_payload
from cts.presentation import (
    build_app_summary,
    build_auth_inventory,
    build_auth_profile,
    build_mount_details,
    build_mount_help,
    build_secret_detail,
    build_secret_inventory,
    build_source_check_result,
    build_source_details,
    build_source_summary,
)
from cts.surfaces.http import create_http_server, default_ui_dist_dir


@dataclass
class CLIState:
    config_path: Optional[Path]
    profile: Optional[str]
    global_output: str = "text"
    _app: Optional[CTSApp] = field(default=None, init=False, repr=False)

    def get_app(self) -> CTSApp:
        if self._app is None:
            self._app = build_app(str(self.config_path) if self.config_path else None, profile=self.profile)
            setattr(self._app, "global_output", self.global_output)
        return self._app


def pass_app(func):
    @click.pass_context
    def wrapper(ctx: click.Context, *args, **kwargs):
        try:
            app = _get_app(ctx)
        except Exception as exc:
            _fail(ctx, exc, "config_load", _error_output_format(ctx, kwargs.get("output_format")))
            return None
        return ctx.invoke(func, app, *args, **kwargs)

    return update_wrapper(wrapper, func)


class CatalogBackedGroup(click.Group):
    def __init__(self, *args, path_prefix=None, dynamic_only: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.path_prefix = tuple(path_prefix or ())
        self.dynamic_only = dynamic_only

    def list_commands(self, ctx):
        commands = [] if self.dynamic_only else list(super().list_commands(ctx))
        try:
            app = _get_app(ctx)
        except Exception:
            return sorted(set(commands))
        commands.extend(app.catalog.child_tokens(self.path_prefix))
        return sorted(set(commands))

    def get_command(self, ctx, cmd_name):
        if not self.dynamic_only:
            builtin = super().get_command(ctx, cmd_name)
            if builtin is not None:
                return builtin

        try:
            app = _get_app(ctx)
        except Exception as exc:
            return _build_error_command(cmd_name, exc)

        next_prefix = self.path_prefix + (cmd_name,)
        mount = app.catalog.find_by_path(next_prefix)
        if mount:
            return build_dynamic_command(app, mount)
        if app.catalog.has_group(next_prefix):
            return CatalogBackedGroup(
                name=cmd_name,
                path_prefix=next_prefix,
                dynamic_only=True,
                help=app.catalog.group_summary(next_prefix),
                no_args_is_help=True,
            )
        return None


@click.group(
    name="cts",
    cls=CatalogBackedGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--config", "config_path", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--profile", default=None, help="Active profile override.")
@click.option(
    "--output",
    "global_output",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Default output mode for top-level commands.",
)
@click.version_option(__version__, prog_name="cts")
@click.pass_context
def main(ctx: click.Context, config_path: Optional[Path], profile: Optional[str], global_output: str) -> None:
    ctx.obj = CLIState(config_path=config_path, profile=profile, global_output=global_output)


@main.group()
def config() -> None:
    """Configuration inspection commands."""


@config.command("paths")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def config_paths(app: CTSApp, output_format: str) -> None:
    payload = {
        "root_paths": [str(path) for path in app.loaded_config.root_paths],
        "loaded_paths": [str(path) for path in app.config_paths],
    }
    click.echo(render_payload(payload, output_format))


@config.command("build")
@click.option("--format", "output_format", type=click.Choice(["json", "yaml"]), default="yaml")
@pass_app
def config_build(app: CTSApp, output_format: str) -> None:
    payload = {
        "root_paths": [str(path) for path in app.loaded_config.root_paths],
        "loaded_paths": [str(path) for path in app.config_paths],
        "config": _strip_internal_metadata(app.config.model_dump(mode="json", by_alias=True)),
    }
    if output_format == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))


@config.command("lint")
@click.option("--compile", "compile_runtime", is_flag=True, help="Compile the runtime and surface conflicts/discovery errors.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def config_lint(ctx: click.Context, compile_runtime: bool, output_format: str) -> None:
    state = _get_state(ctx)
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
        payload["errors"] = [_serialize_error(exc, "config_lint")]
        click.echo(render_payload(payload, output_format))
        ctx.exit(exit_code_for_exception(exc, "config_lint"))
        return

    payload["ok"] = not payload["errors"]
    click.echo(render_payload(payload, output_format))
    if not payload["ok"]:
        ctx.exit(2)


@main.group()
def source() -> None:
    """Source registry operations."""


@source.command("add")
@click.argument("provider_type")
@click.argument("source_name")
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write into a specific loaded config file.")
@click.option("--description", default=None)
@click.option("--owner", default=None)
@click.option("--tag", "tags", multiple=True, help="Repeatable source tag.")
@click.option("--profile-scope", "profile_scopes", multiple=True, help="Repeatable profile scope.")
@click.option("--auth-ref", default=None)
@click.option("--auth-session", default=None)
@click.option("--working-dir", type=click.Path(path_type=Path, file_okay=False), default=None)
@click.option("--root", "root_dir", type=click.Path(path_type=Path, file_okay=False), default=None)
@click.option("--bin", "executable", default=None, help="Executable for cli/shell sources.")
@click.option("--base-url", default=None)
@click.option("--endpoint", default=None)
@click.option("--url", default=None, help="Remote endpoint for MCP or HTTP-like transports.")
@click.option("--server", default=None, help="Named MCP server inside a config file.")
@click.option("--config-file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="External config file, for example MCP server config.")
@click.option("--transport-type", default=None)
@click.option("--adapter", default=None)
@click.option("--manifest", default=None, help="Discovery manifest path.")
@click.option("--spec-url", default=None, help="OpenAPI spec URL.")
@click.option("--spec-file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Local OpenAPI spec file.")
@click.option("--schema-url", default=None, help="GraphQL introspection JSON URL.")
@click.option("--schema-file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Local GraphQL introspection JSON file.")
@click.option("--introspection", "introspection_mode", default=None, help="GraphQL schema introspection mode, for example live.")
@click.option("--discover-mode", default=None, help="Override discovery.mode.")
@click.option("--header", "headers", multiple=True, help="Repeatable header in key=value form.")
@click.option("--env", "env_items", multiple=True, help="Repeatable env var in key=value form.")
@click.option("--expose", "surfaces", multiple=True, help="Repeatable surface name.")
@click.option("--pass-env/--no-pass-env", default=False, help="Whether to inherit current process env during execution.")
@click.option("--enabled/--disabled", default=True)
@click.option("--set", "assignments", multiple=True, help="Arbitrary source override, for example --set reliability.timeout_seconds=30.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def source_add(
    ctx: click.Context,
    provider_type: str,
    source_name: str,
    target_file: Optional[Path],
    description: Optional[str],
    owner: Optional[str],
    tags: tuple[str, ...],
    profile_scopes: tuple[str, ...],
    auth_ref: Optional[str],
    auth_session: Optional[str],
    working_dir: Optional[Path],
    root_dir: Optional[Path],
    executable: Optional[str],
    base_url: Optional[str],
    endpoint: Optional[str],
    url: Optional[str],
    server: Optional[str],
    config_file: Optional[Path],
    transport_type: Optional[str],
    adapter: Optional[str],
    manifest: Optional[str],
    spec_url: Optional[str],
    spec_file: Optional[Path],
    schema_url: Optional[str],
    schema_file: Optional[Path],
    introspection_mode: Optional[str],
    discover_mode: Optional[str],
    headers: tuple[str, ...],
    env_items: tuple[str, ...],
    surfaces: tuple[str, ...],
    pass_env: bool,
    enabled: bool,
    assignments: tuple[str, ...],
    output_format: str,
) -> None:
    state = _get_state(ctx)
    try:
        session = prepare_edit_session(state.config_path, target_file=target_file)
        available_types = CTSApp(
            session.loaded,
            active_profile=state.profile,
            explicit_config_path=str(state.config_path) if state.config_path else None,
            requested_profile=state.profile,
        ).provider_registry.supported_types()
        normalized_provider_type = provider_type.lower()
        if available_types and normalized_provider_type not in available_types:
            raise RegistryError(
                f"unsupported provider type: {provider_type}",
                code="provider_type_unsupported",
                suggestions=[
                    "检查是否已在配置中启用对应 plugin，或改用内置 provider。",
                    "当前可用 provider: " + ", ".join(sorted(available_types)),
                ],
            )
        if source_name in session.loaded.config.sources:
            raise RegistryError(f"source already exists: {source_name}", code="source_exists")

        def mutator(payload: Dict[str, Any]) -> None:
            sources = ensure_mapping(payload, "sources")
            source_payload: Dict[str, Any] = {"type": normalized_provider_type, "enabled": enabled}
            if description:
                source_payload["description"] = description
            if owner:
                source_payload["owner"] = owner
            if tags:
                source_payload["tags"] = list(tags)
            if profile_scopes:
                source_payload["profile_scope"] = list(profile_scopes)
            if auth_ref:
                source_payload["auth_ref"] = auth_ref
            if auth_session:
                source_payload["auth_session"] = auth_session
            if working_dir:
                source_payload["working_dir"] = str(working_dir)
            if root_dir:
                source_payload["root"] = str(root_dir)
            if executable:
                source_payload["executable"] = executable
            if base_url:
                source_payload["base_url"] = base_url
            if endpoint:
                source_payload["endpoint"] = endpoint
            if url:
                source_payload["url"] = url
            if server:
                source_payload["server"] = server
            if config_file:
                source_payload["config_file"] = str(config_file)
            if transport_type:
                source_payload["transport_type"] = transport_type
            if adapter:
                source_payload["adapter"] = adapter
            if spec_url or spec_file:
                spec_payload: Dict[str, Any] = {}
                if spec_url:
                    spec_payload["url"] = spec_url
                if spec_file:
                    spec_payload["path"] = str(spec_file)
                source_payload["spec"] = spec_payload
            if schema_url or schema_file or introspection_mode:
                schema_payload: Dict[str, Any] = {}
                if schema_url:
                    schema_payload["url"] = schema_url
                if schema_file:
                    schema_payload["path"] = str(schema_file)
                if introspection_mode:
                    schema_payload["introspection"] = introspection_mode
                source_payload["schema"] = schema_payload
            if surfaces:
                source_payload["expose_to_surfaces"] = list(surfaces)
            if pass_env:
                source_payload["pass_env"] = True
            if manifest or discover_mode:
                discovery_payload: Dict[str, Any] = {}
                if manifest:
                    discovery_payload["manifest"] = manifest
                if discover_mode:
                    discovery_payload["mode"] = discover_mode
                source_payload["discovery"] = discovery_payload
            if headers:
                source_payload["headers"] = {key: value for key, value in (_parse_string_pair(item, field_name="header") for item in headers)}
            if env_items:
                source_payload["env"] = {key: value for key, value in (_parse_string_pair(item, field_name="env") for item in env_items)}
            for assignment in assignments:
                path, value = _parse_assignment(assignment)
                apply_assignment(source_payload, path, value)
            sources[source_name] = source_payload

        updated, _ = apply_update(session, mutator, compile_runtime=False)
        payload = {
            "ok": True,
            "action": "source_add",
            "source": source_name,
            "provider_type": normalized_provider_type,
            "file": str(session.target_path),
            "created_file": session.created,
            "warnings": list(session.warnings),
            "config": _strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "source_add", output_format)


@source.command("list")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@pass_app
def source_list(app: CTSApp, output_format: str) -> None:
    payload = {"items": [build_source_summary(app, name, source) for name, source in app.config.sources.items()]}
    click.echo(render_payload(payload, output_format))


@source.command("show")
@click.argument("source_name")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def source_show(app: CTSApp, source_name: str, output_format: str) -> None:
    source = app.config.sources.get(source_name)
    if not source:
        _fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "show_source", output_format)
        return
    click.echo(render_payload(build_source_details(app, source_name, source), output_format))


@source.command("test")
@click.argument("source_name")
@click.option("--discover", is_flag=True, help="Also run source discovery and report discovered operation count.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def source_test(app: CTSApp, source_name: str, discover: bool, output_format: str) -> None:
    source = app.config.sources.get(source_name)
    if not source:
        _fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "test_source", output_format)
        return
    payload = build_source_check_result(app, source_name, source)
    if discover:
        sync_result = app.sync(source_name)
        sync_items = sync_result.get("items", [])
        payload["discovery"] = sync_items[0] if sync_items else {"ok": False, "source": source_name, "operation_count": 0}
        payload["discovery_report_path"] = sync_result.get("report_path")
        payload["capability_snapshot_path"] = sync_result.get("capability_snapshot_path")
        payload["ok"] = payload["ok"] and payload["discovery"].get("ok", False)
    click.echo(render_payload(payload, output_format))
    if not payload["ok"]:
        click.get_current_context().exit(6)


@source.command("import-help")
@click.argument("source_name")
@click.argument("operation_id")
@click.argument("command_argv", nargs=-1)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Override the manifest file to write.")
@click.option("--help-flag", default="--help", show_default=True)
@click.option("--title", default=None)
@click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
@click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def source_import_help(
    app: CTSApp,
    source_name: str,
    operation_id: str,
    command_argv: tuple[str, ...],
    manifest_path: Optional[Path],
    help_flag: str,
    title: Optional[str],
    risk: str,
    output_mode: str,
    output_format: str,
) -> None:
    source = app.config.sources.get(source_name)
    if not source:
        _fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "source_import_help", output_format)
        return
    if source.type not in {"cli", "shell"}:
        _fail(
            click.get_current_context(),
            RegistryError(
                f"source '{source_name}' is not a cli/shell source",
                code="source_type_not_supported",
                suggestions=["使用 `cli` 或 `shell` source，或改用对应 provider 的导入方式。"],
            ),
            "source_import_help",
            output_format,
        )
        return

    resolved_manifest = manifest_path
    if resolved_manifest is None and source.discovery.manifest:
        resolved_manifest = app.resolve_path(source.discovery.manifest, owner=source)
    if resolved_manifest is None:
        _fail(
            click.get_current_context(),
            RegistryError(
                f"source '{source_name}' has no discovery.manifest configured",
                code="manifest_path_required",
                suggestions=["先在 source 上配置 discovery.manifest，或执行命令时显式传入 --manifest。"],
            ),
            "source_import_help",
            output_format,
        )
        return

    final_command = list(command_argv)
    if not final_command:
        if source.executable:
            final_command = [source.executable]
        else:
            _fail(
                click.get_current_context(),
                RegistryError(
                    "command argv required when source.executable is not configured",
                    code="command_argv_required",
                ),
                "source_import_help",
                output_format,
            )
            return
    elif source.executable and final_command[0] != source.executable:
        final_command = [source.executable] + final_command

    try:
        result = import_cli_help(
            operation_id=operation_id,
            command_argv=final_command,
            help_flag=help_flag,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
        manifest_payload = merge_operation_into_manifest(
            resolved_manifest,
            result.operation,
            executable=source.executable or (final_command[0] if final_command else None),
        )
        next_app = build_app(app.explicit_config_path, profile=app.requested_profile)
        compiled_operation = next_app.source_operations.get(source_name, {}).get(operation_id)
        payload = {
            "ok": True,
            "action": "source_import_help",
            "source": source_name,
            "operation_id": operation_id,
            "manifest_path": str(resolved_manifest),
            "command_argv": final_command,
            "help_command": result.help_command,
            "manifest_operation_count": len(manifest_payload.get("operations", [])),
            "imported_operation": result.operation,
            "compiled_operation": compiled_operation.model_dump(mode="json") if compiled_operation else None,
        }
        emit_app_event(
            app,
            event="cli_help_import_complete",
            source=source_name,
            operation_id=operation_id,
            data={"manifest_path": str(resolved_manifest), "command_argv": final_command},
        )
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "source_import_help", output_format)


@source.command("import-completion")
@click.argument("source_name")
@click.argument("operation_id")
@click.argument("command_argv", nargs=-1)
@click.option("--completion-command", default=None, help="Shell-escaped command that prints completion candidates.")
@click.option("--completion-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
@click.option("--completion-format", type=click.Choice(["lines", "fish", "json"]), default="lines", show_default=True)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Override the manifest file to write.")
@click.option("--title", default=None)
@click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
@click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def source_import_completion(
    app: CTSApp,
    source_name: str,
    operation_id: str,
    command_argv: tuple[str, ...],
    completion_command: Optional[str],
    completion_file: Optional[Path],
    completion_format: str,
    manifest_path: Optional[Path],
    title: Optional[str],
    risk: str,
    output_mode: str,
    output_format: str,
) -> None:
    source = app.config.sources.get(source_name)
    if not source:
        _fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "source_import_completion", output_format)
        return
    if source.type not in {"cli", "shell"}:
        _fail(
            click.get_current_context(),
            RegistryError(
                f"source '{source_name}' is not a cli/shell source",
                code="source_type_not_supported",
                suggestions=["使用 `cli` 或 `shell` source，或改用对应 provider 的导入方式。"],
            ),
            "source_import_completion",
            output_format,
        )
        return
    if not completion_command and completion_file is None:
        _fail(
            click.get_current_context(),
            RegistryError(
                "completion source required",
                code="completion_source_required",
                suggestions=["传入 --completion-command 或 --completion-file。"],
            ),
            "source_import_completion",
            output_format,
        )
        return

    resolved_manifest = manifest_path
    if resolved_manifest is None and source.discovery.manifest:
        resolved_manifest = app.resolve_path(source.discovery.manifest, owner=source)
    if resolved_manifest is None:
        _fail(
            click.get_current_context(),
            RegistryError(
                f"source '{source_name}' has no discovery.manifest configured",
                code="manifest_path_required",
                suggestions=["先在 source 上配置 discovery.manifest，或执行命令时显式传入 --manifest。"],
            ),
            "source_import_completion",
            output_format,
        )
        return

    final_command = list(command_argv)
    if not final_command:
        if source.executable:
            final_command = [source.executable]
        else:
            _fail(
                click.get_current_context(),
                RegistryError(
                    "command argv required when source.executable is not configured",
                    code="command_argv_required",
                ),
                "source_import_completion",
                output_format,
            )
            return
    elif source.executable and final_command[0] != source.executable:
        final_command = [source.executable] + final_command

    parsed_completion_command = shlex.split(completion_command) if completion_command else None

    try:
        result = import_cli_completion(
            operation_id=operation_id,
            command_argv=final_command,
            completion_command=parsed_completion_command,
            completion_file=completion_file,
            completion_format=completion_format,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
        manifest_payload = merge_operation_into_manifest(
            resolved_manifest,
            result.operation,
            executable=source.executable or (final_command[0] if final_command else None),
        )
        next_app = build_app(app.explicit_config_path, profile=app.requested_profile)
        compiled_operation = next_app.source_operations.get(source_name, {}).get(operation_id)
        payload = {
            "ok": True,
            "action": "source_import_completion",
            "source": source_name,
            "operation_id": operation_id,
            "manifest_path": str(resolved_manifest),
            "command_argv": final_command,
            "completion_command": parsed_completion_command,
            "completion_file": str(completion_file) if completion_file else None,
            "completion_format": completion_format,
            "manifest_operation_count": len(manifest_payload.get("operations", [])),
            "imported_operation": result.operation,
            "compiled_operation": compiled_operation.model_dump(mode="json") if compiled_operation else None,
        }
        emit_app_event(
            app,
            event="cli_completion_import_complete",
            source=source_name,
            operation_id=operation_id,
            data={
                "manifest_path": str(resolved_manifest),
                "command_argv": final_command,
                "completion_command": parsed_completion_command,
                "completion_file": str(completion_file) if completion_file else None,
                "completion_format": completion_format,
            },
        )
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "source_import_completion", output_format)


@source.command("import-manpage")
@click.argument("source_name")
@click.argument("operation_id")
@click.argument("command_argv", nargs=-1)
@click.option("--man-command", default=None, help="Shell-escaped command that prints a plain-text man page.")
@click.option("--man-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Override the manifest file to write.")
@click.option("--title", default=None)
@click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
@click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def source_import_manpage(
    app: CTSApp,
    source_name: str,
    operation_id: str,
    command_argv: tuple[str, ...],
    man_command: Optional[str],
    man_file: Optional[Path],
    manifest_path: Optional[Path],
    title: Optional[str],
    risk: str,
    output_mode: str,
    output_format: str,
) -> None:
    source = app.config.sources.get(source_name)
    if not source:
        _fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "source_import_manpage", output_format)
        return
    if source.type not in {"cli", "shell"}:
        _fail(
            click.get_current_context(),
            RegistryError(
                f"source '{source_name}' is not a cli/shell source",
                code="source_type_not_supported",
                suggestions=["使用 `cli` 或 `shell` source，或改用对应 provider 的导入方式。"],
            ),
            "source_import_manpage",
            output_format,
        )
        return
    if not man_command and man_file is None:
        _fail(
            click.get_current_context(),
            RegistryError(
                "man page source required",
                code="manpage_source_required",
                suggestions=["传入 --man-command 或 --man-file。"],
            ),
            "source_import_manpage",
            output_format,
        )
        return

    resolved_manifest = manifest_path
    if resolved_manifest is None and source.discovery.manifest:
        resolved_manifest = app.resolve_path(source.discovery.manifest, owner=source)
    if resolved_manifest is None:
        _fail(
            click.get_current_context(),
            RegistryError(
                f"source '{source_name}' has no discovery.manifest configured",
                code="manifest_path_required",
                suggestions=["先在 source 上配置 discovery.manifest，或执行命令时显式传入 --manifest。"],
            ),
            "source_import_manpage",
            output_format,
        )
        return

    final_command = list(command_argv)
    if not final_command:
        if source.executable:
            final_command = [source.executable]
        else:
            _fail(
                click.get_current_context(),
                RegistryError(
                    "command argv required when source.executable is not configured",
                    code="command_argv_required",
                ),
                "source_import_manpage",
                output_format,
            )
            return
    elif source.executable and final_command[0] != source.executable:
        final_command = [source.executable] + final_command

    parsed_man_command = shlex.split(man_command) if man_command else None

    try:
        result = import_cli_manpage(
            operation_id=operation_id,
            command_argv=final_command,
            man_command=parsed_man_command,
            man_file=man_file,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
        manifest_payload = merge_operation_into_manifest(
            resolved_manifest,
            result.operation,
            executable=source.executable or (final_command[0] if final_command else None),
        )
        next_app = build_app(app.explicit_config_path, profile=app.requested_profile)
        compiled_operation = next_app.source_operations.get(source_name, {}).get(operation_id)
        payload = {
            "ok": True,
            "action": "source_import_manpage",
            "source": source_name,
            "operation_id": operation_id,
            "manifest_path": str(resolved_manifest),
            "command_argv": final_command,
            "man_command": result.man_command,
            "manifest_operation_count": len(manifest_payload.get("operations", [])),
            "imported_operation": result.operation,
            "compiled_operation": compiled_operation.model_dump(mode="json") if compiled_operation else None,
        }
        emit_app_event(
            app,
            event="cli_manpage_import_complete",
            source=source_name,
            operation_id=operation_id,
            data={"manifest_path": str(resolved_manifest), "command_argv": final_command},
        )
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "source_import_manpage", output_format)


@source.command("import-schema")
@click.argument("source_name")
@click.argument("operation_id")
@click.argument("command_argv", nargs=-1)
@click.option("--schema-command", default=None, help="Shell-escaped command that prints a JSON schema payload.")
@click.option("--schema-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
@click.option("--schema-format", type=click.Choice(["auto", "operation", "bindings", "options"]), default="auto", show_default=True)
@click.option("--manifest", "manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Override the manifest file to write.")
@click.option("--title", default=None)
@click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
@click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def source_import_schema(
    app: CTSApp,
    source_name: str,
    operation_id: str,
    command_argv: tuple[str, ...],
    schema_command: Optional[str],
    schema_file: Optional[Path],
    schema_format: str,
    manifest_path: Optional[Path],
    title: Optional[str],
    risk: str,
    output_mode: str,
    output_format: str,
) -> None:
    source = app.config.sources.get(source_name)
    if not source:
        _fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "source_import_schema", output_format)
        return
    if source.type not in {"cli", "shell"}:
        _fail(
            click.get_current_context(),
            RegistryError(
                f"source '{source_name}' is not a cli/shell source",
                code="source_type_not_supported",
                suggestions=["使用 `cli` 或 `shell` source，或改用对应 provider 的导入方式。"],
            ),
            "source_import_schema",
            output_format,
        )
        return
    if not schema_command and schema_file is None:
        _fail(
            click.get_current_context(),
            RegistryError(
                "schema source required",
                code="schema_source_required",
                suggestions=["传入 --schema-command 或 --schema-file。"],
            ),
            "source_import_schema",
            output_format,
        )
        return

    resolved_manifest = manifest_path
    if resolved_manifest is None and source.discovery.manifest:
        resolved_manifest = app.resolve_path(source.discovery.manifest, owner=source)
    if resolved_manifest is None:
        _fail(
            click.get_current_context(),
            RegistryError(
                f"source '{source_name}' has no discovery.manifest configured",
                code="manifest_path_required",
                suggestions=["先在 source 上配置 discovery.manifest，或执行命令时显式传入 --manifest。"],
            ),
            "source_import_schema",
            output_format,
        )
        return

    final_command = list(command_argv)
    if not final_command:
        if source.executable:
            final_command = [source.executable]
        else:
            _fail(
                click.get_current_context(),
                RegistryError(
                    "command argv required when source.executable is not configured",
                    code="command_argv_required",
                ),
                "source_import_schema",
                output_format,
            )
            return
    elif source.executable and final_command[0] != source.executable:
        final_command = [source.executable] + final_command

    parsed_schema_command = shlex.split(schema_command) if schema_command else None

    try:
        result = import_cli_schema(
            operation_id=operation_id,
            command_argv=final_command,
            schema_command=parsed_schema_command,
            schema_file=schema_file,
            schema_format=schema_format,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
        manifest_payload = merge_operation_into_manifest(
            resolved_manifest,
            result.operation,
            executable=source.executable or (final_command[0] if final_command else None),
        )
        next_app = build_app(app.explicit_config_path, profile=app.requested_profile)
        compiled_operation = next_app.source_operations.get(source_name, {}).get(operation_id)
        payload = {
            "ok": True,
            "action": "source_import_schema",
            "source": source_name,
            "operation_id": operation_id,
            "manifest_path": str(resolved_manifest),
            "command_argv": final_command,
            "schema_command": result.schema_command,
            "schema_payload": result.schema_payload,
            "manifest_operation_count": len(manifest_payload.get("operations", [])),
            "imported_operation": result.operation,
            "compiled_operation": compiled_operation.model_dump(mode="json") if compiled_operation else None,
        }
        emit_app_event(
            app,
            event="cli_schema_import_complete",
            source=source_name,
            operation_id=operation_id,
            data={"manifest_path": str(resolved_manifest), "command_argv": final_command, "schema_format": schema_format},
        )
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "source_import_schema", output_format)


@main.group()
def mount() -> None:
    """Mount registry operations."""


@mount.command("add")
@click.argument("source_name")
@click.argument("operation_id")
@click.option("--id", "mount_id", default=None, help="Stable mount id. Defaults to <source>-<operation>.")
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write into a specific loaded config file.")
@click.option("--path", "command_path_values", multiple=True, help="Full command path. Example: --path \"ops jira issue get\".")
@click.option("--as", "command_path_values", multiple=True, help="Alias of --path for CLI ergonomics.")
@click.option("--under", "under_values", multiple=True, help="Command prefix used together with the operation id tokens.")
@click.option("--alias", "alias_values", multiple=True, help="Repeatable alias command path.")
@click.option("--stable-name", default=None)
@click.option("--summary", default=None)
@click.option("--description", default=None)
@click.option("--note", "notes", multiple=True)
@click.option("--example", "examples", multiple=True)
@click.option("--expose", "surfaces", multiple=True)
@click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default=None)
@click.option("--param", "param_specs", multiple=True, help="Parameter spec in name[:type] form.")
@click.option("--required", "required_params", multiple=True, help="Repeatable required parameter name.")
@click.option("--param-help", "param_help_items", multiple=True, help="Parameter help in name=text form.")
@click.option("--param-default", "param_default_items", multiple=True, help="Parameter default in name=value form.")
@click.option("--param-flag", "param_flag_items", multiple=True, help="Parameter flag in name=--flag form.")
@click.option("--set", "assignments", multiple=True, help="Arbitrary mount override, for example --set policy.confirm=true.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def mount_add(
    ctx: click.Context,
    source_name: str,
    operation_id: str,
    mount_id: Optional[str],
    target_file: Optional[Path],
    command_path_values: tuple[str, ...],
    under_values: tuple[str, ...],
    alias_values: tuple[str, ...],
    stable_name: Optional[str],
    summary: Optional[str],
    description: Optional[str],
    notes: tuple[str, ...],
    examples: tuple[str, ...],
    surfaces: tuple[str, ...],
    risk: Optional[str],
    param_specs: tuple[str, ...],
    required_params: tuple[str, ...],
    param_help_items: tuple[str, ...],
    param_default_items: tuple[str, ...],
    param_flag_items: tuple[str, ...],
    assignments: tuple[str, ...],
    output_format: str,
) -> None:
    state = _get_state(ctx)
    try:
        session = prepare_edit_session(state.config_path, target_file=target_file)
        app = CTSApp(
            session.loaded,
            active_profile=state.profile,
            explicit_config_path=str(state.config_path) if state.config_path else None,
            requested_profile=state.profile,
        )
        if source_name not in app.config.sources:
            raise RegistryError(f"source not found: {source_name}", code="source_not_found")

        final_mount_id = mount_id or f"{source_name}-{operation_id}".replace(".", "-").replace("_", "-")
        if app.catalog.find_by_id(final_mount_id) is not None:
            raise RegistryError(f"mount already exists: {final_mount_id}", code="mount_exists")

        command_path = _split_command_segments(command_path_values)
        under_path = _split_command_segments(under_values)
        alias_paths = [_split_command_segments([item]) for item in alias_values]
        if not command_path and not under_path:
            command_path = tokenize_identifier(operation_id)

        baseline_conflicts = conflict_signatures(app.catalog.conflicts)

        def mutator(payload: Dict[str, Any]) -> None:
            mounts = ensure_list(payload, "mounts")
            mount_payload: Dict[str, Any] = {
                "id": final_mount_id,
                "source": source_name,
                "operation": operation_id,
            }
            command_payload: Dict[str, Any] = {}
            if command_path:
                command_payload["path"] = command_path
            if under_path:
                command_payload["under"] = under_path
            if alias_paths:
                command_payload["aliases"] = alias_paths
            if command_payload:
                mount_payload["command"] = command_payload

            machine_payload: Dict[str, Any] = {}
            if stable_name:
                machine_payload["stable_name"] = stable_name
            if surfaces:
                machine_payload["expose_via"] = list(surfaces)
            if machine_payload:
                mount_payload["machine"] = machine_payload

            help_payload: Dict[str, Any] = {}
            if summary:
                help_payload["summary"] = summary
            if description:
                help_payload["description"] = description
            if notes:
                help_payload["notes"] = list(notes)
            if examples:
                help_payload["examples"] = list(examples)
            if help_payload:
                mount_payload["help"] = help_payload

            if risk:
                mount_payload["policy"] = {"risk": risk}

            params_payload = _build_param_payload(
                param_specs=param_specs,
                required_params=required_params,
                param_help_items=param_help_items,
                param_default_items=param_default_items,
                param_flag_items=param_flag_items,
            )
            if params_payload:
                mount_payload["params"] = params_payload

            for assignment in assignments:
                path, value = _parse_assignment(assignment)
                apply_assignment(mount_payload, path, value)

            mounts.append(mount_payload)

        updated, compiled_app = apply_update(
            session,
            mutator,
            compile_runtime=True,
            profile=state.profile,
            baseline_conflicts=baseline_conflicts,
        )
        compiled_mount = compiled_app.catalog.find_by_id(final_mount_id) if compiled_app else None
        payload = {
            "ok": True,
            "action": "mount_add",
            "mount_id": final_mount_id,
            "file": str(session.target_path),
            "created_file": session.created,
            "warnings": list(session.warnings),
            "config": _find_mount_payload(updated.get("mounts", []), final_mount_id),
            "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "mount_add", output_format)


@mount.command("list")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@pass_app
def mount_list(app: CTSApp, output_format: str) -> None:
    payload = {"mounts": [mount.to_summary() for mount in app.catalog.mounts], "conflicts": app.catalog.conflicts}
    click.echo(render_payload(payload, output_format))


@mount.command("show")
@click.argument("mount_id")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def mount_show(app: CTSApp, mount_id: str, output_format: str) -> None:
    mount = app.catalog.find_by_id(mount_id)
    if not mount:
        _fail(click.get_current_context(), RegistryError(f"mount not found: {mount_id}", code="mount_not_found"), "show_mount", output_format)
        return
    click.echo(render_payload(build_mount_details(app, mount), output_format))


@main.group("alias")
def alias_group() -> None:
    """Top-level alias operations."""


@alias_group.command("list")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def alias_list(app: CTSApp, output_format: str) -> None:
    items = []
    for raw in app.config.aliases:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "from": raw.get("from"),
                "to": raw.get("to"),
            }
        )
    click.echo(render_payload({"items": items}, output_format))


@alias_group.command("add")
@click.argument("alias_from")
@click.argument("alias_to")
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write into a specific loaded config file.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def alias_add(ctx: click.Context, alias_from: str, alias_to: str, target_file: Optional[Path], output_format: str) -> None:
    state = _get_state(ctx)
    try:
        session = prepare_edit_session(state.config_path, target_file=target_file)
        app = CTSApp(
            session.loaded,
            active_profile=state.profile,
            explicit_config_path=str(state.config_path) if state.config_path else None,
            requested_profile=state.profile,
        )
        from_tokens = _split_command_segments([alias_from])
        to_tokens = _split_command_segments([alias_to])
        target_mount = app.catalog.find_by_path(to_tokens)
        if target_mount is None:
            raise RegistryError(
                f"alias target path not found: {' '.join(to_tokens)}",
                code="alias_target_not_found",
            )
        existing = app.catalog.find_by_path(from_tokens)
        if existing is not None:
            raise RegistryError(
                f"alias path already exists: {' '.join(from_tokens)}",
                code="alias_conflict",
            )

        baseline_conflicts = conflict_signatures(app.catalog.conflicts)

        def mutator(payload: Dict[str, Any]) -> None:
            aliases = ensure_list(payload, "aliases")
            aliases.append({"from": from_tokens, "to": to_tokens})

        updated, compiled_app = apply_update(
            session,
            mutator,
            compile_runtime=True,
            profile=state.profile,
            baseline_conflicts=baseline_conflicts,
        )
        resolved_alias_mount = compiled_app.catalog.find_by_path(from_tokens) if compiled_app else None
        payload = {
            "ok": True,
            "action": "alias_add",
            "file": str(session.target_path),
            "created_file": session.created,
            "warnings": list(session.warnings),
            "alias": {"from": from_tokens, "to": to_tokens},
            "mount_id": resolved_alias_mount.mount_id if resolved_alias_mount else target_mount.mount_id,
            "config": _find_alias_payload(updated.get("aliases", []), from_tokens),
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "alias_add", output_format)


@alias_group.command("remove")
@click.argument("alias_from")
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Remove from a specific loaded config file.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def alias_remove(ctx: click.Context, alias_from: str, target_file: Optional[Path], output_format: str) -> None:
    state = _get_state(ctx)
    try:
        session = prepare_edit_session(state.config_path, target_file=target_file)
        from_tokens = _split_command_segments([alias_from])
        removed: Optional[Dict[str, Any]] = None

        def mutator(payload: Dict[str, Any]) -> None:
            nonlocal removed
            aliases = ensure_list(payload, "aliases")
            remaining = []
            for item in aliases:
                if removed is None and isinstance(item, dict) and item.get("from") == from_tokens:
                    removed = item
                    continue
                remaining.append(item)
            if removed is None:
                raise RegistryError(
                    f"alias not found: {' '.join(from_tokens)}",
                    code="alias_not_found",
                )
            payload["aliases"] = remaining

        updated, _ = apply_update(session, mutator, compile_runtime=False)
        payload = {
            "ok": True,
            "action": "alias_remove",
            "file": str(session.target_path),
            "created_file": session.created,
            "warnings": list(session.warnings),
            "alias": removed,
            "remaining_count": len(updated.get("aliases", [])),
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "alias_remove", output_format)


@main.group()
def catalog() -> None:
    """Catalog export commands."""


@catalog.command("export")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def catalog_export(app: CTSApp, output_format: str) -> None:
    click.echo(render_payload(app.export_catalog(), output_format))


@main.group()
def inspect() -> None:
    """Inspect compiled sources, mounts, and operations."""


@inspect.command("mount")
@click.argument("mount_id")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def inspect_mount(app: CTSApp, mount_id: str, output_format: str) -> None:
    mount = app.catalog.find_by_id(mount_id)
    if not mount:
        _fail(click.get_current_context(), RegistryError(f"mount not found: {mount_id}", code="mount_not_found"), "inspect_mount", output_format)
        return
    click.echo(render_payload(build_mount_details(app, mount), output_format))


@inspect.command("source")
@click.argument("source_name")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def inspect_source(app: CTSApp, source_name: str, output_format: str) -> None:
    source = app.config.sources.get(source_name)
    if not source:
        _fail(click.get_current_context(), RegistryError(f"source not found: {source_name}", code="source_not_found"), "inspect_source", output_format)
        return
    click.echo(render_payload(build_source_details(app, source_name, source), output_format))


@inspect.command("operation")
@click.argument("source_name")
@click.argument("operation_id")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def inspect_operation(app: CTSApp, source_name: str, operation_id: str, output_format: str) -> None:
    source = app.config.sources.get(source_name)
    operation = app.source_operations.get(source_name, {}).get(operation_id)
    if not operation:
        _fail(
            click.get_current_context(),
            RegistryError(f"operation not found: {source_name}.{operation_id}", code="operation_not_found"),
            "inspect_operation",
            output_format,
        )
        return
    schema_info = app.get_schema_info(source_name, source, operation_id) if source else None
    payload = operation.model_dump(mode="json")
    payload["source_origin_file"] = _path_to_str(app.origin_file_for(source))
    payload["schema_provenance"] = schema_info[1] if schema_info else None
    click.echo(render_payload(payload, output_format))


@inspect.command("drift")
@click.argument("source_name", required=False)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def inspect_drift(app: CTSApp, source_name: Optional[str], output_format: str) -> None:
    report = app.discovery_store.load_latest_sync_report(source_name)
    if not report:
        _fail(
            click.get_current_context(),
            RegistryError(
                "no sync report available",
                code="drift_report_not_found",
                suggestions=["先执行 `cts sync`，再查看 drift 结果。"],
            ),
            "inspect_drift",
            output_format,
        )
        return
    items = list(report.get("items") or [])
    if source_name:
        items = [item for item in items if item.get("source") == source_name]
        if not items:
            _fail(
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


@main.command()
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
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def invoke(
    app: CTSApp,
    mount_id: str,
    input_json: Optional[str],
    input_file: Optional[Path],
    dry_run: bool,
    non_interactive: bool,
    output_format: str,
) -> None:
    mount = app.catalog.find_by_id(mount_id)
    if not mount:
        _fail(click.get_current_context(), RegistryError(f"mount not found: {mount_id}", code="mount_not_found"), "invoke", output_format)
        return

    kwargs = {
        "input_json": input_json,
        "input_file": input_file,
        "dry_run": dry_run,
        "non_interactive": non_interactive,
        "output_format": output_format,
    }
    _run_mount_command(app, mount, kwargs, mode="invoke")


@main.command()
@click.argument("mount_id")
@click.option("--input-json", default=None, help="Raw JSON object input.")
@click.option(
    "--input-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Path to a JSON file containing operation input.",
)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def explain(app: CTSApp, mount_id: str, input_json: Optional[str], input_file: Optional[Path], output_format: str) -> None:
    mount = app.catalog.find_by_id(mount_id)
    if not mount:
        _fail(click.get_current_context(), RegistryError(f"mount not found: {mount_id}", code="mount_not_found"), "explain", output_format)
        return
    kwargs = {
        "input_json": input_json,
        "input_file": input_file,
        "output_format": output_format,
        "dry_run": False,
        "non_interactive": True,
    }
    _run_mount_command(app, mount, kwargs, mode="explain")


@main.command()
@click.argument("source_name", required=False)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def sync(app: CTSApp, source_name: Optional[str], output_format: str) -> None:
    payload = app.sync(source_name)
    click.echo(render_payload(payload, output_format))


@main.group()
def reconcile() -> None:
    """Drift reconciliation commands."""


@reconcile.command("drift")
@click.argument("source_name")
@click.option("--action", "reconcile_action", type=click.Choice(["accept-breaking"]), default="accept-breaking", show_default=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def reconcile_drift(app: CTSApp, source_name: str, reconcile_action: str, output_format: str) -> None:
    report = app.discovery_store.load_latest_sync_report(source_name)
    if not report:
        _fail(
            click.get_current_context(),
            RegistryError(
                "no sync report available",
                code="drift_report_not_found",
                suggestions=["先执行 `cts sync`，再执行 drift reconcile。"],
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
        _fail(
            click.get_current_context(),
            RegistryError(
                f"no blocking drift found for source: {source_name}",
                code="drift_not_reconcilable",
                suggestions=["先执行 `cts inspect drift " + source_name + "` 查看当前 drift 状态。"],
            ),
            "reconcile_drift",
            output_format,
        )
        return

    normalized_action = reconcile_action.replace("-", "_")
    report_generated_at = str(source_state.get("report_generated_at") or report.get("generated_at") or "")
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


@main.group()
def auth() -> None:
    """Authentication status commands."""


@auth.command("list")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def auth_list(app: CTSApp, output_format: str) -> None:
    click.echo(render_payload(build_auth_inventory(app), output_format))


@auth.command("status")
@click.argument("name", required=False)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def auth_status(app: CTSApp, name: Optional[str], output_format: str) -> None:
    try:
        if name:
            payload = build_auth_profile(app, name)
        else:
            payload = build_auth_inventory(app)
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "auth_status", output_format)


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
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def auth_login(
    app: CTSApp,
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
        _fail(click.get_current_context(), exc, "auth_login", output_format)


@auth.command("refresh")
@click.argument("name")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def auth_refresh(app: CTSApp, name: str, output_format: str) -> None:
    try:
        payload = {
            "ok": True,
            "action": "auth_refresh",
            "profile": app.auth_manager.refresh(name),
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "auth_refresh", output_format)


@auth.command("logout")
@click.argument("name")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def auth_logout(app: CTSApp, name: str, output_format: str) -> None:
    try:
        payload = {
            "ok": True,
            "action": "auth_logout",
            "profile": app.auth_manager.logout(name),
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "auth_logout", output_format)


@main.group()
def secret() -> None:
    """Secret inventory commands."""


@secret.command("list")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def secret_list(app: CTSApp, output_format: str) -> None:
    click.echo(render_payload(build_secret_inventory(app), output_format))


@secret.command("show")
@click.argument("name")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def secret_show(app: CTSApp, name: str, output_format: str) -> None:
    try:
        click.echo(render_payload(build_secret_detail(app, name), output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "secret_show", output_format)


@main.group()
def runs() -> None:
    """Run history inspection commands."""


@runs.command("list")
@click.option("--limit", type=click.IntRange(1, 200), default=20, show_default=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def runs_list(app: CTSApp, limit: int, output_format: str) -> None:
    payload = {"items": list_runs(app, limit=limit)}
    click.echo(render_payload(payload, output_format))


@runs.command("show")
@click.argument("run_id")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def runs_show(app: CTSApp, run_id: str, output_format: str) -> None:
    payload = get_run(app, run_id)
    if payload is None:
        _fail(click.get_current_context(), RegistryError(f"run not found: {run_id}", code="run_not_found"), "show_run", output_format)
        return
    click.echo(render_payload(payload, output_format))


@main.group()
def completion() -> None:
    """Shell completion helpers."""


@completion.command("script")
@click.option("--shell", "shell_name", type=click.Choice(["bash", "zsh", "fish"]), required=True)
def completion_script(shell_name: str) -> None:
    completion_class = get_completion_class(shell_name)
    if completion_class is None:
        raise click.ClickException(f"unsupported shell: {shell_name}")
    prog_name = main.name or "cts"
    complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"
    shell_complete = completion_class(main, {}, prog_name, complete_var)
    click.echo(shell_complete.source())


@main.group()
def serve() -> None:
    """Northbound surface commands."""


@serve.command("http")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8787, show_default=True)
@click.option("--ui", "serve_ui", is_flag=True, help="Also serve the built frontend UI if available.")
@click.option("--ui-dir", type=click.Path(path_type=Path, file_okay=False), default=None, help="Explicit frontend dist directory.")
@pass_app
def serve_http_command(app: CTSApp, host: str, port: int, serve_ui: bool, ui_dir: Optional[Path]) -> None:
    resolved_ui_dir: Optional[Path] = None
    if ui_dir is not None:
        resolved_ui_dir = ui_dir.resolve()
    elif serve_ui:
        candidate = default_ui_dist_dir()
        if not candidate.exists():
            _fail(
                click.get_current_context(),
                RegistryError(
                    f"ui dist directory not found: {candidate}",
                    code="ui_dist_not_found",
                    suggestions=["先在 frontend/app 下执行 `npm run build`，或显式传入 `--ui-dir`。"],
                ),
                "serve_http",
                "json",
            )
            return
        resolved_ui_dir = candidate.resolve()

    server = create_http_server(app, host=host, port=port, ui_dir=resolved_ui_dir)
    actual_host, actual_port = server.server_address
    click.echo(
        json.dumps(
            {
                "ok": True,
                "surface": "http",
                "base_url": f"http://{actual_host}:{actual_port}",
                "ui_enabled": resolved_ui_dir is not None,
                "ui_dir": str(resolved_ui_dir) if resolved_ui_dir else None,
            }
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


@main.command()
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def doctor(app: CTSApp, output_format: str) -> None:
    checks = [build_source_check_result(app, source_name, source) for source_name, source in app.config.sources.items()]
    summary = build_app_summary(app)
    payload = {
        "config_paths": [str(path) for path in app.config_paths],
        "conflicts": app.catalog.conflicts,
        "plugin_provider_conflicts": summary["plugin_provider_conflicts"],
        "discovery_errors": app.discovery_errors,
        "checks": checks,
        "runtime_paths": summary["runtime_paths"],
    }
    click.echo(render_payload(payload, output_format))


def build_dynamic_command(app: CTSApp, mount) -> click.Command:
    emit_app_event(
        app,
        event="help_compile_start",
        source=mount.source_name,
        mount_id=mount.mount_id,
        operation_id=mount.operation.id,
    )
    help_payload = build_mount_help(app, mount)
    emit_app_event(
        app,
        event="help_compile_complete",
        source=mount.source_name,
        mount_id=mount.mount_id,
        operation_id=mount.operation.id,
        data={"schema_provenance": help_payload.get("schema_provenance")},
    )
    return click.Command(
        name=mount.command_path[-1],
        params=build_click_params(mount),
        callback=_dynamic_callback(mount),
        short_help=help_payload["summary"],
        help=help_payload["description"],
        epilog=help_payload["epilog"],
    )


def _dynamic_callback(mount):
    @click.pass_context
    def callback(ctx, **kwargs):
        try:
            app = _get_app(ctx)
        except Exception as exc:
            _fail(ctx, exc, "config_load", _error_output_format(ctx, kwargs.get("output_format")))
            return
        _run_mount_command(app, mount, kwargs, mode="invoke")

    return callback


def _run_mount_command(app: CTSApp, mount, kwargs: Dict[str, Any], mode: str) -> None:
    output_format = kwargs.get("output_format") or getattr(app, "global_output", "text")
    run_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    started_at = utc_now_iso()

    try:
        payload, runtime = extract_request_args(kwargs)
        runtime["run_id"] = run_id
        runtime["trace_id"] = trace_id
        app.ensure_mount_execution_allowed(mount, mode=mode, run_id=run_id, trace_id=trace_id)
        emit_app_event(
            app,
            event=f"{mode}_start",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"args": payload, "provider_type": mount.provider_type},
        )
        if mode == "explain":
            result = explain_mount(app, mount, payload, runtime)
        else:
            result = invoke_mount(app, mount, payload, runtime)
        emit_app_event(
            app,
            event=f"{mode}_complete",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"result": summarize_result(result)},
        )
        emit_audit_event(
            app,
            event=f"{mode}_complete",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"ok": result.get("ok"), "risk": mount.operation.risk, "provider_type": mount.provider_type},
        )
        record_run(
            app,
            {
                "run_id": run_id,
                "trace_id": trace_id,
                "ts_start": started_at,
                "ts_end": utc_now_iso(),
                "surface": "cli",
                "mode": mode,
                "ok": result.get("ok", False),
                "exit_code": 0 if result.get("ok") else 6,
                "profile": app.active_profile,
                "mount_id": mount.mount_id,
                "stable_name": mount.stable_name,
                "source": mount.source_name,
                "operation_id": mount.operation.id,
                "provider_type": mount.provider_type,
                "summary": mount.summary or mount.operation.title,
                "metadata": {"result": summarize_result(result)},
            },
        )
        click.echo(render_payload(result, output_format))
    except Exception as exc:
        exit_code = exit_code_for_exception(exc, mode)
        error_payload = build_error_envelope(exc, mode, mount=mount, run_id=run_id, trace_id=trace_id)
        emit_app_event(
            app,
            event=f"{mode}_failed",
            level="ERROR",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"error": error_payload["error"], "exit_code": exit_code},
        )
        emit_audit_event(
            app,
            event=f"{mode}_failed",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"error_type": error_payload["error"]["type"], "error_code": error_payload["error"]["code"]},
        )
        record_run(
            app,
            {
                "run_id": run_id,
                "trace_id": trace_id,
                "ts_start": started_at,
                "ts_end": utc_now_iso(),
                "surface": "cli",
                "mode": mode,
                "ok": False,
                "exit_code": exit_code,
                "profile": app.active_profile,
                "mount_id": mount.mount_id,
                "stable_name": mount.stable_name,
                "source": mount.source_name,
                "operation_id": mount.operation.id,
                "provider_type": mount.provider_type,
                "summary": mount.summary or mount.operation.title,
                "error_type": error_payload["error"]["type"],
                "error_code": error_payload["error"]["code"],
                "metadata": {"error": error_payload["error"]},
            },
        )
        _fail(click.get_current_context(), exc, mode, output_format, mount=mount, run_id=run_id, trace_id=trace_id)


def _get_app(ctx: click.Context) -> CTSApp:
    return _get_state(ctx).get_app()


def _get_state(ctx: click.Context) -> CLIState:
    root = ctx.find_root()
    if isinstance(root.obj, CLIState):
        return root.obj

    config_path = root.params.get("config_path")
    profile = root.params.get("profile")
    global_output = root.params.get("global_output", "text")
    if config_path is None and not root.params:
        raw = _parse_root_argv(sys.argv[1:])
        config_path = raw.get("config_path")
        profile = raw.get("profile")
        global_output = raw.get("global_output", global_output)
    root.obj = CLIState(config_path=config_path, profile=profile, global_output=global_output)
    return root.obj


def _parse_root_argv(argv: list[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--config" and index + 1 < len(argv):
            parsed["config_path"] = Path(argv[index + 1])
            index += 2
            continue
        if token == "--profile" and index + 1 < len(argv):
            parsed["profile"] = argv[index + 1]
            index += 2
            continue
        if token == "--output" and index + 1 < len(argv):
            parsed["global_output"] = argv[index + 1]
            index += 2
            continue
        index += 1
    return parsed


def _parse_assignment(raw: str) -> tuple[str, Any]:
    return parse_assignment(raw)


def _parse_string_pair(raw: str, *, field_name: str) -> tuple[str, str]:
    return parse_string_map_item(raw, field_name=field_name)


def _split_command_segments(values: tuple[str, ...] | list[str]) -> List[str]:
    tokens: List[str] = []
    for value in values:
        tokens.extend(shlex.split(value))
    return tokens


def _build_param_payload(
    *,
    param_specs: tuple[str, ...],
    required_params: tuple[str, ...],
    param_help_items: tuple[str, ...],
    param_default_items: tuple[str, ...],
    param_flag_items: tuple[str, ...],
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for spec in param_specs:
        name, param_type = _parse_param_spec(spec)
        params[name] = {"type": param_type}

    for name in required_params:
        params.setdefault(name, {"type": "string"})
        params[name]["required"] = True

    for item in param_help_items:
        name, text = _parse_string_pair(item, field_name="param-help")
        params.setdefault(name, {"type": "string"})
        params[name]["help"] = text

    for item in param_default_items:
        name, raw_value = _parse_assignment(item)
        params.setdefault(name, {"type": "string"})
        params[name]["default"] = raw_value

    for item in param_flag_items:
        name, flag = _parse_string_pair(item, field_name="param-flag")
        params.setdefault(name, {"type": "string"})
        params[name]["flag"] = flag

    return params


def _parse_param_spec(spec: str) -> tuple[str, str]:
    if ":" in spec:
        name, param_type = spec.split(":", 1)
    else:
        name, param_type = spec, "string"
    name = name.strip()
    param_type = param_type.strip() or "string"
    if not name:
        raise ConfigEditError(f"param 不能为空: {spec}")
    return name, param_type


def _find_mount_payload(items: List[Dict[str, Any]], mount_id: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and item.get("id") == mount_id:
            return _strip_internal_metadata(item)
    return None


def _find_alias_payload(items: List[Dict[str, Any]], from_tokens: List[str]) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and item.get("from") == from_tokens:
            return _strip_internal_metadata(item)
    return None


def _path_to_str(path: Optional[Path]) -> Optional[str]:
    return str(path) if path else None


def _serialize_error(exc: Exception, stage: str) -> Dict[str, Any]:
    return build_error_envelope(exc, stage)["error"]


def _error_output_format(ctx: click.Context, requested_output: Optional[str]) -> str:
    if requested_output == "json":
        return "json"
    return _get_state(ctx).global_output


def _build_error_command(name: str, exc: Exception) -> click.Command:
    @click.pass_context
    def callback(ctx: click.Context) -> None:
        _fail(ctx, exc, "config_load", _error_output_format(ctx, None))

    return click.Command(name=name, callback=callback, help="Configuration failed to load.")


def _strip_internal_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_internal_metadata(item) for key, item in value.items() if not key.startswith("__")}
    if isinstance(value, list):
        return [_strip_internal_metadata(item) for item in value]
    return value


def _fail(
    ctx: click.Context,
    exc: Exception,
    stage: str,
    output_format: str,
    mount=None,
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> None:
    payload = build_error_envelope(exc, stage, mount=mount, run_id=run_id, trace_id=trace_id)
    click.echo(render_payload(payload, output_format))
    ctx.exit(exit_code_for_exception(exc, stage))
