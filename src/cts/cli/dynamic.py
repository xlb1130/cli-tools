from __future__ import annotations

import inspect as pyinspect
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional

import click

from cts.cli.lazy import build_click_params, build_mount_help, compile_command_help
from cts.execution.logging import emit_app_event


class GroupedOptionCommand(click.Command):
    def _structured_help(self):
        return getattr(self, "help_sections", [])

    def _structured_epilog(self):
        return getattr(self, "help_epilog_sections", [])

    def format_help_text(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        text = ""
        if self.help is not None:
            text = pyinspect.cleandoc(self.help).partition("\f")[0]
        if self.deprecated:
            text = f"(Deprecated) {text}".strip()

        sections = self._structured_help()
        if not text and not sections:
            return

        formatter.write_paragraph()
        if text:
            with formatter.indentation():
                formatter.write_text(text)

        for section in sections:
            rows = section.get("rows") or []
            body = section.get("body")
            if not rows and not body:
                continue
            formatter.write_paragraph()
            with formatter.section(section["title"]):
                if rows:
                    formatter.write_dl(rows)
                if body:
                    formatter.write_text(body)

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

    def format_epilog(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        text = pyinspect.cleandoc(self.epilog) if self.epilog else ""
        sections = self._structured_epilog()
        if not text and not sections:
            return

        formatter.write_paragraph()
        if text:
            with formatter.indentation():
                formatter.write_text(text)

        for section in sections:
            rows = section.get("rows") or []
            body = section.get("body")
            if not rows and not body:
                continue
            formatter.write_paragraph()
            with formatter.section(section["title"]):
                if rows:
                    formatter.write_dl(rows)
                if body:
                    formatter.write_text(body)


class DirectPathGroup(click.Group):
    def __init__(self, *args, path_prefix=None, target_mount=None, callback_factory: Optional[Callable[[Any], Callable]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.path_prefix = tuple(path_prefix or ())
        self.target_mount = target_mount
        self.callback_factory = callback_factory

    def list_commands(self, ctx):
        target_path = tuple(self.target_mount.command_path)
        if len(self.path_prefix) >= len(target_path):
            return []
        return [target_path[len(self.path_prefix)]]

    def get_command(self, ctx, cmd_name):
        next_prefix = self.path_prefix + (cmd_name,)
        target_path = tuple(self.target_mount.command_path)
        if next_prefix != target_path[: len(next_prefix)]:
            return None
        if len(next_prefix) < len(target_path):
            return DirectPathGroup(
                name=cmd_name,
                path_prefix=next_prefix,
                target_mount=self.target_mount,
                callback_factory=self.callback_factory,
                help="Dynamic command group for " + " ".join(next_prefix),
                no_args_is_help=True,
            )
        return build_static_help_command(self.target_mount, callback=self.callback_factory(self.target_mount))


def build_dynamic_command(app: Any, mount: Any, callback: Callable) -> click.Command:
    return LazyDynamicCommand(
        app,
        mount,
        name=mount.command_path[-1],
        callback=callback,
        short_help=_mount_short_help(mount),
    )


def build_static_help_command(mount: Any, callback: Callable) -> click.Command:
    help_content = compile_command_help(mount)
    command = GroupedOptionCommand(
        name=mount.command_path[-1],
        params=build_click_params(mount),
        callback=callback,
        short_help=_mount_short_help(mount, help_content=help_content),
        help=help_content["description"],
        epilog=None,
    )
    command.help_sections = [
        {"title": "Details", "rows": help_content["detail_rows"]},
        {"title": "Notes", "rows": help_content["note_rows"]},
    ]
    command.help_epilog_sections = [
        {"title": "Examples", "rows": help_content["example_rows"]},
        {"title": "References", "rows": help_content["reference_rows"]},
    ]
    return command


def _mount_short_help(mount: Any, help_content: Optional[Dict[str, str]] = None) -> str:
    summary = (help_content or {}).get("summary") or (help_content or {}).get("short_help")
    if summary:
        return str(summary).strip().splitlines()[0]
    description = (
        mount.description
        or mount.operation.description
        or (help_content or {}).get("description")
        or (help_content or {}).get("help")
    )
    if description:
        return str(description).strip().splitlines()[0]
    return mount.summary or mount.operation.title


class LazyDynamicCommand(GroupedOptionCommand):
    def __init__(self, app: Any, mount: Any, *args, **kwargs):
        super().__init__(*args, params=[], **kwargs)
        self._app = app
        self._mount = mount
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        emit_app_event(
            self._app,
            event="help_compile_start",
            source=self._mount.source_name,
            mount_id=self._mount.mount_id,
            operation_id=self._mount.operation.id,
        )
        help_payload = build_mount_help(self._app, self._mount)
        emit_app_event(
            self._app,
            event="help_compile_complete",
            source=self._mount.source_name,
            mount_id=self._mount.mount_id,
            operation_id=self._mount.operation.id,
            data={"schema_provenance": help_payload.get("schema_provenance")},
        )
        self.params = build_click_params(self._mount)
        self.help = help_payload.get("description") or ""
        self.epilog = None
        self.short_help = help_payload["summary"]
        self.help_sections = [
            {"title": "Details", "rows": help_payload.get("detail_rows") or []},
            {"title": "Notes", "rows": help_payload.get("note_rows") or []},
        ]
        self.help_epilog_sections = [
            {"title": "Examples", "rows": help_payload.get("example_rows") or []},
            {"title": "References", "rows": help_payload.get("reference_rows") or []},
        ]
        self._loaded = True

    def get_params(self, ctx: click.Context) -> List[click.Parameter]:
        self._ensure_loaded()
        return super().get_params(ctx)

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        self._ensure_loaded()
        super().format_help(ctx, formatter)
