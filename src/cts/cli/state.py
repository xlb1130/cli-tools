from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import click

from cts.cli.command_registry import resolve_auto_mode, resolve_command_scopes, should_load_drift_governance


StaticCatalogBuilder = Callable[[Any], Any]
_PROCESS_STATIC_CATALOG_CACHE: Dict[str, Any] = {}


@dataclass
class CLIState:
    config_path: Optional[Path]
    profile: Optional[str]
    global_output: str = "text"
    help_requested: bool = False
    requested_command_path: tuple[str, ...] = ()
    static_catalog_builder: Optional[StaticCatalogBuilder] = field(default=None, repr=False)
    _help_app: Any = field(default=None, init=False, repr=False)
    _minimal_app: Any = field(default=None, init=False, repr=False)
    _full_app: Any = field(default=None, init=False, repr=False)
    _invoke_app: Any = field(default=None, init=False, repr=False)
    _static_help_catalog: Any = field(default=None, init=False, repr=False)
    _static_help_catalog_loaded: bool = field(default=False, init=False, repr=False)
    _static_catalog: Any = field(default=None, init=False, repr=False)
    _static_catalog_loaded: bool = field(default=False, init=False, repr=False)
    _direct_help_mount: Any = field(default=None, init=False, repr=False)
    _direct_help_mount_loaded: bool = field(default=False, init=False, repr=False)

    def get_command_scopes(self):
        return resolve_command_scopes(self.requested_command_path)

    def get_app(self, mode: str = "auto", progress_callback: Optional[Callable[[str], None]] = None) -> Any:
        from cts.cli.lazy import build_app

        resolved_mode = (
            resolve_auto_mode(self.requested_command_path, help_requested=self.help_requested)
            if mode == "auto"
            else mode
        )
        if resolved_mode == "minimal":
            if self._full_app is not None:
                return self._full_app
            if self._minimal_app is None:
                self._minimal_app = build_app(
                    str(self.config_path) if self.config_path else None,
                    profile=self.profile,
                    compile_mode="minimal",
                    load_drift_governance=False,
                    progress_callback=progress_callback,
                )
                setattr(self._minimal_app, "global_output", self.global_output)
            return self._minimal_app

        if resolved_mode == "help":
            if self._full_app is not None:
                return self._full_app
            if self._help_app is None:
                self._help_app = build_app(
                    str(self.config_path) if self.config_path else None,
                    profile=self.profile,
                    compile_mode="help",
                    load_drift_governance=False,
                    progress_callback=progress_callback,
                )
                setattr(self._help_app, "global_output", self.global_output)
            return self._help_app

        if resolved_mode == "invoke":
            if self._full_app is not None:
                return self._full_app
            if self._invoke_app is None:
                target_mount = self.get_static_requested_mount()
                target_sources = [target_mount.source_name] if target_mount is not None else None
                self._invoke_app = build_app(
                    str(self.config_path) if self.config_path else None,
                    profile=self.profile,
                    compile_mode="invoke",
                    target_source_names=target_sources,
                    load_drift_governance=True,
                    progress_callback=progress_callback,
                )
                setattr(self._invoke_app, "global_output", self.global_output)
            return self._invoke_app

        if self._full_app is None:
            self._full_app = build_app(
                str(self.config_path) if self.config_path else None,
                profile=self.profile,
                compile_mode="full",
                load_drift_governance=should_load_drift_governance(
                    self.requested_command_path,
                    help_requested=self.help_requested,
                ),
                progress_callback=progress_callback,
            )
            setattr(self._full_app, "global_output", self.global_output)
        return self._full_app

    def get_direct_help_mount(self):
        if self._direct_help_mount_loaded:
            return self._direct_help_mount
        self._direct_help_mount_loaded = True
        if not self.help_requested or not self.requested_command_path:
            self._direct_help_mount = None
            return None
        try:
            catalog = self.get_static_help_catalog()
            self._direct_help_mount = catalog.find_by_path(self.requested_command_path) if catalog else None
        except Exception:
            self._direct_help_mount = None
        return self._direct_help_mount

    def get_static_requested_mount(self):
        if not self.requested_command_path:
            return None
        catalog = self.get_static_catalog()
        if catalog is None:
            return None
        return catalog.find_by_path(self.requested_command_path)

    def get_static_catalog(self):
        if self._static_catalog_loaded:
            return self._static_catalog
        self._static_catalog_loaded = True
        if self.static_catalog_builder is None:
            self._static_catalog = None
            return None
        try:
            from cts.cli.command_index import load_command_index, write_command_index
            from cts.config.loader import load_raw_config

            explicit_config_path = str(self.config_path) if self.config_path else None
            cache_key = explicit_config_path or f"cwd:{Path.cwd().resolve()}"
            process_cached_catalog = _PROCESS_STATIC_CATALOG_CACHE.get(cache_key)
            if process_cached_catalog is not None:
                self._static_catalog = process_cached_catalog
                return self._static_catalog

            cached_catalog = load_command_index(explicit_config_path)
            if cached_catalog is not None:
                self._static_catalog = cached_catalog
                _PROCESS_STATIC_CATALOG_CACHE[cache_key] = cached_catalog
                return self._static_catalog

            loaded = load_raw_config(explicit_config_path)
            self._static_catalog = self.static_catalog_builder(loaded)
            write_command_index(
                explicit_config_path,
                loaded,
                self._static_catalog,
                help_mode=self.help_requested,
            )
            _PROCESS_STATIC_CATALOG_CACHE[cache_key] = self._static_catalog
        except Exception:
            self._static_catalog = None
        return self._static_catalog

    def get_static_help_catalog(self):
        if self._static_help_catalog_loaded:
            return self._static_help_catalog
        self._static_help_catalog_loaded = True
        if not self.help_requested:
            self._static_help_catalog = None
            return None
        try:
            self._static_help_catalog = self.get_static_catalog()
        except Exception:
            self._static_help_catalog = None
        return self._static_help_catalog


