from __future__ import annotations

import json
import shlex
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import click

from cts.imports.framework import (
    build_provider_import_plan,
    describe_provider_import,
    execute_import_plan,
    provider_supports_import,
)
from cts.imports.models import ImportArgumentDescriptor, ImportRequest, ImportWizardField


def register_import_commands(
    import_group,
    *,
    get_state: Callable,
    progress_steps: Callable,
    fail: Callable,
    prepare_edit_session: Callable,
    app_factory: Callable,
    apply_update: Callable,
    render_payload: Callable,
    **_: Any,
) -> None:
    @import_group.command("wizard")
    @click.argument("provider_type", required=False)
    @click.option("--apply", is_flag=True, help="Apply imported source/mount changes.")
    @click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
    @click.pass_context
    def import_wizard(ctx: click.Context, provider_type: Optional[str], apply: bool, output_format: str) -> None:
        try:
            app, state, session = _build_import_app(ctx, get_state=get_state, prepare_edit_session=prepare_edit_session, app_factory=app_factory)
            if not provider_type:
                provider_type = click.prompt(
                    "Import type",
                    type=click.Choice(_wizard_provider_types(app), case_sensitive=False),
                    show_choices=False,
                )
            provider = _resolve_provider_for_import(app, str(provider_type))
            descriptor = describe_provider_import(provider, app)
            values = _run_provider_wizard(descriptor)
            source_name = str(values.get("source_name") or "")
            request = ImportRequest(
                provider_type=str(provider_type),
                source_name=source_name or None,
                values=values,
                apply=apply,
                profile=state.profile,
                requested_by="wizard",
            )
            payload = _execute_import_request(
                request,
                provider=provider,
                app=app,
                state=state,
                session=session,
                apply_update=apply_update,
                prepare_edit_session=prepare_edit_session,
            )
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, "import_wizard", output_format)

    _attach_dynamic_provider_commands(
        import_group,
        get_state=get_state,
        prepare_edit_session=prepare_edit_session,
        app_factory=app_factory,
        apply_update=apply_update,
        render_payload=render_payload,
        fail=fail,
    )


def _attach_dynamic_provider_commands(
    import_group: click.Group,
    *,
    get_state: Callable,
    prepare_edit_session: Callable,
    app_factory: Callable,
    apply_update: Callable,
    render_payload: Callable,
    fail: Callable,
) -> None:
    original_list = import_group.list_commands
    original_get = import_group.get_command

    def list_commands(self: click.Group, ctx: click.Context) -> List[str]:
        commands = list(original_list(ctx))
        try:
            app, _state, _session = _build_import_app(ctx, get_state=get_state, prepare_edit_session=prepare_edit_session, app_factory=app_factory)
            commands.extend(_import_provider_types(app))
        except Exception:
            pass
        return sorted(set(commands))

    def get_command(self: click.Group, ctx: click.Context, cmd_name: str):
        builtin = original_get(ctx, cmd_name)
        if builtin is not None:
            return builtin
        try:
            app, _state, _session = _build_import_app(ctx, get_state=get_state, prepare_edit_session=prepare_edit_session, app_factory=app_factory)
        except Exception:
            return None
        try:
            provider = _resolve_provider_for_import(app, cmd_name)
        except Exception:
            return None
        return _build_provider_import_command(
            provider_type=cmd_name,
            provider=provider,
            app=app,
            get_state=get_state,
            prepare_edit_session=prepare_edit_session,
            app_factory=app_factory,
            apply_update=apply_update,
            render_payload=render_payload,
            fail=fail,
        )

    import_group.list_commands = types.MethodType(list_commands, import_group)
    import_group.get_command = types.MethodType(get_command, import_group)


def _build_provider_import_command(
    *,
    provider_type: str,
    provider: Any,
    app: Any,
    get_state: Callable,
    prepare_edit_session: Callable,
    app_factory: Callable,
    apply_update: Callable,
    render_payload: Callable,
    fail: Callable,
) -> click.Command:
    descriptor = describe_provider_import(provider, app)
    params: List[click.Parameter] = []
    for argument in descriptor.arguments:
        param = _build_click_parameter(argument)
        if param is not None:
            params.append(param)
    params.append(click.Option(["--apply"], is_flag=True, help="Apply changes now."))
    params.append(click.Option(["--wizard"], is_flag=True, help="Run provider-defined wizard."))
    params.append(click.Option(["--format", "output_format"], type=click.Choice(["text", "json"]), default="text"))

    def callback(**kwargs: Any) -> None:
        ctx = click.get_current_context()
        output_format = str(kwargs.pop("output_format"))
        try:
            app_inner, state, session = _build_import_app(ctx, get_state=get_state, prepare_edit_session=prepare_edit_session, app_factory=app_factory)
            provider_inner = _resolve_provider_for_import(app_inner, provider_type)
            values = dict(kwargs)
            use_wizard = bool(values.pop("wizard", False))
            apply = bool(values.pop("apply", False))
            if use_wizard:
                wizard_values = _run_provider_wizard(describe_provider_import(provider_inner, app_inner))
                values.update({key: value for key, value in wizard_values.items() if value not in (None, "", ())})
            source_name = str(values.get("source_name") or "")
            request = ImportRequest(
                provider_type=provider_type,
                source_name=source_name or None,
                values=values,
                apply=apply,
                profile=state.profile,
                requested_by="wizard" if use_wizard else "cli",
            )
            payload = _execute_import_request(
                request,
                provider=provider_inner,
                app=app_inner,
                state=state,
                session=session,
                apply_update=apply_update,
                prepare_edit_session=prepare_edit_session,
            )
            click.echo(render_payload(payload, output_format))
        except Exception as exc:
            fail(ctx, exc, f"import_{provider_type}", output_format)

    return click.Command(
        name=provider_type,
        params=params,
        callback=callback,
        help=descriptor.description or descriptor.summary,
        short_help=descriptor.summary,
    )


