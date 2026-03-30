from __future__ import annotations

import json
import shlex
import sys
import uuid
import webbrowser
from collections import OrderedDict
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
from cts.execution.errors import ConfigError, RegistryError, exit_code_for_exception
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
from cts.importers import (
    import_cli_completion,
    import_cli_help,
    import_cli_manpage,
    import_cli_schema,
    inspect_cli_help,
    merge_operation_into_manifest,
    write_manifest_operations,
)
from cts.execution.runtime import build_error_envelope, explain_mount, invoke_mount, render_payload
from cts.presentation import (
    build_app_summary,
    build_auth_inventory,
    build_auth_profile,
    build_mount_details,
    build_mount_help,
    build_reliability_status,
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


class GroupedOptionCommand(click.Command):
    def format_options(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        sections: "OrderedDict[str, List[tuple[str, str]]]" = OrderedDict()

        for param in self.get_params(ctx):
            rv = param.get_help_record(ctx)
            if rv is None:
                continue
            section_name = getattr(param, "help_group", "Options")
            sections.setdefault(section_name, []).append(rv)

        for section_name, records in sections.items():
            if not records:
                continue
            with formatter.section(section_name):
                formatter.write_dl(records)


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
def manage() -> None:
    """CTS administration and maintenance commands."""


@manage.group()
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


@config.command("migrate")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying them.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def config_migrate(ctx: click.Context, dry_run: bool, output_format: str) -> None:
    """Migrate configuration to the latest version.
    
    This command analyzes the current configuration and applies
    any necessary migrations to bring it up to the latest version.
    
    Use --dry-run to preview what changes would be made.
    """
    from cts.config.migration import MigrationManager, get_latest_version
    from cts.config.loader import load_config
    
    state = _get_state(ctx)
    config_path = str(state.config_path) if state.config_path else None
    
    try:
        loaded = load_config(config_path)
        raw_config = loaded.raw if hasattr(loaded, 'raw') else loaded.config.model_dump()
        
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
        _fail(ctx, exc, "config_migrate", output_format)


@manage.group()
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


@source.command("remove")
@click.argument("source_name")
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Remove from a specific config file.")
@click.option("--force", is_flag=True, help="Force removal even if mounts depend on this source.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def source_remove(
    ctx: click.Context,
    source_name: str,
    target_file: Optional[Path],
    force: bool,
    output_format: str,
) -> None:
    """Remove a source from configuration.
    
    This will also remove any mounts that reference this source,
    unless --force is not specified and dependent mounts exist.
    """
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
        
        # Find dependent mounts
        dependent_mounts = [
            mount for mount in app.catalog.mounts
            if mount.source_name == source_name
        ]
        
        if dependent_mounts and not force:
            raise RegistryError(
                f"source '{source_name}' has {len(dependent_mounts)} dependent mount(s)",
                code="source_has_dependents",
                suggestions=[
                    "使用 --force 强制删除（同时删除依赖的 mount）",
                    f"先手动删除依赖的 mount: {', '.join(m.mount_id for m in dependent_mounts[:5])}"
                ],
            )
        
        def mutator(payload: Dict[str, Any]) -> None:
            sources = payload.get("sources", {})
            if source_name in sources:
                del sources[source_name]
            if not sources:
                payload.pop("sources", None)
            
            # Also remove dependent mounts if --force
            if dependent_mounts:
                mounts = payload.get("mounts", [])
                if isinstance(mounts, list):
                    remaining = [
                        m for m in mounts
                        if not (isinstance(m, dict) and m.get("source") == source_name)
                    ]
                    if remaining:
                        payload["mounts"] = remaining
                    else:
                        payload.pop("mounts", None)
        
        updated, _ = apply_update(session, mutator, compile_runtime=False)
        
        payload = {
            "ok": True,
            "action": "source_remove",
            "source_name": source_name,
            "file": str(session.target_path),
            "removed_mounts": [m.mount_id for m in dependent_mounts] if dependent_mounts else [],
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "source_remove", output_format)


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


@main.group("import")
def import_group() -> None:
    """Simplified import flows for common onboarding tasks."""


@import_group.command("cli")
@click.argument("source_name")
@click.argument("command_argv", nargs=-1)
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write into a specific loaded config file.")
@click.option("--operation-id", default=None, help="Operation id. Defaults to a name derived from the command.")
@click.option("--from", "import_strategy", type=click.Choice(["help", "completion", "manpage", "schema"]), default="help", show_default=True)
@click.option("--bin", "executable", default=None, help="Executable to store on the source. Defaults to the first command token.")
@click.option("--title", default=None)
@click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
@click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--help-flag", default="--help", show_default=True)
@click.option("--completion-command", default=None, help="Shell-escaped command that prints completion candidates.")
@click.option("--completion-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
@click.option("--completion-format", type=click.Choice(["lines", "fish", "json"]), default="lines", show_default=True)
@click.option("--man-command", default=None, help="Shell-escaped command that prints a plain-text man page.")
@click.option("--man-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
@click.option("--schema-command", default=None, help="Shell-escaped command that prints a JSON schema payload.")
@click.option("--schema-file", type=click.Path(path_type=Path, dir_okay=False, exists=True), default=None)
@click.option("--schema-format", type=click.Choice(["auto", "operation", "bindings", "options"]), default="auto", show_default=True)
@click.option("--all", "import_all", is_flag=True, help="Recursively import the full CLI command tree using nested help output.")
@click.option("--apply", is_flag=True, help="Write the imported source operation and mount into config.")
@click.option("--save-manifest", "save_manifest_path", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Optional manifest file to write instead of storing the operation inline.")
@click.option("--mount/--no-mount", "create_mount", default=True, show_default=True, help="Also create a mount for the imported operation.")
@click.option("--mount-id", default=None, help="Mount id override. Defaults to an auto-generated stable id.")
@click.option("--path", "command_path_value", default=None, help="Full mount command path. Defaults to '<source> <operation>'.")
@click.option("--under", "under_values", multiple=True, help="Command path prefix used together with the operation tokens.")
@click.option("--prefix", default=None, help="Mount id prefix. Defaults to the source name.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def import_cli_command(
    ctx: click.Context,
    source_name: str,
    command_argv: tuple[str, ...],
    target_file: Optional[Path],
    operation_id: Optional[str],
    import_strategy: str,
    executable: Optional[str],
    title: Optional[str],
    risk: str,
    output_mode: str,
    help_flag: str,
    completion_command: Optional[str],
    completion_file: Optional[Path],
    completion_format: str,
    man_command: Optional[str],
    man_file: Optional[Path],
    schema_command: Optional[str],
    schema_file: Optional[Path],
    schema_format: str,
    import_all: bool,
    apply: bool,
    save_manifest_path: Optional[Path],
    create_mount: bool,
    mount_id: Optional[str],
    command_path_value: Optional[str],
    under_values: tuple[str, ...],
    prefix: Optional[str],
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
        if import_all:
            if import_strategy != "help":
                raise RegistryError(
                    "--all currently supports --from help only",
                    code="import_all_strategy_unsupported",
                    suggestions=["改用 `cts import cli <source> <cmd> --all --from help --apply`。"],
                )
            if operation_id is not None or mount_id is not None or command_path_value is not None or title is not None:
                raise RegistryError(
                    "--all cannot be combined with per-command identity overrides",
                    code="import_all_overrides_not_supported",
                    suggestions=["去掉 --operation-id / --mount-id / --path / --title，改用 --under 或 --prefix 控制整棵树路径。"],
                )
            plan = _prepare_cli_import_tree_plan(
                app,
                source_name=source_name,
                command_argv=list(command_argv),
                executable=executable,
                risk=risk,
                output_mode=output_mode,
                help_flag=help_flag,
                create_mount=create_mount,
                under_values=under_values,
                prefix=prefix,
                save_manifest_path=save_manifest_path,
            )
            if not apply:
                click.echo(
                    render_payload(
                        {
                            "ok": True,
                            "action": "import_cli_tree_preview",
                            **plan,
                        },
                        output_format,
                    )
                )
                return

            manifest_write = dict(plan["manifest_write"])
            write_manifest_operations(
                Path(manifest_write["resolved_path"]),
                list(manifest_write["operations"]),
                executable=manifest_write.get("executable"),
            )

            baseline_conflicts = conflict_signatures(app.catalog.conflicts)

            def mutator(payload: Dict[str, Any]) -> None:
                _apply_cli_import_tree_plan(payload, plan)

            updated, compiled_app = apply_update(
                session,
                mutator,
                compile_runtime=True,
                profile=state.profile,
                baseline_conflicts=baseline_conflicts,
            )

            click.echo(
                render_payload(
                    {
                        "ok": True,
                        "action": "import_cli_tree_apply",
                        "file": str(session.target_path),
                        "created_file": session.created,
                        "warnings": list(session.warnings),
                        **plan,
                        "source_config": _strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
                        "mount_count": len(plan.get("mounts") or []),
                        "operation_count": len(plan.get("operations") or []),
                    },
                    output_format,
                )
            )
            return

        plan = _prepare_cli_import_plan(
            app,
            source_name=source_name,
            command_argv=list(command_argv),
            operation_id=operation_id,
            import_strategy=import_strategy,
            executable=executable,
            title=title,
            risk=risk,
            output_mode=output_mode,
            help_flag=help_flag,
            completion_command=completion_command,
            completion_file=completion_file,
            completion_format=completion_format,
            man_command=man_command,
            man_file=man_file,
            schema_command=schema_command,
            schema_file=schema_file,
            schema_format=schema_format,
            create_mount=create_mount,
            mount_id=mount_id,
            command_path_value=command_path_value,
            under_values=under_values,
            prefix=prefix,
            save_manifest_path=save_manifest_path,
        )

        if not apply:
            payload = {
                "ok": True,
                "action": "import_cli_preview",
                **plan,
            }
            click.echo(render_payload(payload, output_format))
            return

        if plan.get("manifest_write"):
            manifest_write = dict(plan["manifest_write"])
            merge_operation_into_manifest(
                Path(manifest_write["resolved_path"]),
                dict(manifest_write["operation"]),
                executable=manifest_write.get("executable"),
            )

        baseline_conflicts = conflict_signatures(app.catalog.conflicts)

        def mutator(payload: Dict[str, Any]) -> None:
            _apply_cli_import_plan(payload, plan)

        updated, compiled_app = apply_update(
            session,
            mutator,
            compile_runtime=True,
            profile=state.profile,
            baseline_conflicts=baseline_conflicts,
        )

        compiled_mount = None
        if compiled_app and plan.get("mount"):
            compiled_mount = compiled_app.catalog.find_by_id(plan["mount"]["id"])

        payload = {
            "ok": True,
            "action": "import_cli_apply",
            "file": str(session.target_path),
            "created_file": session.created,
            "warnings": list(session.warnings),
            **plan,
            "source_config": _strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
            "mount_config": _find_mount_payload(updated.get("mounts", []), plan["mount"]["id"]) if plan.get("mount") else None,
            "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "import_cli", output_format)


@import_group.command("shell")
@click.argument("source_name")
@click.option("--exec", "exec_command", default=None, help="Shell command string to execute.")
@click.option(
    "--script-file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Path to a shell script file to execute.",
)
@click.option("--shell-bin", default="/bin/sh", show_default=True, help="Shell executable used to run the command.")
@click.option("--under", "under_values", multiple=True, help="Command path prefix for the generated mount.")
@click.option("--title", default=None, help="Optional operation title.")
@click.option("--description", default=None, help="Optional operation description.")
@click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default="read", show_default=True)
@click.option("--output-mode", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--apply", is_flag=True, help="Write the shell source and mount into config.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def import_shell_command(
    ctx: click.Context,
    source_name: str,
    exec_command: Optional[str],
    script_file: Optional[Path],
    shell_bin: str,
    under_values: tuple[str, ...],
    title: Optional[str],
    description: Optional[str],
    risk: str,
    output_mode: str,
    apply: bool,
    output_format: str,
) -> None:
    """Import a shell command string as a runnable mount."""
    try:
        if bool(exec_command) == bool(script_file):
            raise RegistryError(
                "exactly one of --exec or --script-file is required",
                code="shell_import_source_required",
                suggestions=["传入 --exec 'echo hello'，或传入 --script-file ./script.sh。"],
            )
        payload = _execute_import_shell(
            ctx,
            source_name=source_name,
            exec_command=exec_command,
            script_file=script_file,
            shell_bin=shell_bin,
            under_values=under_values,
            title=title,
            description=description,
            risk=risk,
            output_mode=output_mode,
            apply=apply,
        )
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "import_shell", output_format)


@import_group.command("mcp")
@click.argument("source_name")
@click.option("--server-config", type=str, help="MCP server configuration as JSON string.")
@click.option("--server-name", type=str, help="Server name in the servers.json file.")
@click.option("--config-file", type=click.Path(path_type=Path), default=None, help="Path to servers.json. Defaults to ./servers.json.")
@click.option("--under", "under_values", multiple=True, help="Command path prefix for all imported mounts.")
@click.option("--apply", is_flag=True, help="Apply the MCP source and import all tools as mounts.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def import_mcp_command(
    ctx: click.Context,
    source_name: str,
    server_config: Optional[str],
    server_name: Optional[str],
    config_file: Optional[Path],
    under_values: tuple[str, ...],
    apply: bool,
    output_format: str,
) -> None:
    """Import an MCP server and batch import its tools.
    
    This command creates an MCP source configuration and imports all
    discovered tools as mounts in one step.
    
    Examples:
        cts import mcp my-mcp --server-config '{"type":"sse","url":"https://..."}' --apply
        cts import mcp my-mcp --server-name my-server --config-file ./servers.json --apply
    """
    try:
        payload = _execute_import_mcp(
            ctx,
            source_name=source_name,
            server_config=server_config,
            server_name=server_name,
            config_file=config_file,
            under_values=under_values,
            apply=apply,
        )
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "import_mcp", output_format)


@import_group.command("wizard")
@click.option("--apply", is_flag=True, help="Write the imported source operation and mount into config after the wizard.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def import_wizard(ctx: click.Context, apply: bool, output_format: str) -> None:
    """Interactive wizard for simplified imports."""
    import_type = click.prompt("Import type", type=click.Choice(["cli", "mcp"]), default="cli", show_choices=False)

    if import_type == "mcp":
        source_name = click.prompt("Source name")
        server_config = click.prompt("Server config JSON (optional)", default="", show_default=False).strip() or None
        server_name = click.prompt("Server name (optional)", default="", show_default=False).strip() or None
        config_file_raw = click.prompt("servers.json path (optional)", default="", show_default=False).strip()
        under_raw = click.prompt("Command prefix (optional)", default="", show_default=False).strip()
        should_apply = apply or click.confirm("Apply changes now?", default=False)

        payload = _execute_import_mcp(
            ctx,
            source_name=source_name,
            server_config=server_config,
            server_name=server_name,
            config_file=Path(config_file_raw) if config_file_raw else None,
            under_values=tuple(shlex.split(under_raw)) if under_raw else (),
            apply=should_apply,
        )
        click.echo(render_payload(payload, output_format))
        return

    source_name = click.prompt("Source name")
    command_text = click.prompt("Command argv", prompt_suffix=": ")
    import_strategy = click.prompt(
        "Import strategy",
        type=click.Choice(["help", "completion", "manpage", "schema"]),
        default="help",
        show_choices=False,
    )
    operation_id = click.prompt("Operation id", default=_derive_operation_id_from_command(shlex.split(command_text)))
    title = click.prompt("Title", default="", show_default=False)
    risk = click.prompt(
        "Risk level",
        type=click.Choice(["read", "write", "destructive"]),
        default="read",
        show_choices=False,
    )
    output_mode = click.prompt(
        "Output mode",
        type=click.Choice(["text", "json"]),
        default="text",
        show_choices=False,
    )
    save_manifest_raw = click.prompt("Save manifest path (optional)", default="", show_default=False)

    extra_args: List[str] = []
    if import_strategy == "help":
        help_flag = click.prompt("Help flag", default="--help")
        extra_args.extend(["--help-flag", help_flag])
    elif import_strategy == "completion":
        completion_command = click.prompt("Completion command", default="", show_default=False)
        completion_file = click.prompt("Completion file (optional)", default="", show_default=False)
        if completion_command:
            extra_args.extend(["--completion-command", completion_command])
        if completion_file:
            extra_args.extend(["--completion-file", completion_file])
    elif import_strategy == "manpage":
        man_command = click.prompt("Manpage command", default="", show_default=False)
        man_file = click.prompt("Manpage file (optional)", default="", show_default=False)
        if man_command:
            extra_args.extend(["--man-command", man_command])
        if man_file:
            extra_args.extend(["--man-file", man_file])
    elif import_strategy == "schema":
        schema_command = click.prompt("Schema command", default="", show_default=False)
        schema_file = click.prompt("Schema file (optional)", default="", show_default=False)
        if schema_command:
            extra_args.extend(["--schema-command", schema_command])
        if schema_file:
            extra_args.extend(["--schema-file", schema_file])

    should_apply = apply or click.confirm("Apply changes now?", default=False)

    state = _get_state(ctx)
    session = prepare_edit_session(state.config_path)
    app = CTSApp(
        session.loaded,
        active_profile=state.profile,
        explicit_config_path=str(state.config_path) if state.config_path else None,
        requested_profile=state.profile,
    )
    extra: Dict[str, Any] = {
        "help_flag": "--help",
        "completion_command": None,
        "completion_file": None,
        "completion_format": "lines",
        "man_command": None,
        "man_file": None,
        "schema_command": None,
        "schema_file": None,
        "schema_format": "auto",
    }
    for index in range(0, len(extra_args), 2):
        key = extra_args[index].lstrip("-").replace("-", "_")
        value = extra_args[index + 1]
        extra[key] = Path(value) if key.endswith("_file") else value

    plan = _prepare_cli_import_plan(
        app,
        source_name=source_name,
        command_argv=shlex.split(command_text),
        operation_id=operation_id,
        import_strategy=import_strategy,
        executable=None,
        title=title or None,
        risk=risk,
        output_mode=output_mode,
        help_flag=str(extra["help_flag"]),
        completion_command=extra["completion_command"],
        completion_file=extra["completion_file"],
        completion_format=str(extra["completion_format"]),
        man_command=extra["man_command"],
        man_file=extra["man_file"],
        schema_command=extra["schema_command"],
        schema_file=extra["schema_file"],
        schema_format=str(extra["schema_format"]),
        create_mount=True,
        mount_id=None,
        command_path_value=None,
        under_values=(),
        prefix=None,
        save_manifest_path=Path(save_manifest_raw) if save_manifest_raw else None,
    )

    if not should_apply:
        click.echo(render_payload({"ok": True, "action": "import_cli_preview", **plan}, output_format))
        return

    if plan.get("manifest_write"):
        manifest_write = dict(plan["manifest_write"])
        merge_operation_into_manifest(
            Path(manifest_write["resolved_path"]),
            dict(manifest_write["operation"]),
            executable=manifest_write.get("executable"),
        )

    baseline_conflicts = conflict_signatures(app.catalog.conflicts)

    def mutator(payload: Dict[str, Any]) -> None:
        _apply_cli_import_plan(payload, plan)

    updated, compiled_app = apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=state.profile,
        baseline_conflicts=baseline_conflicts,
    )
    compiled_mount = None
    if compiled_app and plan.get("mount"):
        compiled_mount = compiled_app.catalog.find_by_id(plan["mount"]["id"])
    click.echo(
        render_payload(
            {
                "ok": True,
                "action": "import_cli_apply",
                "file": str(session.target_path),
                "created_file": session.created,
                "warnings": list(session.warnings),
                **plan,
                "source_config": _strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
                "mount_config": _find_mount_payload(updated.get("mounts", []), plan["mount"]["id"]) if plan.get("mount") else None,
                "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
            },
            output_format,
        )
    )


def _execute_import_mcp(
    ctx: click.Context,
    *,
    source_name: str,
    server_config: Optional[str],
    server_name: Optional[str],
    config_file: Optional[Path],
    under_values: tuple[str, ...],
    apply: bool,
) -> Dict[str, Any]:
    import json

    state = _get_state(ctx)
    session = prepare_edit_session(state.config_path, target_file=None)

    if config_file is None:
        config_file = session.target_path.parent / "servers.json"

    if server_config:
        try:
            server_cfg = json.loads(server_config)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in --server-config: {exc}")
    elif server_name:
        server_cfg = None
    else:
        raise ValueError("Either --server-config or --server-name must be provided")

    servers_json_path = Path(config_file)
    servers_data: Dict[str, Any] = {}

    if servers_json_path.exists():
        with open(servers_json_path) as f:
            servers_data = json.load(f)

    if server_config:
        actual_server_name = server_name or f"{source_name}-server"
        servers_data["mcpServers"] = servers_data.get("mcpServers", {})
        servers_data["mcpServers"][actual_server_name] = server_cfg
    else:
        actual_server_name = server_name

    plan = {
        "source_name": source_name,
        "server_name": actual_server_name,
        "config_file": str(servers_json_path),
        "servers_data": servers_data,
        "under": list(under_values),
    }

    if not apply:
        return {
            "ok": True,
            "action": "import_mcp_preview",
            **plan,
        }

    servers_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(servers_json_path, "w") as f:
        json.dump(servers_data, f, indent=2)

    baseline_conflicts = set()

    def mutator(payload: Dict[str, Any]) -> None:
        if "sources" not in payload:
            payload["sources"] = {}
        payload["sources"][source_name] = {
            "type": "mcp",
            "adapter": "mcp-cli",
            "config_file": str(servers_json_path),
            "server": actual_server_name,
            "discovery": {"mode": "live"},
        }

    updated, compiled_app = apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=state.profile,
        baseline_conflicts=baseline_conflicts,
    )

    if compiled_app:
        try:
            sync_result = compiled_app.sync(source_name)
            sync_items = sync_result.get("items", [])
            discovery = sync_items[0] if sync_items else {}
            operations = compiled_app.source_operations.get(source_name, {})

            mounts_to_create = []
            for op_id, op in operations.items():
                mount_id = f"{source_name}-{op_id}"
                mount_path = list(under_values) + [op_id] if under_values else [source_name, op_id]

                mounts_to_create.append(
                    {
                        "id": mount_id,
                        "source": source_name,
                        "operation": op_id,
                        "command": {"path": mount_path},
                    }
                )

            mount_session = prepare_edit_session(state.config_path, target_file=session.target_path)

            def mount_mutator(payload: Dict[str, Any]) -> None:
                if "mounts" not in payload:
                    payload["mounts"] = []
                payload["mounts"].extend(mounts_to_create)

            apply_update(
                mount_session,
                mount_mutator,
                compile_runtime=True,
                profile=state.profile,
                baseline_conflicts=baseline_conflicts,
            )

            return {
                "ok": True,
                "action": "import_mcp_apply",
                "file": str(session.target_path),
                "created_file": session.created,
                "servers_file": str(servers_json_path),
                "warnings": list(session.warnings),
                "source_config": updated.get("sources", {}).get(source_name, {}),
                "tools_count": len(operations),
                "mounts_created": len(mounts_to_create),
                "discovery": discovery,
                "discovery_report_path": sync_result.get("report_path"),
                "capability_snapshot_path": sync_result.get("capability_snapshot_path"),
                **(
                    {"tools_import_error": discovery.get("error")}
                    if discovery and not discovery.get("ok", True) and discovery.get("error")
                    else {}
                ),
            }
        except Exception as exc:
            return {
                "ok": True,
                "action": "import_mcp_apply",
                "file": str(session.target_path),
                "created_file": session.created,
                "servers_file": str(servers_json_path),
                "warnings": list(session.warnings),
                "source_config": updated.get("sources", {}).get(source_name, {}),
                "tools_import_error": str(exc),
            }

    return {
        "ok": True,
        "action": "import_mcp_apply",
        "file": str(session.target_path),
        "created_file": session.created,
        "servers_file": str(servers_json_path),
        "warnings": list(session.warnings),
        "source_config": updated.get("sources", {}).get(source_name, {}),
    }


def _execute_import_shell(
    ctx: click.Context,
    *,
    source_name: str,
    exec_command: Optional[str],
    script_file: Optional[Path],
    shell_bin: str,
    under_values: tuple[str, ...],
    title: Optional[str],
    description: Optional[str],
    risk: str,
    output_mode: str,
    apply: bool,
) -> Dict[str, Any]:
    state = _get_state(ctx)
    session = prepare_edit_session(state.config_path, target_file=None)
    app = CTSApp(
        session.loaded,
        active_profile=state.profile,
        explicit_config_path=str(state.config_path) if state.config_path else None,
        requested_profile=state.profile,
    )

    if source_name in app.config.sources:
        raise RegistryError(f"source already exists: {source_name}", code="source_exists")

    mount_id = source_name.replace(".", "-").replace("_", "-")
    if app.catalog.find_by_id(mount_id) is not None:
        raise RegistryError(f"mount already exists: {mount_id}", code="mount_exists")

    operation_id = "run"
    command_path = list(_split_command_segments(under_values)) + [source_name]
    script_path = script_file.resolve() if script_file else None
    source_label = exec_command if exec_command else str(script_path)
    argv_template = [shell_bin, "-c", exec_command] if exec_command else [shell_bin, str(script_path)]
    source_payload = {
        "type": "shell",
        "enabled": True,
        "executable": shell_bin,
        "operations": {
            operation_id: {
                "title": title or source_name,
                "description": description or f"Execute shell command: {source_label}",
                "risk": risk,
                "input_schema": {"type": "object", "properties": {}},
                "provider_config": {
                    "argv_template": argv_template,
                    "output_mode": output_mode,
                },
            }
        },
    }
    mount_payload = {
        "id": mount_id,
        "source": source_name,
        "operation": operation_id,
        "command": {"path": command_path},
        "machine": {"stable_name": f"{source_name}.run"},
        "help": {
            "summary": title or source_name,
            "description": description or f"Execute shell command: {source_label}",
            "notes": [f"Shell executable: {shell_bin}"],
        },
    }
    plan = {
        "source": {"name": source_name, "type": "shell"},
        "operation_id": operation_id,
        "mount_id": mount_id,
        "exec": exec_command,
        "script_file": str(script_path) if script_path else None,
        "shell_bin": shell_bin,
        "command_path": command_path,
        "source_config": source_payload,
        "mount_config": mount_payload,
    }

    if not apply:
        return {
            "ok": True,
            "action": "import_shell_preview",
            **plan,
        }

    baseline_conflicts = conflict_signatures(app.catalog.conflicts)

    def mutator(payload: Dict[str, Any]) -> None:
        sources = ensure_mapping(payload, "sources")
        sources[source_name] = source_payload
        mounts = ensure_list(payload, "mounts")
        mounts.append(mount_payload)

    updated, compiled_app = apply_update(
        session,
        mutator,
        compile_runtime=True,
        profile=state.profile,
        baseline_conflicts=baseline_conflicts,
    )
    compiled_mount = compiled_app.catalog.find_by_id(mount_id) if compiled_app else None

    return {
        "ok": True,
        "action": "import_shell_apply",
        "file": str(session.target_path),
        "created_file": session.created,
        "warnings": list(session.warnings),
        "source": {"name": source_name, "type": "shell"},
        "operation_id": operation_id,
        "mount_id": mount_id,
        "exec": exec_command,
        "script_file": str(script_path) if script_path else None,
        "shell_bin": shell_bin,
        "command_path": command_path,
        "source_config": _strip_internal_metadata(updated.get("sources", {}).get(source_name, {})),
        "mount_config": _find_mount_payload(updated.get("mounts", []), mount_id),
        "compiled": build_mount_details(compiled_app, compiled_mount) if compiled_app and compiled_mount else None,
    }


def _prepare_cli_import_tree_plan(
    app: CTSApp,
    *,
    source_name: str,
    command_argv: List[str],
    executable: Optional[str],
    risk: str,
    output_mode: str,
    help_flag: str,
    create_mount: bool,
    under_values: tuple[str, ...],
    prefix: Optional[str],
    save_manifest_path: Optional[Path],
) -> Dict[str, Any]:
    existing_source = app.config.sources.get(source_name)
    if existing_source and existing_source.type not in {"cli", "shell"}:
        raise RegistryError(
            f"source '{source_name}' is not a cli/shell source",
            code="source_type_not_supported",
            suggestions=["改用新的 source 名称，或继续使用原来的 provider 专用导入命令。"],
        )

    final_command = list(command_argv)
    source_executable = executable or (existing_source.executable if existing_source else None)
    if not final_command:
        if source_executable:
            final_command = [source_executable]
        else:
            raise RegistryError(
                "command argv required",
                code="command_argv_required",
                suggestions=["传入要导入的命令，例如 `cts import cli aac aac --all --apply`。"],
            )
    if source_executable is None and final_command:
        source_executable = final_command[0]

    tree = _discover_cli_help_tree(final_command, help_flag=help_flag)
    if not tree["leaves"]:
        raise RegistryError(
            f"no executable leaf commands discovered for source '{source_name}'",
            code="import_all_no_leaf_commands",
            suggestions=["确认该 CLI 的每层 help 都会列出子命令，或改为单条 `cts import cli` 导入。"],
        )

    imported_operations = []
    source_operations: Dict[str, Dict[str, Any]] = {}
    for leaf in tree["leaves"]:
        operation_id = _derive_operation_id_from_tokens(leaf["relative_tokens"])
        import_result = import_cli_help(
            operation_id=operation_id,
            command_argv=list(leaf["command_argv"]),
            help_flag=help_flag,
            risk=risk,
            output_mode=output_mode,
            title=None,
        )
        imported_operation = dict(import_result.operation)
        imported_operations.append(imported_operation)
        source_operations[operation_id] = _build_inline_source_operation(imported_operation)

    manifest_path = save_manifest_path or Path(f"{source_name}-manifest.yaml")
    manifest_write = {
        "path": str(manifest_path),
        "resolved_path": str(app.resolve_path(str(manifest_path), owner=existing_source)),
        "operations": imported_operations,
        "executable": source_executable,
    }

    mounts = []
    warnings = list(tree["warnings"])
    if create_mount:
        mounts, mount_warnings = _build_cli_import_tree_mounts(
            app,
            source_name=source_name,
            operations=imported_operations,
            under_values=under_values,
            prefix=prefix,
            root_command=final_command,
        )
        warnings.extend(mount_warnings)

    source_preview = {
        "name": source_name,
        "existing": existing_source is not None,
        "type": existing_source.type if existing_source else "cli",
        "executable": source_executable,
        "stores_operation_inline": False,
        "manifest_path": manifest_write["path"],
        "operation_count": len(imported_operations),
        "operations_preview": sorted(source_operations.keys())[:50],
        "truncated": len(imported_operations) > 50,
    }

    return {
        "source": source_preview,
        "command_argv": final_command,
        "strategy": "help_tree",
        "operations": imported_operations,
        "mounts": mounts,
        "tree": {
            "group_count": len(tree["groups"]),
            "leaf_count": len(tree["leaves"]),
            "max_depth": tree["max_depth"],
            "groups": tree["groups"][:50],
            "leaves": [item["relative_tokens"] for item in tree["leaves"][:50]],
            "truncated": len(tree["groups"]) > 50 or len(tree["leaves"]) > 50,
        },
        "manifest_write": manifest_write,
        "warnings": warnings,
    }


def _discover_cli_help_tree(command_argv: List[str], *, help_flag: str) -> Dict[str, Any]:
    queue: List[List[str]] = [list(command_argv)]
    seen: set[tuple[str, ...]] = set()
    groups: List[List[str]] = []
    leaves: List[Dict[str, Any]] = []
    warnings: List[str] = []
    max_depth = 0

    while queue:
        current = queue.pop(0)
        current_key = tuple(current)
        if current_key in seen:
            continue
        seen.add(current_key)
        relative_tokens = _relative_cli_tokens_from_base(current, command_argv)
        max_depth = max(max_depth, len(relative_tokens))
        node = inspect_cli_help(command_argv=current, help_flag=help_flag)
        if node.subcommands:
            if relative_tokens:
                groups.append(relative_tokens)
            for subcommand in node.subcommands:
                candidate = current + [subcommand]
                candidate_key = tuple(candidate)
                if candidate_key in seen:
                    continue
                queue.append(candidate)
            continue
        if relative_tokens:
            leaves.append({"command_argv": list(current), "relative_tokens": relative_tokens})

    if len(seen) > 500:
        warnings.append("discovered more than 500 help nodes; preview output was truncated")

    return {
        "groups": groups,
        "leaves": leaves,
        "warnings": warnings,
        "max_depth": max_depth,
    }


def _build_cli_import_tree_mounts(
    app: CTSApp,
    *,
    source_name: str,
    operations: List[Dict[str, Any]],
    under_values: tuple[str, ...],
    prefix: Optional[str],
    root_command: List[str],
) -> tuple[List[Dict[str, Any]], List[str]]:
    reserved_mount_ids = {mount.mount_id for mount in app.catalog.mounts}
    reserved_paths = {tuple(mount.command_path) for mount in app.catalog.mounts}
    mounts: List[Dict[str, Any]] = []
    warnings: List[str] = []
    mount_prefix = prefix or source_name.replace("_", "-").replace(".", "-")
    under_tokens = _split_command_segments(list(under_values))

    for operation in operations:
        operation_id = str(operation["id"])
        existing_mount = app.catalog.find_by_source_and_operation(source_name, operation_id)
        if existing_mount is not None:
            warnings.append(f"mount already exists for {source_name}.{operation_id}; reusing {existing_mount.mount_id}")
            continue

        relative_tokens = _relative_cli_tokens_from_base(list(operation.get("command_argv") or root_command), root_command)
        base_mount_id = f"{mount_prefix}-{operation_id.replace('.', '-').replace('_', '-')}"
        base_command_path = list(under_tokens) + relative_tokens if under_tokens else [source_name] + relative_tokens
        final_mount_id, final_command_path, warning = _make_mount_identity_unique_respecting(
            app,
            base_mount_id,
            base_command_path,
            reserved_mount_ids=reserved_mount_ids,
            reserved_paths=reserved_paths,
        )
        reserved_mount_ids.add(final_mount_id)
        reserved_paths.add(tuple(final_command_path))

        mount_entry: Dict[str, Any] = {
            "id": final_mount_id,
            "source": source_name,
            "operation": operation_id,
            "command": {"path": final_command_path},
        }

        help_entry: Dict[str, Any] = {}
        if operation.get("title"):
            help_entry["summary"] = operation["title"]
        if operation.get("description"):
            help_entry["description"] = operation["description"]
        if help_entry:
            mount_entry["help"] = help_entry

        if operation.get("risk") and operation.get("risk") != "read":
            mount_entry["policy"] = {"risk": operation["risk"]}

        mounts.append(mount_entry)
        if warning:
            warnings.append(f"{operation_id}: {warning}")

    return mounts, warnings


@manage.group()
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


@mount.command("remove")
@click.argument("mount_id")
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Remove from a specific config file.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def mount_remove(
    ctx: click.Context,
    mount_id: str,
    target_file: Optional[Path],
    output_format: str,
) -> None:
    """Remove a mount from configuration.
    
    This removes the mount entry from the config file.
    """
    state = _get_state(ctx)
    try:
        session = prepare_edit_session(state.config_path, target_file=target_file)
        app = CTSApp(
            session.loaded,
            active_profile=state.profile,
            explicit_config_path=str(state.config_path) if state.config_path else None,
            requested_profile=state.profile,
        )
        
        mount = app.catalog.find_by_id(mount_id)
        if not mount:
            raise RegistryError(f"mount not found: {mount_id}", code="mount_not_found")
        
        def mutator(payload: Dict[str, Any]) -> None:
            mounts = payload.get("mounts", [])
            if not isinstance(mounts, list):
                return
            remaining = [
                m for m in mounts
                if not (isinstance(m, dict) and m.get("id") == mount_id)
            ]
            if len(remaining) == len(mounts):
                # Mount not found in this file, try to remove from raw config
                return
            if remaining:
                payload["mounts"] = remaining
            else:
                payload.pop("mounts", None)
        
        updated, _ = apply_update(session, mutator, compile_runtime=False)
        
        payload = {
            "ok": True,
            "action": "mount_remove",
            "mount_id": mount_id,
            "file": str(session.target_path),
            "source": mount.source_name,
            "operation_id": mount.operation.id,
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "mount_remove", output_format)


@mount.command("import")
@click.argument("source_name")
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write to a specific config file.")
@click.option("--prefix", default=None, help="Mount ID prefix (default: source name).")
@click.option("--under", "under_path", multiple=True, help="Command path prefix for all imported mounts.")
@click.option("--risk", type=click.Choice(["read", "write", "destructive"]), default=None, help="Override risk level for all operations.")
@click.option("--filter", "operation_filter", multiple=True, help="Only import operations matching these IDs (supports wildcards).")
@click.option("--exclude", "exclude_filter", multiple=True, help="Exclude operations matching these IDs (supports wildcards).")
@click.option("--dry-run", is_flag=True, help="Preview what would be imported without making changes.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def mount_import(
    ctx: click.Context,
    source_name: str,
    target_file: Optional[Path],
    prefix: Optional[str],
    under_path: tuple[str, ...],
    risk: Optional[str],
    operation_filter: tuple[str, ...],
    exclude_filter: tuple[str, ...],
    dry_run: bool,
    output_format: str,
) -> None:
    """Batch import operations from a source as mounts.
    
    This command discovers all operations from a source and creates
    mount entries for each one. Useful for quickly onboarding new
    APIs or CLI tools.
    
    Examples:
        cts manage mount import my-api --dry-run
        cts manage mount import my-api --prefix api --under api
        cts manage mount import my-api --filter "get_*" --filter "list_*"
    """
    import fnmatch
    
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
        
        # Get operations from source
        operations = app.source_operations.get(source_name, {})
        if not operations:
            # Try to discover
            sync_result = app.sync(source_name)
            operations = app.source_operations.get(source_name, {})
        
        if not operations:
            raise RegistryError(
                f"no operations found for source '{source_name}'",
                code="no_operations",
                suggestions=["确保 source 配置正确并能正常 discovery。"],
            )
        
        # Filter operations
        filtered_ops = []
        for op_id, op in operations.items():
            # Check include filter
            if operation_filter:
                if not any(fnmatch.fnmatch(op_id, pattern) for pattern in operation_filter):
                    continue
            # Check exclude filter
            if exclude_filter:
                if any(fnmatch.fnmatch(op_id, pattern) for pattern in exclude_filter):
                    continue
            filtered_ops.append((op_id, op))
        
        if not filtered_ops:
            raise RegistryError(
                "no operations match the specified filters",
                code="no_matching_operations",
            )
        
        # Generate mount entries
        mount_prefix = prefix or source_name.replace("_", "-").replace(".", "-")
        under_tokens = list(under_path)
        
        new_mounts = []
        skipped_existing = []
        
        for op_id, op in filtered_ops:
            mount_id = f"{mount_prefix}-{op_id.replace('.', '-').replace('_', '-')}"
            
            # Check if mount already exists
            if app.catalog.find_by_id(mount_id):
                skipped_existing.append(mount_id)
                continue
            
            command_path = tokenize_identifier(op_id)
            
            mount_entry = {
                "id": mount_id,
                "source": source_name,
                "operation": op_id,
            }
            
            if command_path:
                mount_entry["command"] = {"path": command_path}
            
            if under_tokens:
                if "command" not in mount_entry:
                    mount_entry["command"] = {}
                mount_entry["command"]["under"] = under_tokens
            
            if risk:
                mount_entry["policy"] = {"risk": risk}
            elif op.risk and op.risk != "read":
                mount_entry["policy"] = {"risk": op.risk}
            
            # Add help from operation
            help_entry = {}
            if op.title:
                help_entry["summary"] = op.title
            if op.description:
                help_entry["description"] = op.description
            if help_entry:
                mount_entry["help"] = help_entry
            
            new_mounts.append(mount_entry)
        
        if dry_run:
            payload = {
                "ok": True,
                "action": "mount_import_dry_run",
                "source": source_name,
                "total_operations": len(operations),
                "filtered_operations": len(filtered_ops),
                "mounts_to_create": len(new_mounts),
                "skipped_existing": len(skipped_existing),
                "mounts": new_mounts[:50],  # Limit preview
                "truncated": len(new_mounts) > 50,
            }
            click.echo(render_payload(payload, output_format))
            return
        
        if not new_mounts:
            raise RegistryError(
                f"all {len(filtered_ops)} matching operations already have mounts",
                code="all_mounts_exist",
            )
        
        baseline_conflicts = conflict_signatures(app.catalog.conflicts)
        
        def mutator(payload: Dict[str, Any]) -> None:
            mounts = ensure_list(payload, "mounts")
            mounts.extend(new_mounts)
        
        updated, compiled_app = apply_update(
            session,
            mutator,
            compile_runtime=True,
            profile=state.profile,
            baseline_conflicts=baseline_conflicts,
        )
        
        payload = {
            "ok": True,
            "action": "mount_import",
            "source": source_name,
            "file": str(session.target_path),
            "created_file": session.created,
            "total_operations": len(operations),
            "filtered_operations": len(filtered_ops),
            "mounts_created": len(new_mounts),
            "skipped_existing": skipped_existing,
            "mount_ids": [m["id"] for m in new_mounts],
        }
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(ctx, exc, "mount_import", output_format)


@manage.group("alias")
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


@manage.group()
def catalog() -> None:
    """Catalog export commands."""


@catalog.command("export")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def catalog_export(app: CTSApp, output_format: str) -> None:
    click.echo(render_payload(app.export_catalog(), output_format))


@manage.command("docs")
@click.argument("output_dir", type=click.Path(path_type=Path), default=Path("docs/generated"))
@click.option("--title", default="CTS Documentation", help="Documentation title.")
@click.option("--format", "doc_format", type=click.Choice(["markdown", "html", "json"]), default="markdown")
@click.option("--no-sources", is_flag=True, help="Skip sources documentation.")
@click.option("--no-mounts", is_flag=True, help="Skip mounts documentation.")
@click.option("--no-catalog", is_flag=True, help="Skip catalog documentation.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json", hidden=True)
@pass_app
def docs_generate(
    app: CTSApp,
    output_dir: Path,
    title: str,
    doc_format: str,
    no_sources: bool,
    no_mounts: bool,
    no_catalog: bool,
    output_format: str,
) -> None:
    """Generate documentation from CTS configuration."""
    from cts.docs import DocsGenerator, DocsConfig
    
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
        "generated_files": {k: str(v) for k, v in generated.items()},
    }
    click.echo(render_payload(payload, output_format))


@manage.group()
def workflow() -> None:
    """Workflow management commands."""


@workflow.command("list")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def workflow_list(app: CTSApp, output_format: str) -> None:
    """List all configured workflows."""
    workflows = [
        workflow.model_dump(mode="json") if hasattr(workflow, "model_dump") else workflow
        for workflow in getattr(app.config, "workflows", [])
    ]
    payload = {
        "workflows": workflows,
        "count": len(workflows),
    }
    click.echo(render_payload(payload, output_format))


@workflow.command("execute")
@click.argument("workflow_id")
@click.option("--input-json", default=None, help="JSON input for the workflow.")
@click.option("--dry-run", is_flag=True, help="Preview execution without running.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.pass_context
def workflow_execute(
    ctx: click.Context,
    workflow_id: str,
    input_json: Optional[str],
    dry_run: bool,
    output_format: str,
) -> None:
    """Execute a workflow."""
    state = _get_state(ctx)
    app = state.get_app()
    
    workflows = [
        workflow.model_dump(mode="json") if hasattr(workflow, "model_dump") else workflow
        for workflow in getattr(app.config, "workflows", [])
    ]
    workflow_config = None
    for wf in workflows:
        if wf.get("id") == workflow_id:
            workflow_config = wf
            break
    
    if not workflow_config:
        _fail(ctx, RegistryError(f"workflow not found: {workflow_id}", code="workflow_not_found"), "workflow_execute", output_format)
        return
    
    from cts.workflow import WorkflowConfig, WorkflowExecutor
    
    workflow = WorkflowConfig.from_dict(workflow_config)
    executor = WorkflowExecutor(app)
    
    args = {}
    if input_json:
        try:
            args = json.loads(input_json)
        except json.JSONDecodeError as e:
            _fail(ctx, ConfigError(f"Invalid JSON input: {e}"), "workflow_execute", output_format)
            return
    
    result = executor.execute(workflow, args, dry_run=dry_run)
    
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


@manage.group()
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


@manage.command(
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


@manage.command(
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


@manage.command(
    help="Run discovery sync for one source or the whole registry.",
    short_help="Run discovery sync for one source or the whole registry.",
)
@click.argument("source_name", required=False)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def sync(app: CTSApp, source_name: Optional[str], output_format: str) -> None:
    payload = app.sync(source_name)
    click.echo(render_payload(payload, output_format))


@manage.group()
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
        _fail(
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


@manage.group()
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


@auth.command("validate")
@click.argument("name", required=False)
@click.option("--all", "validate_all", is_flag=True, help="Validate all auth profiles.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@pass_app
def auth_validate(app: CTSApp, name: Optional[str], validate_all: bool, output_format: str) -> None:
    """Validate auth profile(s) and show any issues.
    
    This command checks whether auth profiles are properly configured
    and ready for use. It identifies issues like expired sessions,
    missing credentials, or configuration problems.
    
    Examples:
        cts manage auth validate my-profile
        cts manage auth validate --all
    """
    try:
        if validate_all or not name:
            payload = app.auth_manager.validate_all()
        else:
            payload = app.auth_manager.validate(name)
        click.echo(render_payload(payload, output_format))
    except Exception as exc:
        _fail(click.get_current_context(), exc, "auth_validate", output_format)


@manage.group()
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


@manage.group()
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


@manage.group()
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


@completion.command("install")
@click.option("--shell", "shell_name", type=click.Choice(["bash", "zsh", "fish"]), required=False, help="Shell type (auto-detected if not specified).")
@click.option("--file", "target_file", type=click.Path(path_type=Path, dir_okay=False), default=None, help="Write to a specific file instead of the default shell config.")
@click.option("--append", is_flag=True, help="Append to config file instead of replacing existing cts completion.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def completion_install(
    shell_name: Optional[str],
    target_file: Optional[Path],
    append: bool,
    output_format: str,
) -> None:
    """Install shell completion for cts.
    
    This command installs shell completion scripts for bash, zsh, or fish.
    If --shell is not specified, it attempts to auto-detect the shell.
    
    For bash, completion is added to ~/.bashrc or ~/.bash_profile.
    For zsh, completion is added to ~/.zshrc.
    For fish, completion is added to ~/.config/fish/completions/cts.fish.
    
    Examples:
        cts manage completion install
        cts manage completion install --shell bash
        cts manage completion install --shell zsh --file ~/.zshrc
    """
    import os
    import re
    
    # Auto-detect shell if not specified
    if shell_name is None:
        shell_env = os.environ.get("SHELL", "")
        if "zsh" in shell_env:
            shell_name = "zsh"
        elif "fish" in shell_env:
            shell_name = "fish"
        elif "bash" in shell_env:
            shell_name = "bash"
        else:
            raise click.ClickException(
                "Could not auto-detect shell. Please specify --shell (bash, zsh, or fish)."
            )
    
    completion_class = get_completion_class(shell_name)
    if completion_class is None:
        raise click.ClickException(f"unsupported shell: {shell_name}")
    
    prog_name = main.name or "cts"
    complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"
    shell_complete = completion_class(main, {}, prog_name, complete_var)
    completion_source = shell_complete.source()
    
    # Determine target file
    home = Path.home()
    if target_file is None:
        if shell_name == "bash":
            # Try .bashrc first, then .bash_profile
            target_file = home / ".bashrc"
            if not target_file.exists():
                target_file = home / ".bash_profile"
        elif shell_name == "zsh":
            target_file = home / ".zshrc"
        elif shell_name == "fish":
            target_file = home / ".config" / "fish" / "completions" / f"{prog_name}.fish"
            target_file.parent.mkdir(parents=True, exist_ok=True)
    
    # For bash and zsh, we need to source the completion
    if shell_name in ("bash", "zsh"):
        # Create the completion script in a separate file
        completion_dir = home / ".local" / "share" / "cts" / "completions"
        completion_dir.mkdir(parents=True, exist_ok=True)
        completion_script_file = completion_dir / f"{prog_name}.{shell_name}"
        completion_script_file.write_text(completion_source)
        
        # Add source line to config
        source_line = f'[ -f {completion_script_file} ] && source {completion_script_file}'
        marker_start = f"# >>> cts completion >>>"
        marker_end = f"# <<< cts completion <<<"
        
        if target_file.exists():
            existing_content = target_file.read_text()
        else:
            existing_content = ""
        
        # Check if completion is already installed
        if marker_start in existing_content:
            if append:
                payload = {
                    "ok": True,
                    "action": "completion_install",
                    "shell": shell_name,
                    "file": str(target_file),
                    "message": "Completion already installed. Use --append to add another or manually edit.",
                    "completion_script": str(completion_script_file),
                }
                click.echo(render_payload(payload, output_format))
                return
            # Replace existing completion block
            pattern = f"{re.escape(marker_start)}.*?{re.escape(marker_end)}"
            new_content = re.sub(pattern, f"{marker_start}\n{source_line}\n{marker_end}", existing_content, flags=re.DOTALL)
        else:
            # Add new completion block
            completion_block = f"\n{marker_start}\n{source_line}\n{marker_end}\n"
            new_content = existing_content + completion_block
        
        target_file.write_text(new_content)
        
        payload = {
            "ok": True,
            "action": "completion_install",
            "shell": shell_name,
            "file": str(target_file),
            "completion_script": str(completion_script_file),
            "message": f"Completion installed. Restart your shell or run: source {target_file}",
        }
    else:
        # For fish, just write the completion file
        target_file.write_text(completion_source)
        payload = {
            "ok": True,
            "action": "completion_install",
            "shell": shell_name,
            "file": str(target_file),
            "message": f"Completion installed. Restart your shell or run: source {target_file}",
        }
    
    click.echo(render_payload(payload, output_format))


@completion.command("bootstrap")
@click.option("--shell", "shell_name", type=click.Choice(["bash", "zsh", "fish"]), required=False, help="Shell type (auto-detected if not specified).")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def completion_bootstrap(shell_name: Optional[str], output_format: str) -> None:
    """Bootstrap shell completion for the current session.
    
    This command outputs the shell commands needed to enable completion
    in the current session. Useful for testing or for adding to your
    shell profile manually.
    
    Examples:
        eval $(cts manage completion bootstrap)
        eval $(cts manage completion bootstrap --shell zsh)
    """
    import os
    
    # Auto-detect shell if not specified
    if shell_name is None:
        shell_env = os.environ.get("SHELL", "")
        if "zsh" in shell_env:
            shell_name = "zsh"
        elif "fish" in shell_env:
            shell_name = "fish"
        elif "bash" in shell_env:
            shell_name = "bash"
        else:
            raise click.ClickException(
                "Could not auto-detect shell. Please specify --shell (bash, zsh, or fish)."
            )
    
    completion_class = get_completion_class(shell_name)
    if completion_class is None:
        raise click.ClickException(f"unsupported shell: {shell_name}")
    
    prog_name = main.name or "cts"
    complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"
    shell_complete = completion_class(main, {}, prog_name, complete_var)
    completion_source = shell_complete.source()
    
    if shell_name == "bash":
        # For bash, we need to set up the completion
        click.echo(f"complete -F _{prog_name}_completion {prog_name}")
        click.echo(f"_{prog_name}_completion() {{")
        click.echo(f"  local IFS=$'\\n'")
        click.echo(f"  COMPREPLY=($(env COMP_WORDS=\"${{COMP_WORDS[*]}}\" COMP_CWORD=$COMP_CWORD {complete_var}=complete-{shell_name} {prog_name}))")
        click.echo("}")
    elif shell_name == "zsh":
        # For zsh, output the compdef
        click.echo(completion_source)
    elif shell_name == "fish":
        # For fish, just output the source
        click.echo(completion_source)


@manage.group()
def serve() -> None:
    """Northbound surface commands."""


def _resolve_http_ui_dir(ctx: click.Context, serve_ui: bool, ui_dir: Optional[Path]) -> Optional[Path]:
    if ui_dir is not None:
        return ui_dir.resolve()
    if not serve_ui:
        return None

    candidate = default_ui_dist_dir()
    if not candidate.exists():
        _fail(
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


def _serve_http_surface(
    app: CTSApp,
    host: str,
    port: int,
    serve_ui: bool,
    ui_dir: Optional[Path],
    open_browser: bool,
) -> None:
    ctx = click.get_current_context()
    resolved_ui_dir = _resolve_http_ui_dir(ctx, serve_ui=serve_ui, ui_dir=ui_dir)
    if serve_ui and resolved_ui_dir is None:
        return

    server = create_http_server(app, host=host, port=port, ui_dir=resolved_ui_dir)
    actual_host, actual_port = server.server_address
    base_url = f"http://{actual_host}:{actual_port}"
    browser_url = base_url if resolved_ui_dir is not None else f"{base_url}/api/app/summary"
    click.echo(
        json.dumps(
            {
                "ok": True,
                "surface": "http",
                "base_url": base_url,
                "browser_url": browser_url,
                "ui_enabled": resolved_ui_dir is not None,
                "ui_dir": str(resolved_ui_dir) if resolved_ui_dir else None,
            }
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
@pass_app
def serve_http_command(app: CTSApp, host: str, port: int, serve_ui: bool, ui_dir: Optional[Path], open_browser: bool) -> None:
    _serve_http_surface(
        app,
        host=host,
        port=port,
        serve_ui=serve_ui,
        ui_dir=ui_dir,
        open_browser=open_browser,
    )


@manage.command("ui")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8787, show_default=True)
@click.option("--ui-dir", type=click.Path(path_type=Path, file_okay=False), default=None, help="Explicit frontend dist directory.")
@click.option("--open", "open_browser", is_flag=True, help="Open the UI in the default browser after startup.")
@pass_app
def ui_command(app: CTSApp, host: str, port: int, ui_dir: Optional[Path], open_browser: bool) -> None:
    """Start the HTTP API together with the bundled frontend UI."""
    _serve_http_surface(
        app,
        host=host,
        port=port,
        serve_ui=True,
        ui_dir=ui_dir,
        open_browser=open_browser,
    )


@serve.command("jsonrpc")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8788, show_default=True)
@pass_app
def serve_jsonrpc_command(app: CTSApp, host: str, port: int) -> None:
    """Start JSON-RPC 2.0 server for CTS API."""
    from cts.surfaces.jsonrpc import serve_jsonrpc
    
    click.echo(
        json.dumps(
            {
                "ok": True,
                "surface": "jsonrpc",
                "base_url": f"http://{host}:{port}",
            }
        )
    )
    serve_jsonrpc(app, host=host, port=port)


@serve.command("mcp")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=int, default=8789, show_default=True)
@pass_app
def serve_mcp_command(app: CTSApp, host: str, port: int) -> None:
    """Start MCP (Model Context Protocol) server exposing CTS mounts as tools."""
    from cts.surfaces.mcp import serve_mcp
    
    click.echo(
        json.dumps(
            {
                "ok": True,
                "surface": "mcp",
                "base_url": f"http://{host}:{port}",
                "tools_count": len([m for m in app.catalog.mounts if "mcp" in getattr(m, "supported_surfaces", ["invoke"])]),
            }
        )
    )
    serve_mcp(app, host=host, port=port)


@manage.command(
    help="Run health, config, and runtime diagnostics.",
    short_help="Run health, config, and runtime diagnostics.",
)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="json")
@click.option("--compatibility", is_flag=True, help="Also run compatibility checks.")
@click.option("--auth", "check_auth", is_flag=True, help="Also validate auth profiles.")
@pass_app
def doctor(app: CTSApp, output_format: str, compatibility: bool, check_auth: bool) -> None:
    checks = [build_source_check_result(app, source_name, source) for source_name, source in app.config.sources.items()]
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
        payload["compatibility"] = doctor_compatibility(app)
    
    if check_auth:
        payload["auth"] = app.auth_manager.validate_all()
    
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
    return GroupedOptionCommand(
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


def _prepare_cli_import_plan(
    app: CTSApp,
    *,
    source_name: str,
    command_argv: List[str],
    operation_id: Optional[str],
    import_strategy: str,
    executable: Optional[str],
    title: Optional[str],
    risk: str,
    output_mode: str,
    help_flag: str,
    completion_command: Optional[str],
    completion_file: Optional[Path],
    completion_format: str,
    man_command: Optional[str],
    man_file: Optional[Path],
    schema_command: Optional[str],
    schema_file: Optional[Path],
    schema_format: str,
    create_mount: bool,
    mount_id: Optional[str],
    command_path_value: Optional[str],
    under_values: tuple[str, ...],
    prefix: Optional[str],
    save_manifest_path: Optional[Path],
) -> Dict[str, Any]:
    existing_source = app.config.sources.get(source_name)
    if existing_source and existing_source.type not in {"cli", "shell"}:
        raise RegistryError(
            f"source '{source_name}' is not a cli/shell source",
            code="source_type_not_supported",
            suggestions=["改用新的 source 名称，或继续使用原来的 provider 专用导入命令。"],
        )

    final_command = list(command_argv)
    source_executable = executable or (existing_source.executable if existing_source else None)
    if not final_command:
        if source_executable:
            final_command = [source_executable]
        else:
            raise RegistryError(
                "command argv required",
                code="command_argv_required",
                suggestions=["传入要导入的命令，例如 `cts import cli gh gh issue list --from help`。"],
            )
    if source_executable is None and final_command:
        source_executable = final_command[0]

    final_operation_id = operation_id or _derive_operation_id_from_command(final_command)
    import_result = _run_cli_import_strategy(
        operation_id=final_operation_id,
        command_argv=final_command,
        import_strategy=import_strategy,
        title=title,
        risk=risk,
        output_mode=output_mode,
        help_flag=help_flag,
        completion_command=completion_command,
        completion_file=completion_file,
        completion_format=completion_format,
        man_command=man_command,
        man_file=man_file,
        schema_command=schema_command,
        schema_file=schema_file,
        schema_format=schema_format,
    )

    imported_operation = dict(import_result.operation)
    source_operation = _build_inline_source_operation(imported_operation)
    manifest_write = None
    if save_manifest_path is not None:
        manifest_write = {
            "path": str(save_manifest_path),
            "resolved_path": str(app.resolve_path(str(save_manifest_path), owner=existing_source)),
            "operation": imported_operation,
            "executable": source_executable,
        }

    mount_plan = None
    warnings: List[str] = []
    if create_mount:
        mount_plan, mount_warning = _build_cli_import_mount_plan(
            app,
            source_name=source_name,
            operation_id=final_operation_id,
            imported_operation=imported_operation,
            mount_id=mount_id,
            command_path_value=command_path_value,
            under_values=under_values,
            prefix=prefix,
        )
        if mount_warning:
            warnings.append(mount_warning)

    source_preview = {
        "name": source_name,
        "existing": existing_source is not None,
        "type": existing_source.type if existing_source else "cli",
        "executable": source_executable,
        "stores_operation_inline": manifest_write is None,
        "manifest_path": manifest_write["path"] if manifest_write else (existing_source.discovery.manifest if existing_source else None),
        "operation_id": final_operation_id,
        "operation": source_operation,
    }

    return {
        "source": source_preview,
        "operation_id": final_operation_id,
        "command_argv": final_command,
        "strategy": import_strategy,
        "imported_operation": imported_operation,
        "mount": mount_plan,
        "manifest_write": manifest_write,
        "warnings": warnings,
    }


def _run_cli_import_strategy(
    *,
    operation_id: str,
    command_argv: List[str],
    import_strategy: str,
    title: Optional[str],
    risk: str,
    output_mode: str,
    help_flag: str,
    completion_command: Optional[str],
    completion_file: Optional[Path],
    completion_format: str,
    man_command: Optional[str],
    man_file: Optional[Path],
    schema_command: Optional[str],
    schema_file: Optional[Path],
    schema_format: str,
):
    if import_strategy == "help":
        return import_cli_help(
            operation_id=operation_id,
            command_argv=command_argv,
            help_flag=help_flag,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
    if import_strategy == "completion":
        if not completion_command and completion_file is None:
            raise RegistryError(
                "completion source required",
                code="completion_source_required",
                suggestions=["传入 --completion-command 或 --completion-file。"],
            )
        return import_cli_completion(
            operation_id=operation_id,
            command_argv=command_argv,
            completion_command=shlex.split(completion_command) if completion_command else None,
            completion_file=completion_file,
            completion_format=completion_format,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
    if import_strategy == "manpage":
        if not man_command and man_file is None:
            raise RegistryError(
                "man page source required",
                code="manpage_source_required",
                suggestions=["传入 --man-command 或 --man-file。"],
            )
        return import_cli_manpage(
            operation_id=operation_id,
            command_argv=command_argv,
            man_command=shlex.split(man_command) if man_command else None,
            man_file=man_file,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
    if import_strategy == "schema":
        if not schema_command and schema_file is None:
            raise RegistryError(
                "schema source required",
                code="schema_source_required",
                suggestions=["传入 --schema-command 或 --schema-file。"],
            )
        return import_cli_schema(
            operation_id=operation_id,
            command_argv=command_argv,
            schema_command=shlex.split(schema_command) if schema_command else None,
            schema_file=schema_file,
            schema_format=schema_format,
            risk=risk,
            output_mode=output_mode,
            title=title,
        )
    raise RegistryError(f"unsupported import strategy: {import_strategy}", code="import_strategy_unsupported")


def _build_inline_source_operation(imported_operation: Dict[str, Any]) -> Dict[str, Any]:
    provider_config: Dict[str, Any] = {}
    for key in (
        "command_argv",
        "option_bindings",
        "option_order",
        "output",
        "output_mode",
        "imported_from",
        "schema_payload",
        "help_command",
        "completion_command",
        "man_command",
    ):
        if key in imported_operation:
            provider_config[key] = imported_operation[key]

    return {
        "title": imported_operation.get("title"),
        "description": imported_operation.get("description"),
        "kind": imported_operation.get("kind", "action"),
        "risk": imported_operation.get("risk", "read"),
        "input_schema": imported_operation.get("input_schema") or {},
        "output_schema": imported_operation.get("output_schema"),
        "examples": imported_operation.get("examples") or [],
        "supported_surfaces": imported_operation.get("supported_surfaces") or ["cli", "invoke"],
        "provider_config": provider_config,
    }


def _build_cli_import_mount_plan(
    app: CTSApp,
    *,
    source_name: str,
    operation_id: str,
    imported_operation: Dict[str, Any],
    mount_id: Optional[str],
    command_path_value: Optional[str],
    under_values: tuple[str, ...],
    prefix: Optional[str],
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    existing_mount = app.catalog.find_by_source_and_operation(source_name, operation_id)
    if existing_mount is not None:
        return (
            {
                "id": existing_mount.mount_id,
                "existing": True,
                "command_path": list(existing_mount.command_path),
                "source": source_name,
                "operation": operation_id,
            },
            f"mount already exists for {source_name}.{operation_id}; reusing {existing_mount.mount_id}",
        )

    mount_prefix = prefix or source_name.replace("_", "-").replace(".", "-")
    base_mount_id = mount_id or f"{mount_prefix}-{operation_id.replace('.', '-').replace('_', '-')}"

    if command_path_value:
        base_command_path = _split_command_segments([command_path_value])
    else:
        under_tokens = _split_command_segments(list(under_values))
        operation_tokens = tokenize_identifier(operation_id)
        if under_tokens:
            base_command_path = under_tokens + operation_tokens
        else:
            base_command_path = tokenize_identifier(source_name) + operation_tokens

    final_mount_id, final_command_path, warning = _make_mount_identity_unique(app, base_mount_id, base_command_path)
    mount_entry: Dict[str, Any] = {
        "id": final_mount_id,
        "source": source_name,
        "operation": operation_id,
        "command": {"path": final_command_path},
    }

    help_entry: Dict[str, Any] = {}
    if imported_operation.get("title"):
        help_entry["summary"] = imported_operation["title"]
    if imported_operation.get("description"):
        help_entry["description"] = imported_operation["description"]
    if help_entry:
        mount_entry["help"] = help_entry

    risk = imported_operation.get("risk")
    if risk and risk != "read":
        mount_entry["policy"] = {"risk": risk}

    return mount_entry, warning


def _make_mount_identity_unique(app: CTSApp, mount_id: str, command_path: List[str]) -> tuple[str, List[str], Optional[str]]:
    return _make_mount_identity_unique_respecting(
        app,
        mount_id,
        command_path,
        reserved_mount_ids=set(),
        reserved_paths=set(),
    )


def _make_mount_identity_unique_respecting(
    app: CTSApp,
    mount_id: str,
    command_path: List[str],
    *,
    reserved_mount_ids: set[str],
    reserved_paths: set[tuple[str, ...]],
) -> tuple[str, List[str], Optional[str]]:
    candidate_mount_id = mount_id
    candidate_path = list(command_path)
    suffix = 2
    warning = None

    while (
        app.catalog.find_by_id(candidate_mount_id) is not None
        or app.catalog.find_by_path(candidate_path) is not None
        or candidate_mount_id in reserved_mount_ids
        or tuple(candidate_path) in reserved_paths
    ):
        warning = "mount id or command path already exists; generated a numeric suffix automatically"
        candidate_mount_id = f"{mount_id}-{suffix}"
        candidate_path = list(command_path)
        if candidate_path:
            candidate_path[-1] = f"{candidate_path[-1]}-{suffix}"
        suffix += 1
    return candidate_mount_id, candidate_path, warning


def _derive_operation_id_from_command(command_argv: List[str]) -> str:
    relative_tokens = _relative_cli_tokens(command_argv)
    if not relative_tokens:
        return "command"
    return _derive_operation_id_from_tokens(relative_tokens)


def _derive_operation_id_from_tokens(tokens: List[str]) -> str:
    if not tokens:
        return "command"
    return "_".join(token.replace("-", "_").replace(".", "_") for token in tokens)


def _relative_cli_tokens(command_argv: List[str]) -> List[str]:
    candidates = [token for token in command_argv if token and not token.startswith("-")]
    if len(candidates) <= 1:
        return []
    return list(candidates[1:])


def _relative_cli_tokens_from_base(command_argv: List[str], base_command_argv: List[str]) -> List[str]:
    if len(command_argv) >= len(base_command_argv) and command_argv[: len(base_command_argv)] == base_command_argv:
        return [token for token in command_argv[len(base_command_argv) :] if token and not token.startswith("-")]
    return _relative_cli_tokens(command_argv)


def _apply_cli_import_plan(payload: Dict[str, Any], plan: Dict[str, Any]) -> None:
    source_plan = dict(plan["source"])
    source_name = str(source_plan["name"])
    operation_id = str(source_plan["operation_id"])
    sources = ensure_mapping(payload, "sources")
    source_payload = sources.get(source_name)
    if source_payload is None:
        source_payload = {"type": source_plan["type"], "enabled": True}
        sources[source_name] = source_payload
    if not isinstance(source_payload, dict):
        raise ConfigEditError(f"source payload must be a mapping: {source_name}")

    source_payload.setdefault("type", source_plan["type"])
    if source_plan.get("executable"):
        source_payload["executable"] = source_plan["executable"]

    manifest_write = plan.get("manifest_write")
    if manifest_write:
        discovery = ensure_mapping(source_payload, "discovery")
        discovery["manifest"] = manifest_write["path"]
        operations = source_payload.get("operations")
        if isinstance(operations, dict) and operation_id in operations:
            del operations[operation_id]
            if not operations:
                source_payload.pop("operations", None)
    else:
        operations = ensure_mapping(source_payload, "operations")
        operations[operation_id] = dict(source_plan["operation"])

    mount_plan = plan.get("mount")
    if mount_plan and not mount_plan.get("existing"):
        mounts = ensure_list(payload, "mounts")
        mounts.append(dict(mount_plan))


def _apply_cli_import_tree_plan(payload: Dict[str, Any], plan: Dict[str, Any]) -> None:
    source_plan = dict(plan["source"])
    source_name = str(source_plan["name"])
    sources = ensure_mapping(payload, "sources")
    source_payload = sources.get(source_name)
    if source_payload is None:
        source_payload = {"type": source_plan["type"], "enabled": True}
        sources[source_name] = source_payload
    if not isinstance(source_payload, dict):
        raise ConfigEditError(f"source payload must be a mapping: {source_name}")

    source_payload.setdefault("type", source_plan["type"])
    if source_plan.get("executable"):
        source_payload["executable"] = source_plan["executable"]

    manifest_write = dict(plan["manifest_write"])
    discovery = ensure_mapping(source_payload, "discovery")
    discovery["manifest"] = manifest_write["path"]

    mounts = ensure_list(payload, "mounts")
    existing_mount_ids = {
        item.get("id")
        for item in mounts
        if isinstance(item, dict) and item.get("id")
    }
    for mount in plan.get("mounts") or []:
        if mount.get("id") in existing_mount_ids:
            continue
        mounts.append(dict(mount))
        existing_mount_ids.add(mount.get("id"))


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