def parse_root_argv(argv: list[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {
        "help_requested": any(token in {"-h", "--help"} for token in argv),
        "command_path": [],
    }
    index = 0
    command_tokens: list[str] = []
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
        if token in {"--format", "--output"} and index + 1 < len(argv):
            parsed["global_output"] = argv[index + 1]
            index += 2
            continue
        if token in {"-h", "--help"}:
            break
        if token.startswith("-"):
            index += 1
            continue
        command_tokens.append(token)
        index += 1
    parsed["command_path"] = command_tokens
    return parsed


def get_state(ctx: click.Context, static_catalog_builder: StaticCatalogBuilder) -> CLIState:
    root = ctx.find_root()
    if isinstance(root.obj, CLIState):
        root.obj.static_catalog_builder = static_catalog_builder
        return root.obj

    raw = parse_root_argv(sys.argv[1:])
    config_path = root.params.get("config_path")
    profile = root.params.get("profile")
    global_output = root.params.get("global_output", "text")
    if config_path is None and not root.params:
        config_path = raw.get("config_path")
        profile = raw.get("profile")
        global_output = raw.get("global_output", global_output)
    remaining_tokens = list(getattr(root, "protected_args", []) or []) + list(getattr(root, "args", []) or [])
    help_requested = any(token in {"-h", "--help"} for token in remaining_tokens)
    root.obj = CLIState(
        config_path=config_path,
        profile=profile,
        global_output=global_output,
        help_requested=help_requested or bool(raw.get("help_requested")),
        requested_command_path=tuple(raw.get("command_path", [])),
        static_catalog_builder=static_catalog_builder,
    )
    return root.obj


def get_app(
    ctx: click.Context,
    static_catalog_builder: StaticCatalogBuilder,
    mode: str = "auto",
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Any:
    return get_state(ctx, static_catalog_builder).get_app(mode=mode, progress_callback=progress_callback)
