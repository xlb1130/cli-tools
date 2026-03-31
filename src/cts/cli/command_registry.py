from __future__ import annotations

from typing import Literal


LoadMode = Literal["help", "invoke", "full"]
CommandScope = Literal[
    "config",
    "completion",
    "catalog",
    "mount_execution",
    "discovery",
    "auth",
    "runs",
    "events",
    "docs",
    "workflow",
    "surfaces",
    "imports",
]


_FULL_MODE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("manage",),
    ("import",),
)

_INVOKE_MODE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("manage", "invoke"),
    ("manage", "explain"),
    ("invoke",),
    ("explain",),
)

_COMMAND_SCOPES: tuple[tuple[tuple[str, ...], frozenset[CommandScope]], ...] = (
    (("manage", "invoke"), frozenset({"mount_execution"})),
    (("manage", "explain"), frozenset({"mount_execution"})),
    (("invoke",), frozenset({"mount_execution"})),
    (("explain",), frozenset({"mount_execution"})),
    (("manage", "source"), frozenset({"config", "catalog", "discovery"})),
    (("source",), frozenset({"config", "catalog", "discovery"})),
    (("manage", "mount"), frozenset({"config", "catalog"})),
    (("mount",), frozenset({"config", "catalog"})),
    (("manage", "alias"), frozenset({"config", "catalog"})),
    (("alias",), frozenset({"config", "catalog"})),
    (("manage", "inspect"), frozenset({"catalog", "discovery"})),
    (("inspect",), frozenset({"catalog", "discovery"})),
    (("manage", "auth"), frozenset({"auth"})),
    (("auth",), frozenset({"auth"})),
    (("manage", "secret"), frozenset({"auth"})),
    (("secret",), frozenset({"auth"})),
    (("manage", "runs"), frozenset({"runs"})),
    (("runs",), frozenset({"runs"})),
    (("manage", "logs"), frozenset({"events"})),
    (("logs",), frozenset({"events"})),
    (("manage", "catalog"), frozenset({"catalog"})),
    (("catalog",), frozenset({"catalog"})),
    (("manage", "docs"), frozenset({"catalog", "docs"})),
    (("docs",), frozenset({"catalog", "docs"})),
    (("manage", "workflow"), frozenset({"workflow"})),
    (("workflow",), frozenset({"workflow"})),
    (("manage", "sync"), frozenset({"discovery", "catalog"})),
    (("sync",), frozenset({"discovery", "catalog"})),
    (("manage", "reconcile"), frozenset({"discovery", "catalog"})),
    (("reconcile",), frozenset({"discovery", "catalog"})),
    (("manage", "serve"), frozenset({"surfaces", "catalog"})),
    (("serve",), frozenset({"surfaces", "catalog"})),
    (("manage", "ui"), frozenset({"surfaces", "catalog"})),
    (("ui",), frozenset({"surfaces", "catalog"})),
    (("manage", "doctor"), frozenset({"catalog", "discovery", "auth", "events", "runs"})),
    (("doctor",), frozenset({"catalog", "discovery", "auth", "events", "runs"})),
    (("import",), frozenset({"imports", "config"})),
    (("manage", "config"), frozenset({"config"})),
    (("config",), frozenset({"config"})),
    (("manage", "completion"), frozenset({"completion"})),
    (("completion",), frozenset({"completion"})),
)

_STATIC_TOP_LEVEL_COMMANDS: frozenset[str] = frozenset(
    {
        "manage",
        "import",
        "config",
        "source",
        "mount",
        "alias",
        "catalog",
        "docs",
        "workflow",
        "inspect",
        "auth",
        "secret",
        "runs",
        "logs",
        "serve",
        "ui",
        "completion",
        "doctor",
        "sync",
        "reconcile",
        "invoke",
        "explain",
    }
)


def resolve_auto_mode(command_path: tuple[str, ...], *, help_requested: bool) -> LoadMode:
    if help_requested:
        return "help"
    if not command_path:
        return "full"
    if _matches_prefix(command_path, _INVOKE_MODE_PREFIXES):
        return "invoke"
    if _matches_prefix(command_path, _FULL_MODE_PREFIXES):
        return "full"

    # Any unknown top-level token is treated as a mounted dynamic command path.
    if command_path[0] not in _STATIC_TOP_LEVEL_COMMANDS:
        return "invoke"
    return "full"


def resolve_command_scopes(command_path: tuple[str, ...]) -> frozenset[CommandScope]:
    if not command_path:
        return frozenset({"catalog"})
    for prefix, scopes in _COMMAND_SCOPES:
        if command_path[: len(prefix)] == prefix:
            return scopes
    if command_path[0] not in _STATIC_TOP_LEVEL_COMMANDS:
        return frozenset({"mount_execution"})
    return frozenset({"catalog"})


def should_load_drift_governance(command_path: tuple[str, ...], *, help_requested: bool) -> bool:
    if help_requested:
        return False
    scopes = resolve_command_scopes(command_path)
    return bool(scopes.intersection(frozenset({"catalog", "discovery", "mount_execution", "surfaces"})))


def _matches_prefix(command_path: tuple[str, ...], prefixes: tuple[tuple[str, ...], ...]) -> bool:
    return any(command_path[: len(prefix)] == prefix for prefix in prefixes)
