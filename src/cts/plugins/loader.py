from __future__ import annotations

import importlib
import importlib.util
import fnmatch
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Optional

from cts.config.loader import LoadedConfig
from cts.config.models import HookConfig, PluginConfig
from cts.execution.errors import CTSStructuredError, ConfigError
from cts.plugins.contracts import get_hook_contract


class PluginLoadError(ConfigError):
    error_code = "plugin_load_failed"


class HookExecutionError(CTSStructuredError):
    error_type = "HookError"
    error_code = "hook_failed"
    default_exit_code = 9


@dataclass
class HookContext:
    event: str
    plugin_name: str
    plugin_config: PluginConfig
    hook_config: HookConfig
    payload: MutableMapping[str, Any]
    app: Any = None


@dataclass
class LoadedPlugin:
    name: str
    config: PluginConfig
    module: ModuleType
    instance: Any
    providers: Dict[str, Any] = field(default_factory=dict)
    hook_handlers: Dict[str, Callable[[HookContext], Optional[MutableMapping[str, Any]]]] = field(default_factory=dict)


class PluginManager:
    def __init__(self, loaded_config: LoadedConfig) -> None:
        self.loaded_config = loaded_config
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._provider_owners: Dict[str, str] = {}
        self._provider_conflicts: list[Dict[str, Any]] = []
        self._load_plugins()
        self._validate_hooks()

    def register_providers(self, registry: Any) -> None:
        for plugin in self._plugins.values():
            for provider_type, provider in plugin.providers.items():
                normalized = str(provider_type).strip().lower()
                if not normalized:
                    raise PluginLoadError(f"plugin '{plugin.name}' registered empty provider_type")
                if normalized in registry.supported_types():
                    self._provider_conflicts.append(
                        {
                            "provider_type": normalized,
                            "plugin": plugin.name,
                            "existing_owner": self._provider_owners.get(normalized, "core"),
                            "action": "skipped",
                        }
                    )
                    continue
                registry.register(normalized, provider)
                self._provider_owners[normalized] = plugin.name

    def supported_provider_types(self) -> set[str]:
        result = set()
        for plugin in self._plugins.values():
            result.update(plugin.providers.keys())
        return result

    @property
    def provider_conflicts(self) -> list[Dict[str, Any]]:
        return [dict(item) for item in self._provider_conflicts]

    def describe_plugins(self) -> list[Dict[str, Any]]:
        items: list[Dict[str, Any]] = []
        hook_bindings = self.describe_hooks()
        hooks_by_plugin: Dict[str, list[Dict[str, Any]]] = {}
        for hook in hook_bindings:
            hooks_by_plugin.setdefault(str(hook.get("plugin") or ""), []).append(hook)

        for name, plugin in sorted(self._plugins.items()):
            config = plugin.config
            provider_types = []
            for provider_type, provider in sorted(plugin.providers.items()):
                normalized = str(provider_type).strip().lower()
                provider_types.append(
                    {
                        "provider_type": normalized,
                        "active": self._provider_owners.get(normalized) == name,
                        "class_name": provider.__class__.__name__,
                        "module": provider.__class__.__module__,
                    }
                )
            items.append(
                {
                    "name": name,
                    "enabled": bool(config.enabled),
                    "module": config.module,
                    "path": config.path,
                    "resolved_path": str(self._resolve_path(config.path)) if config.path else None,
                    "factory": config.factory,
                    "config": dict(config.config),
                    "provider_types": provider_types,
                    "hook_handlers": sorted(plugin.hook_handlers.keys()),
                    "bound_hooks": hooks_by_plugin.get(name, []),
                }
            )
        return items

    def describe_hooks(self) -> list[Dict[str, Any]]:
        items: list[Dict[str, Any]] = []
        for index, hook in enumerate(self.loaded_config.config.hooks):
            plugin = self._plugins.get(hook.plugin)
            items.append(
                {
                    "id": f"{hook.event}:{hook.plugin}:{hook.handler}:{index}",
                    "index": index,
                    "event": hook.event,
                    "plugin": hook.plugin,
                    "handler": hook.handler,
                    "enabled": bool(hook.enabled),
                    "priority": hook.priority,
                    "fail_mode": hook.fail_mode,
                    "when": dict(hook.when),
                    "config": dict(hook.config),
                    "plugin_loaded": plugin is not None,
                    "handler_available": plugin is not None and hook.handler in plugin.hook_handlers,
                }
            )
        return items

    def provider_owner(self, provider_type: str) -> Dict[str, Any]:
        normalized = str(provider_type).strip().lower()
        owner = self._provider_owners.get(normalized)
        if owner:
            return {"owner_type": "plugin", "owner_name": owner}
        return {"owner_type": "core", "owner_name": "core"}

    def explain_dispatch(self, event: str, payload: MutableMapping[str, Any], *, app: Any = None) -> Dict[str, Any]:
        context_values = _hook_context_values(payload, app, event=event)
        contract = get_hook_contract(event)
        items: list[Dict[str, Any]] = []
        for index, hook in self._iter_hooks_for_event(event):
            evaluation = self._explain_hook_match(hook, payload, app)
            plugin = self._plugins.get(hook.plugin)
            items.append(
                {
                    "id": f"{hook.event}:{hook.plugin}:{hook.handler}:{index}",
                    "index": index,
                    "event": hook.event,
                    "plugin": hook.plugin,
                    "handler": hook.handler,
                    "priority": hook.priority,
                    "fail_mode": hook.fail_mode,
                    "plugin_loaded": plugin is not None,
                    "handler_available": plugin is not None and hook.handler in plugin.hook_handlers,
                    "matched": evaluation["matched"],
                    "criteria": evaluation["criteria"],
                    "when": dict(hook.when),
                }
            )
        return {
            "event": event,
            "contract": contract,
            "context": _serialize_payload_value(context_values),
            "payload": _serialize_payload_value(dict(payload)),
            "hooks": items,
        }

    def simulate_dispatch(
        self,
        event: str,
        payload: MutableMapping[str, Any],
        *,
        app: Any = None,
        execute_handlers: bool = False,
    ) -> Dict[str, Any]:
        explanation = self.explain_dispatch(event, payload, app=app)
        current_payload = payload
        steps: list[Dict[str, Any]] = []
        halted = False
        contract = get_hook_contract(event) or {}

        for index, hook in self._iter_hooks_for_event(event):
            evaluation = self._explain_hook_match(hook, current_payload, app)
            plugin = self._plugins.get(hook.plugin)
            step = {
                "id": f"{hook.event}:{hook.plugin}:{hook.handler}:{index}",
                "index": index,
                "event": hook.event,
                "plugin": hook.plugin,
                "handler": hook.handler,
                "priority": hook.priority,
                "fail_mode": hook.fail_mode,
                "plugin_loaded": plugin is not None,
                "handler_available": plugin is not None and hook.handler in plugin.hook_handlers,
                "matched": evaluation["matched"],
                "criteria": evaluation["criteria"],
                "when": dict(hook.when),
            }
            if not step.get("matched"):
                step["status"] = "skipped"
                steps.append(step)
                continue

            if plugin is None:
                step["status"] = "plugin_missing"
                steps.append(step)
                continue
            handler = plugin.hook_handlers.get(hook.handler)
            if handler is None:
                step["status"] = "handler_missing"
                steps.append(step)
                continue
            if not execute_handlers:
                step["status"] = "matched"
                steps.append(step)
                continue

            context = HookContext(
                event=event,
                plugin_name=plugin.name,
                plugin_config=plugin.config,
                hook_config=hook,
                payload=current_payload,
                app=app,
            )
            try:
                result = handler(context)
            except Exception as exc:
                step["status"] = "error"
                step["error"] = {"type": exc.__class__.__name__, "message": str(exc)}
                steps.append(step)
                if hook.fail_mode == "raise":
                    halted = True
                    break
                continue

            if isinstance(result, MutableMapping):
                current_payload = result
                step["status"] = "applied"
                step["mutated"] = True
                step["result_payload"] = _serialize_payload_value(dict(result))
            else:
                step["status"] = "applied"
                step["mutated"] = False
            steps.append(step)

        return {
            **explanation,
            "execute_handlers": execute_handlers,
            "simulation": {
                **dict(contract.get("simulation") or {}),
                "mode": "handler_execution" if execute_handlers else "match_only",
                "execute_handlers": execute_handlers,
                "provider_calls_blocked": True,
                "mount_execution_blocked": True,
            },
            "steps": steps,
            "halted": halted,
            "final_payload": _serialize_payload_value(dict(current_payload)),
        }

    def dispatch(self, event: str, payload: MutableMapping[str, Any], *, app: Any = None) -> MutableMapping[str, Any]:
        current_payload = payload
        for index, hook in self._iter_hooks_for_event(event):
            if not self._matches_hook(hook, current_payload, app):
                self._emit_hook_debug_event(
                    app,
                    event="hook_dispatch_skipped",
                    hook_event=event,
                    plugin_name=hook.plugin,
                    handler_name=hook.handler,
                    priority=hook.priority,
                    index=index,
                    payload=current_payload,
                    data={"reason": "when_mismatch", "when": dict(hook.when), "payload_keys": sorted(current_payload.keys())},
                )
                continue
            plugin = self._plugins.get(hook.plugin)
            if plugin is None:
                continue
            handler = plugin.hook_handlers.get(hook.handler)
            if handler is None:
                continue
            self._emit_hook_debug_event(
                app,
                event="hook_dispatch_start",
                hook_event=event,
                plugin_name=plugin.name,
                handler_name=hook.handler,
                priority=hook.priority,
                index=index,
                payload=current_payload,
                data={"payload_keys": sorted(current_payload.keys()), "fail_mode": hook.fail_mode},
            )
            context = HookContext(
                event=event,
                plugin_name=plugin.name,
                plugin_config=plugin.config,
                hook_config=hook,
                payload=current_payload,
                app=app,
            )
            try:
                result = handler(context)
            except Exception as exc:
                self._emit_hook_debug_event(
                    app,
                    event="hook_dispatch_error",
                    level="WARN" if hook.fail_mode != "raise" else "ERROR",
                    hook_event=event,
                    plugin_name=plugin.name,
                    handler_name=hook.handler,
                    priority=hook.priority,
                    index=index,
                    payload=current_payload,
                    data={"fail_mode": hook.fail_mode, "error": str(exc)},
                )
                if hook.fail_mode == "ignore":
                    continue
                if hook.fail_mode == "warn":
                    self._emit_hook_warning(app, event, plugin.name, hook.handler, exc)
                    continue
                raise HookExecutionError(
                    f"hook failed for event '{event}' via {plugin.name}.{hook.handler}: {exc}",
                    details={
                        "event": event,
                        "plugin": plugin.name,
                        "handler": hook.handler,
                        "priority": hook.priority,
                        "index": index,
                    },
                ) from exc
            if isinstance(result, MutableMapping):
                self._emit_hook_debug_event(
                    app,
                    event="hook_dispatch_complete",
                    hook_event=event,
                    plugin_name=plugin.name,
                    handler_name=hook.handler,
                    priority=hook.priority,
                    index=index,
                    payload=current_payload,
                    data={
                        "payload_keys": sorted(current_payload.keys()),
                        "result_keys": sorted(result.keys()),
                        "mutated": True,
                    },
                )
                current_payload = result
            else:
                self._emit_hook_debug_event(
                    app,
                    event="hook_dispatch_complete",
                    hook_event=event,
                    plugin_name=plugin.name,
                    handler_name=hook.handler,
                    priority=hook.priority,
                    index=index,
                    payload=current_payload,
                    data={"payload_keys": sorted(current_payload.keys()), "result_keys": [], "mutated": False},
                )
        return current_payload

    def has_plugins(self) -> bool:
        return bool(self._plugins)

    def _load_plugins(self) -> None:
        for name, plugin_config in self.loaded_config.config.plugins.items():
            if not plugin_config.enabled:
                continue
            module = self._load_module(name, plugin_config)
            instance = _build_plugin_instance(name, plugin_config, module)
            providers = _normalize_mapping(_call_optional(instance, "register_providers"), f"{name}.register_providers")
            hook_handlers = _normalize_mapping(_call_optional(instance, "get_hook_handlers"), f"{name}.get_hook_handlers")
            self._plugins[name] = LoadedPlugin(
                name=name,
                config=plugin_config,
                module=module,
                instance=instance,
                providers=providers,
                hook_handlers=hook_handlers,
            )

    def _load_module(self, name: str, plugin_config: PluginConfig) -> ModuleType:
        if plugin_config.module:
            return importlib.import_module(plugin_config.module)
        if plugin_config.path:
            path = self._resolve_path(plugin_config.path)
            if not path.exists():
                raise PluginLoadError(f"plugin file not found: {path}")
            module_name = f"cts_plugin_{name.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"unable to load plugin module spec: {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        raise PluginLoadError(f"plugin '{name}' must declare either module or path")

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        if self.loaded_config.root_paths:
            return (self.loaded_config.root_paths[-1].parent / candidate).resolve()
        if self.loaded_config.paths:
            return (self.loaded_config.paths[0].parent / candidate).resolve()
        return (Path.cwd() / candidate).resolve()

    def _validate_hooks(self) -> None:
        for hook in self.loaded_config.config.hooks:
            if hook.plugin not in self._plugins:
                raise PluginLoadError(f"hook references unknown plugin: {hook.plugin}")
            plugin = self._plugins[hook.plugin]
            if hook.handler not in plugin.hook_handlers:
                raise PluginLoadError(
                    f"hook handler not found: {hook.plugin}.{hook.handler}"
                )
            if hook.fail_mode not in {"warn", "raise", "ignore"}:
                raise PluginLoadError(
                    f"unsupported hook fail_mode '{hook.fail_mode}' for {hook.plugin}.{hook.handler}"
                )
            if not isinstance(hook.when, Mapping):
                raise PluginLoadError(
                    f"hook when must be a mapping for {hook.plugin}.{hook.handler}"
                )

    def _emit_hook_warning(self, app: Any, event: str, plugin_name: str, handler_name: str, exc: Exception) -> None:
        if app is None:
            return
        try:
            from cts.execution.logging import emit_app_event

            emit_app_event(
                app,
                event="hook_failed",
                level="WARN",
                data={
                    "hook_event": event,
                    "plugin": plugin_name,
                    "handler": handler_name,
                    "error": str(exc),
                },
            )
        except Exception:
            return

    def _emit_hook_debug_event(
        self,
        app: Any,
        *,
        event: str,
        hook_event: str,
        plugin_name: str,
        handler_name: str,
        priority: int,
        index: int,
        payload: Optional[MutableMapping[str, Any]] = None,
        level: str = "INFO",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        if app is None:
            return
        try:
            from cts.execution.logging import emit_app_event

            context = _hook_context_values(payload or {}, app, event=hook_event)
            emit_app_event(
                app,
                event=event,
                level=level,
                source=context.get("source_name"),
                mount_id=context.get("mount_id"),
                operation_id=context.get("operation_id"),
                data={
                    "hook_event": hook_event,
                    "plugin": plugin_name,
                    "handler": handler_name,
                    "priority": priority,
                    "index": index,
                    **dict(data or {}),
                },
            )
        except Exception:
            return

    def _iter_hooks_for_event(self, event: str) -> list[tuple[int, HookConfig]]:
        hooks = [
            (index, hook)
            for index, hook in enumerate(self.loaded_config.config.hooks)
            if hook.enabled and hook.event == event
        ]
        hooks.sort(key=lambda item: (item[1].priority, item[0]))
        return hooks

    def _matches_hook(self, hook: HookConfig, payload: MutableMapping[str, Any], app: Any) -> bool:
        return bool(self._explain_hook_match(hook, payload, app)["matched"])

    def _explain_hook_match(self, hook: HookConfig, payload: MutableMapping[str, Any], app: Any) -> Dict[str, Any]:
        if not hook.when:
            return {"matched": True, "criteria": []}
        context_values = _hook_context_values(payload, app, event=hook.event)
        criteria = []
        matched = True
        for key, expected in hook.when.items():
            source = "context" if key in context_values else "payload"
            actual = context_values.get(key, _resolve_dotted_path(payload, key))
            passed = _match_expected(actual, expected)
            if not passed:
                matched = False
            criteria.append(
                {
                    "key": key,
                    "source": source,
                    "expected": _serialize_payload_value(expected),
                    "actual": _serialize_payload_value(actual),
                    "matched": passed,
                }
            )
        return {"matched": matched, "criteria": criteria}


def _build_plugin_instance(name: str, plugin_config: PluginConfig, module: ModuleType) -> Any:
    if plugin_config.factory:
        factory = getattr(module, plugin_config.factory, None)
        if factory is None or not callable(factory):
            raise PluginLoadError(f"plugin factory not found: {name}.{plugin_config.factory}")
        return _call_factory(factory, name, plugin_config)

    if hasattr(module, "get_plugin") and callable(module.get_plugin):
        return _call_factory(module.get_plugin, name, plugin_config)

    if hasattr(module, "plugin"):
        return module.plugin

    if hasattr(module, "Plugin"):
        plugin_class = getattr(module, "Plugin")
        return _call_factory(plugin_class, name, plugin_config)

    raise PluginLoadError(
        f"plugin '{name}' must expose factory, get_plugin(), plugin, or Plugin"
    )


def _call_factory(factory: Callable[..., Any], name: str, plugin_config: PluginConfig) -> Any:
    attempts = [
        lambda: factory(plugin_name=name, config=dict(plugin_config.config)),
        lambda: factory(name=name, config=dict(plugin_config.config)),
        lambda: factory(config=dict(plugin_config.config)),
        lambda: factory(),
    ]
    last_error: Optional[Exception] = None
    for attempt in attempts:
        try:
            return attempt()
        except TypeError as exc:
            last_error = exc
            continue
    raise PluginLoadError(f"unable to construct plugin '{name}': {last_error}")


def _call_optional(instance: Any, method_name: str) -> Any:
    method = getattr(instance, method_name, None)
    if method is None:
        return {}
    if not callable(method):
        raise PluginLoadError(f"{instance!r}.{method_name} is not callable")
    return method()


def _normalize_mapping(raw: Any, label: str) -> Dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise PluginLoadError(f"{label} must return a mapping")
    return {str(key): value for key, value in raw.items()}


def _hook_context_values(payload: Mapping[str, Any], app: Any, *, event: str | None = None) -> Dict[str, Any]:
    values: Dict[str, Any] = {"event": event}
    values["profile"] = getattr(app, "active_profile", None) if app is not None else None

    for key in ["event", "source_name", "provider_type", "mode", "method", "path", "surface", "mount_id", "operation_id"]:
        if key in payload:
            values[key] = payload.get(key)

    mount = payload.get("mount")
    if mount is not None:
        values.setdefault("mount_id", getattr(mount, "mount_id", None))
        values.setdefault("source", getattr(mount, "source_name", None))
        values.setdefault("source_name", getattr(mount, "source_name", None))
        values.setdefault("provider_type", getattr(mount, "provider_type", None))
        operation = getattr(mount, "operation", None)
        values.setdefault("operation_id", getattr(operation, "id", None) if operation is not None else None)

    source_config = payload.get("source_config")
    if source_config is not None:
        values.setdefault("provider_type", getattr(source_config, "type", None))

    if "source" in payload:
        values.setdefault("source", payload.get("source"))
        values.setdefault("source_name", payload.get("source"))
    if "source_name" in values and "source" not in values:
        values["source"] = values["source_name"]
    return values


def _resolve_dotted_path(value: Any, path: str) -> Any:
    current = value
    for part in str(path).split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return None
            current = current[part]
            continue
        if hasattr(current, part):
            current = getattr(current, part)
            continue
        return None
    return current


def _match_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        if "exists" in expected:
            return (actual is not None) == bool(expected["exists"])
        if "eq" in expected:
            return _match_expected(actual, expected["eq"])
        if "glob" in expected:
            return _match_glob(actual, expected["glob"])
        if "in" in expected and isinstance(expected["in"], list):
            return any(_match_expected(actual, item) for item in expected["in"])
        if "not" in expected:
            return not _match_expected(actual, expected["not"])
        return False
    if isinstance(expected, list):
        return any(_match_expected(actual, item) for item in expected)
    if isinstance(expected, str) and any(char in expected for char in "*?[]"):
        return _match_glob(actual, expected)
    return actual == expected


def _match_glob(actual: Any, pattern: Any) -> bool:
    if actual is None:
        return False
    return fnmatch.fnmatch(str(actual), str(pattern))


def _serialize_payload_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Exception):
        return {"type": value.__class__.__name__, "message": str(value)}
    if isinstance(value, Mapping):
        return {str(key): _serialize_payload_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_payload_value(item) for item in value]
    if hasattr(value, "mount_id") and hasattr(value, "source_name"):
        operation = getattr(value, "operation", None)
        return {
            "mount_id": getattr(value, "mount_id", None),
            "source": getattr(value, "source_name", None),
            "provider_type": getattr(value, "provider_type", None),
            "operation_id": getattr(operation, "id", None) if operation is not None else None,
        }
    if hasattr(value, "type") and hasattr(value, "enabled"):
        return {
            "type": getattr(value, "type", None),
            "enabled": getattr(value, "enabled", None),
            "auth_ref": getattr(value, "auth_ref", None),
        }
    if hasattr(value, "__class__"):
        return {"class_name": value.__class__.__name__, "module": value.__class__.__module__}
    return repr(value)