def _build_click_parameter(argument: ImportArgumentDescriptor) -> Optional[click.Parameter]:
    param_type = _click_type_for(argument)
    if argument.kind == "argument":
        nargs = -1 if argument.value_type == "string_list" else 1
        return click.Argument([argument.name], nargs=nargs, required=argument.required, type=param_type)
    if argument.kind == "flag":
        return click.Option(argument.flags or [f"--{_dash(argument.name)}"], is_flag=True, default=bool(argument.default), help=argument.help)
    if argument.kind == "option":
        option_names = argument.flags or [f"--{_dash(argument.name)}"]
        if argument.value_type == "bool":
            return click.Option(option_names, is_flag=True, default=bool(argument.default), help=argument.help)
        multiple = bool(argument.repeated)
        return click.Option(option_names, default=argument.default, required=argument.required, multiple=multiple, type=param_type, help=argument.help)
    return None


def _click_type_for(argument: ImportArgumentDescriptor) -> Any:
    if argument.value_type == "choice":
        return click.Choice(list(argument.choices))
    if argument.value_type == "path":
        return click.Path(path_type=Path)
    if argument.value_type == "int":
        return int
    if argument.value_type == "float":
        return float
    if argument.value_type == "json":
        return str
    return str


def _build_import_app(ctx: click.Context, *, get_state: Callable, prepare_edit_session: Callable, app_factory: Callable):
    state = get_state(ctx)
    session = prepare_edit_session(state.config_path, target_file=None)
    app = app_factory(session.loaded, state.profile, session.target_path)
    return app, state, session


def _import_provider_types(app: Any) -> List[str]:
    result = []
    for provider_type in sorted(app.provider_registry.supported_types()):
        provider = app.provider_registry.get(provider_type)
        if provider_supports_import(provider):
            result.append(provider_type)
    return result


def _wizard_provider_types(app: Any) -> List[str]:
    result = []
    for provider_type in _import_provider_types(app):
        provider = app.provider_registry.get(provider_type)
        descriptor = describe_provider_import(provider, app)
        if descriptor.supports_wizard:
            result.append(provider_type)
    return result


def _resolve_provider_for_import(app: Any, provider_type: str) -> Any:
    provider = app.provider_registry.get(provider_type)
    if not provider_supports_import(provider):
        raise click.UsageError(f"provider '{provider_type}' does not support import")
    return provider


def _run_provider_wizard(descriptor: Any) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    wizard = descriptor.wizard
    if wizard is None:
        for argument in descriptor.arguments:
            field = ImportWizardField(
                name=argument.name,
                label=argument.name.replace("_", " ").title(),
                value_type=argument.value_type,
                required=argument.required,
                default=argument.default,
                help=argument.help,
                choices=list(argument.choices),
                multiple=argument.repeated,
                secret=argument.secret,
            )
            values[field.name] = _prompt_for_field(field)
        return values

    for step in wizard.steps:
        for field in step.fields:
            if not _field_is_visible(field, values):
                continue
            values[field.name] = _prompt_for_field(field)
    return values


def _field_is_visible(field: ImportWizardField, values: Dict[str, Any]) -> bool:
    if not field.visible_when:
        return True
    for key, expected in field.visible_when.items():
        if values.get(key) != expected:
            return False
    return True


def _prompt_for_field(field: ImportWizardField) -> Any:
    prompt_text = field.label
    if field.value_type == "choice":
        return click.prompt(prompt_text, type=click.Choice(list(field.choices), case_sensitive=False), default=field.default or None, show_choices=False)
    if field.value_type == "bool":
        return click.confirm(prompt_text, default=bool(field.default))
    if field.value_type == "json":
        raw = click.prompt(prompt_text, default=field.default or "", show_default=bool(field.default), hide_input=field.secret)
        raw = str(raw).strip()
        return json.loads(raw) if raw else None
    raw = click.prompt(prompt_text, default=field.default or "", show_default=bool(field.default), hide_input=field.secret)
    raw = str(raw).strip()
    if not raw:
        return None
    if field.multiple or field.value_type == "string_list":
        return shlex.split(raw)
    if field.value_type == "int":
        return int(raw)
    if field.value_type == "float":
        return float(raw)
    return raw


def _execute_import_request(
    request: ImportRequest,
    *,
    provider: Any,
    app: Any,
    state: Any,
    session: Any,
    apply_update: Callable,
    prepare_edit_session: Callable,
) -> Dict[str, Any]:
    request.values.setdefault("__target_dir__", str(session.target_path.parent))
    plan = build_provider_import_plan(provider, request, app)
    if not request.apply:
        return dict(plan.preview)
    return execute_import_plan(
        plan,
        session=session,
        app=app,
        state=state,
        apply_update=apply_update,
        prepare_edit_session=prepare_edit_session,
    )


def _dash(value: str) -> str:
    return value.replace("_", "-")
