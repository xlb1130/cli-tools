from __future__ import annotations

import fnmatch
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from cts.auth import AuthManager
from cts.config.loader import LoadedConfig, load_config
from cts.config.models import MountConfig, ParamConfig, SourceConfig
from cts.discovery import DiscoveryStore, compare_discovery_snapshots
from cts.execution.errors import PolicyError
from cts.execution.logging import emit_app_event, utc_now_iso
from cts.models import MountRecord, OperationDescriptor
from cts.plugins import PluginManager
from cts.providers.registry import ProviderRegistry
from cts.secrets import SecretManager


class Catalog:
    def __init__(self) -> None:
        self.mounts: List[MountRecord] = []
        self._mounts_by_id: Dict[str, MountRecord] = {}
        self._path_index: Dict[Tuple[str, ...], MountRecord] = {}
        self._group_help: Dict[Tuple[str, ...], Dict[str, str]] = {}
        self._conflicts: List[Dict[str, Any]] = []

    @property
    def conflicts(self) -> List[Dict[str, Any]]:
        return list(self._conflicts)

    def add_mount(self, mount: MountRecord) -> None:
        if mount.mount_id in self._mounts_by_id:
            self._conflicts.append(
                {"type": "mount_id", "mount_id": mount.mount_id, "command_path": mount.command_path}
            )
            return

        if not self._register_path(mount.command_path, mount, path_type="command_path"):
            return

        self.mounts.append(mount)
        self._mounts_by_id[mount.mount_id] = mount
        for alias in mount.aliases:
            self._register_path(alias, mount, path_type="mount_alias", target_path=mount.command_path)

    def add_alias(self, alias_path: Iterable[str], target_path: Iterable[str]) -> None:
        target_tokens = tuple(target_path)
        mount = self._path_index.get(target_tokens)
        if mount is None:
            self._conflicts.append(
                {
                    "type": "alias_target_not_found",
                    "alias_path": list(alias_path),
                    "target_path": list(target_path),
                }
            )
            return

        alias_tokens = list(alias_path)
        if alias_tokens not in mount.aliases:
            mount.aliases.append(alias_tokens)
        self._register_path(alias_tokens, mount, path_type="config_alias", target_path=target_tokens)

    def _register_path(
        self,
        path: Iterable[str],
        mount: MountRecord,
        *,
        path_type: str,
        target_path: Optional[Iterable[str]] = None,
    ) -> bool:
        key = tuple(path)
        if not key:
            return False

        if key in self._path_index:
            existing = self._path_index[key]
            if existing.mount_id == mount.mount_id:
                return True
            self._conflicts.append(
                {
                    "type": "command_path",
                    "path": list(key),
                    "mount_id": mount.mount_id,
                    "existing_mount_id": existing.mount_id,
                    "path_type": path_type,
                    "target_path": list(target_path) if target_path else None,
                }
            )
            return False

        for existing_key, existing_mount in self._path_index.items():
            if key[: len(existing_key)] == existing_key or existing_key[: len(key)] == key:
                self._conflicts.append(
                    {
                        "type": "path_prefix",
                        "path": list(key),
                        "existing_path": list(existing_key),
                        "mount_id": mount.mount_id,
                        "existing_mount_id": existing_mount.mount_id,
                        "path_type": path_type,
                        "target_path": list(target_path) if target_path else None,
                    }
                )
                return False
        self._path_index[key] = mount
        return True

    def find_by_id(self, mount_id: str) -> Optional[MountRecord]:
        return self._mounts_by_id.get(mount_id)

    def find_by_path(self, path: Iterable[str]) -> Optional[MountRecord]:
        return self._path_index.get(tuple(path))

    def find_by_source_and_operation(self, source_name: str, operation_id: str) -> Optional[MountRecord]:
        for mount in self.mounts:
            if mount.source_name == source_name and mount.operation.id == operation_id:
                return mount
        return None

    def has_group(self, prefix: Iterable[str]) -> bool:
        prefix_tuple = tuple(prefix)
        for path in self._path_index:
            if len(path) > len(prefix_tuple) and path[: len(prefix_tuple)] == prefix_tuple:
                return True
        if prefix_tuple in self._group_help:
            return True
        return False

    def child_tokens(self, prefix: Iterable[str]) -> List[str]:
        prefix_tuple = tuple(prefix)
        tokens = set()
        for path in self._path_index:
            if len(path) <= len(prefix_tuple):
                continue
            if path[: len(prefix_tuple)] == prefix_tuple:
                tokens.add(path[len(prefix_tuple)])
        return sorted(tokens)

    def group_summary(self, prefix: Iterable[str]) -> str:
        help_payload = self._group_help.get(tuple(prefix)) or {}
        return help_payload.get("summary") or "Dynamic command group for " + " ".join(prefix)

    def group_description(self, prefix: Iterable[str]) -> str:
        help_payload = self._group_help.get(tuple(prefix)) or {}
        return help_payload.get("description") or self.group_summary(prefix)

    def add_group_help(self, prefix: Iterable[str], *, summary: Optional[str], description: Optional[str]) -> None:
        prefix_tuple = tuple(prefix)
        if not prefix_tuple:
            return
        self._group_help[prefix_tuple] = {
            "summary": summary or " ".join(prefix_tuple),
            "description": description or summary or "Dynamic command group for " + " ".join(prefix_tuple),
        }

    def to_catalog(self) -> Dict[str, Any]:
        return {
            "mounts": [mount.to_summary() for mount in self.mounts],
            "conflicts": list(self._conflicts),
        }


class CTSApp:
    def __init__(
        self,
        loaded_config: LoadedConfig,
        active_profile: Optional[str] = None,
        explicit_config_path: Optional[str] = None,
        requested_profile: Optional[str] = None,
        compile_mode: str = "full",
        target_source_names: Optional[List[str]] = None,
        load_drift_governance: bool = True,
    ) -> None:
        self.loaded_config = loaded_config
        self.config = loaded_config.config
        self.active_profile = active_profile or self.config.app.default_profile
        self.explicit_config_path = explicit_config_path
        self.requested_profile = requested_profile
        self.compile_mode = compile_mode
        self.target_source_names = set(target_source_names or [])
        self.load_drift_governance = load_drift_governance
        self.plugin_manager = PluginManager(loaded_config)
        self.provider_registry = ProviderRegistry()
        self.plugin_manager.register_providers(self.provider_registry)
        self.discovery_store = DiscoveryStore(self)
        self._secret_manager: Optional[SecretManager] = None
        self._auth_manager: Optional[AuthManager] = None
        self._drift_governance_loaded = not load_drift_governance
        self.sync_baselines: Dict[str, Optional[Dict[str, Any]]] = {}
        self.latest_drift_report: Optional[Dict[str, Any]] = None
        self.source_drift_state: Dict[str, Dict[str, Any]] = {}
        self.mount_drift_state: Dict[str, Dict[str, Any]] = {}
        self.source_operations: Dict[str, Dict[str, OperationDescriptor]] = {}
        self.schema_cache: Dict[str, Dict[str, Any]] = {}
        self.schema_provenance_index: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.discovery_errors: Dict[str, str] = {}
        self.discovery_state: Dict[str, Dict[str, Any]] = {}
        self.catalog = Catalog()
        self._compile()
        self.dispatch_hooks("app.init", {"app": self})
        emit_app_event(
            self,
            event="config_merge_complete",
            data={
                "config_files": [str(path) for path in self.config_paths],
                "source_count": len(self.config.sources),
                "mount_count": len(self.config.mounts),
                "plugin_count": len(self.config.plugins),
                "hook_count": len(self.config.hooks),
                "discovery_error_count": len(self.discovery_errors),
            },
        )
        emit_app_event(
            self,
            event="profile_resolved",
            data={"profile": self.active_profile},
        )

    @property
    def config_paths(self) -> List[Path]:
        return self.loaded_config.paths

    @property
    def secret_manager(self) -> SecretManager:
        if self._secret_manager is None:
            self._secret_manager = SecretManager(self)
        return self._secret_manager

    @property
    def auth_manager(self) -> AuthManager:
        if self._auth_manager is None:
            self._auth_manager = AuthManager(self)
        return self._auth_manager

    @property
    def primary_config_dir(self) -> Path:
        if self.loaded_config.root_paths:
            return self.loaded_config.root_paths[-1].parent
        if self.loaded_config.paths:
            return self.loaded_config.paths[0].parent
        return Path.cwd()

    def resolve_path(self, raw_path: str, owner: Any = None) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path
        owner_origin = self.origin_file_for(owner)
        if owner_origin:
            return (owner_origin.parent / path).resolve()
        return (self.primary_config_dir / path).resolve()

    def origin_file_for(self, owner: Any) -> Optional[Path]:
        if owner is None:
            return None
        model_extra = getattr(owner, "model_extra", None) or {}
        origin = model_extra.get("__origin_file__")
        if origin:
            return Path(origin)
        return None

    def get_provider(self, source_config: SourceConfig):
        return self.provider_registry.get(source_config.type)

    def get_schema_info(
        self,
        source_name: str,
        source_config: SourceConfig,
        operation_id: str,
    ) -> Optional[tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
        schema_info = self._schema_info_from_memory(source_name, operation_id)
        if schema_info:
            return schema_info

        provider = self.get_provider(source_config)
        try:
            schema_info = provider.get_schema(source_name, source_config, operation_id, self)
        except Exception as exc:  # pragma: no cover - defensive path
            emit_app_event(
                self,
                event="schema_lookup_failed",
                level="WARNING",
                source=source_name,
                operation_id=operation_id,
                data={"provider_type": source_config.type, "error": str(exc)},
            )
            schema_info = None

        if schema_info:
            schema, provenance = schema_info
            self._remember_schema_info(source_name, operation_id, schema, provenance)
            return self._schema_info_from_memory(source_name, operation_id)

        operation = self.source_operations.get(source_name, {}).get(operation_id)
        if operation and operation.input_schema:
            provenance = self._default_schema_provenance(source_config, operation)
            self._remember_schema_info(source_name, operation_id, operation.input_schema, provenance)
            return self._schema_info_from_memory(source_name, operation_id)
        return None

    def dispatch_hooks(self, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return dict(self.plugin_manager.dispatch(event, payload, app=self))

    def get_mount_drift_state(self, mount: MountRecord | str | None) -> Optional[Dict[str, Any]]:
        self._ensure_drift_governance_loaded()
        if mount is None:
            return None
        mount_id = mount if isinstance(mount, str) else mount.mount_id
        state = self.mount_drift_state.get(mount_id)
        return dict(state) if state else None

    def get_source_drift_state(self, source_name: str) -> Optional[Dict[str, Any]]:
        self._ensure_drift_governance_loaded()
        state = self.source_drift_state.get(source_name)
        return dict(state) if state else None

    def get_latest_drift_report(self, source_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        self._ensure_drift_governance_loaded()
        report = dict(self.latest_drift_report) if self.latest_drift_report else None
        if report is None:
            loaded = self.discovery_store.load_latest_sync_report(source_name)
            report = dict(loaded) if loaded else None
        if report is None:
            return None
        report.setdefault("report_path", str(self.discovery_store.latest_sync_report_path(source_name)))
        if source_name:
            report["items"] = [item for item in report.get("items", []) if item.get("source") == source_name]
        return report

    def export_catalog(self) -> Dict[str, Any]:
        latest_drift = self.get_latest_drift_report()
        return {
            "version": 1,
            "kind": "catalog_export",
            "generated_at": utc_now_iso(),
            "profile": self.active_profile,
            "config_files": [str(path) for path in self.config_paths],
            "drift_summary": latest_drift.get("drift_summary") if latest_drift else None,
            "mounts": [
                {
                    **mount.to_summary(),
                    "operation_id": mount.operation.id,
                    "supported_surfaces": list(mount.operation.supported_surfaces),
                    "drift_state": self.get_mount_drift_state(mount),
                }
                for mount in self.catalog.mounts
            ],
            "sources": [
                {
                    "name": source_name,
                    "type": source.type,
                    "enabled": source.enabled,
                    "operation_count": len(self.source_operations.get(source_name, {})),
                    "drift_state": self.get_source_drift_state(source_name),
                }
                for source_name, source in self.config.sources.items()
            ],
            "conflicts": list(self.catalog.conflicts),
        }

    def ensure_mount_execution_allowed(
        self,
        mount: MountRecord,
        *,
        mode: str,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        if mode != "invoke":
            return
        drift_state = self.get_mount_drift_state(mount)
        if not drift_state or not drift_state.get("blocked"):
            return

        action = drift_state.get("action")
        code = "drift_execution_blocked"
        if action in {"freeze_mount", "disable_mount"}:
            code = "mount_frozen_by_drift"
        elif action == "require_manual_review":
            code = "mount_requires_drift_review"

        emit_app_event(
            self,
            event="policy_blocked",
            level="WARNING",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"policy": "drift", "action": action, "drift_state": drift_state},
        )
        raise PolicyError(
            f"mount execution blocked by drift policy: {mount.mount_id}",
            code=code,
            details={"mount_id": mount.mount_id, "action": action, "drift_state": drift_state},
            suggestions=[
                "先执行 `cts manage inspect drift "
                + mount.source_name
                + "` 查看最近一次 drift 分类和受影响原因。",
                "如果确认变更可接受，再执行后续的 drift reconcile 流程。",
            ],
        )

    def _compile(self) -> None:
        discovery_mode = "help" if self.compile_mode == "help" else "compile"
        self._discover_source_operations(mode=discovery_mode)
        self._compile_mounts()
        self._compile_aliases()
        self._compile_group_help()

    def _discover_source_operations(self, *, mode: str = "compile") -> None:
        for source_name, source_config in self.config.sources.items():
            if not source_config.enabled:
                continue
            if self.target_source_names and source_name not in self.target_source_names:
                continue
            self._discover_source(source_name, source_config, mode=mode)

    def _compile_mounts(self) -> None:
        for mount in self.config.mounts:
            if self.target_source_names and mount.source not in self.target_source_names:
                continue
            source_config = self.config.sources.get(mount.source)
            if not source_config or not source_config.enabled:
                continue

            source_operations = self.source_operations.get(mount.source, {})
            if mount.select:
                self._compile_selected_mounts(mount, source_config, source_operations)
            else:
                operation_id = mount.operation or mount.id
                operation = source_operations.get(operation_id) or synthesize_operation(mount, source_config, operation_id)
                record = build_mount_record(mount, source_config, operation, generated=False)
                self.catalog.add_mount(record)

    def _compile_selected_mounts(
        self,
        mount: MountConfig,
        source_config: SourceConfig,
        source_operations: Dict[str, OperationDescriptor],
    ) -> None:
        for operation in source_operations.values():
            if not operation_matches_select(operation, mount.select):
                continue
            generated_mount = build_generated_mount(mount, source_config, operation)
            self.catalog.add_mount(generated_mount)

    def _compile_aliases(self) -> None:
        for raw in self.config.aliases:
            alias_from = raw.get("from")
            alias_to = raw.get("to")
            if not isinstance(alias_from, list) or not isinstance(alias_to, list):
                self.catalog._conflicts.append(
                    {"type": "alias_invalid", "alias": raw}
                )
                continue
            self.catalog.add_alias(alias_from, alias_to)

    def _compile_group_help(self) -> None:
        if self.compile_mode == "invoke" and self.target_source_names:
            return
        for source_name, source_config in self.config.sources.items():
            if self.target_source_names and source_name not in self.target_source_names:
                continue
            model_extra = getattr(source_config, "model_extra", None) or {}
            for item in model_extra.get("imported_cli_groups") or []:
                if not isinstance(item, dict):
                    continue
                path = item.get("path") or []
                if not isinstance(path, list) or not path:
                    continue
                self.catalog.add_group_help(
                    path,
                    summary=item.get("summary"),
                    description=item.get("description"),
                )

    def sync(self, source_name: Optional[str] = None) -> Dict[str, Any]:
        items = []
        sources = self.config.sources.items()
        if source_name:
            source = self.config.sources.get(source_name)
            if not source:
                return {"items": [], "report_path": None, "capability_snapshot_path": None}
            sources = [(source_name, source)]

        for current_name, source_config in sources:
            items.append(self._discover_source(current_name, source_config, mode="sync"))
        self.catalog = Catalog()
        self._compile_mounts()
        self._compile_aliases()
        sync_generated_at = utc_now_iso()
        drift_summary = _aggregate_drift(items)
        governance = self._build_drift_governance(items, report_generated_at=sync_generated_at)
        self._drift_governance_loaded = True
        self.source_drift_state = governance["sources"]
        self.mount_drift_state = governance["mounts"]

        capability_snapshot = self.build_capability_snapshot()
        capability_snapshot_path = self.discovery_store.write_capability_snapshot(
            capability_snapshot,
            source_name=source_name,
        )
        report = {
            "version": 1,
            "kind": "sync_report",
            "generated_at": sync_generated_at,
            "requested_source": source_name,
            "profile": self.active_profile,
            "config_files": [str(path) for path in self.config_paths],
            "items": items,
            "drift_summary": drift_summary,
            "drift_governance": governance,
            "discovery_errors": dict(self.discovery_errors),
            "capability_snapshot_path": str(capability_snapshot_path),
        }
        report_path = self.discovery_store.write_sync_report(report, source_name=source_name)
        self.latest_drift_report = dict(report)
        self._annotate_drift_report_path(str(report_path))
        self._apply_drift_reconciliations()
        emit_app_event(
            self,
            event="sync_report_written",
            data={
                "requested_source": source_name,
                "report_path": str(report_path),
                "capability_snapshot_path": str(capability_snapshot_path),
                "item_count": len(items),
            },
        )
        return {
            "items": items,
            "drift_summary": report["drift_summary"],
            "drift_governance": governance,
            "report_path": str(report_path),
            "capability_snapshot_path": str(capability_snapshot_path),
        }

    def build_capability_snapshot(self) -> Dict[str, Any]:
        mounts = []
        for mount in self.catalog.mounts:
            schema_info = self.get_schema_info(mount.source_name, mount.source_config, mount.operation.id)
            mounts.append(
                {
                    "mount_id": mount.mount_id,
                    "command_path": list(mount.command_path),
                    "aliases": [list(alias) for alias in mount.aliases],
                    "stable_name": mount.stable_name,
                    "source": mount.source_name,
                    "provider_type": mount.provider_type,
                    "operation_id": mount.operation.id,
                    "summary": mount.summary,
                    "risk": mount.operation.risk,
                    "supported_surfaces": list(mount.operation.supported_surfaces),
                    "schema_provenance": schema_info[1] if schema_info else None,
                    "drift_state": self.get_mount_drift_state(mount),
                }
            )

        sources = []
        for source_name, source_config in self.config.sources.items():
            sources.append(
                {
                    "name": source_name,
                    "type": source_config.type,
                    "enabled": source_config.enabled,
                    "origin_file": str(self.origin_file_for(source_config)) if self.origin_file_for(source_config) else None,
                    "operation_count": len(self.source_operations.get(source_name, {})),
                    "discovery_state": dict(self.discovery_state.get(source_name, {})),
                    "drift_state": self.get_source_drift_state(source_name),
                }
            )

        return {
            "version": 1,
            "kind": "capability_snapshot",
            "generated_at": utc_now_iso(),
            "profile": self.active_profile,
            "config_files": [str(path) for path in self.config_paths],
            "providers": sorted(self.provider_registry.supported_types()),
            "plugins": sorted(self.config.plugins.keys()),
            "hooks": [
                {"event": hook.event, "plugin": hook.plugin, "handler": hook.handler, "fail_mode": hook.fail_mode}
                for hook in self.config.hooks
                if hook.enabled
            ],
            "plugin_provider_conflicts": self.plugin_manager.provider_conflicts,
            "sources": sources,
            "mounts": mounts,
            "conflicts": list(self.catalog.conflicts),
        }

    def _load_drift_governance(self) -> None:
        self._drift_governance_loaded = True
        report = self.discovery_store.load_latest_sync_report()
        if not report:
            self.latest_drift_report = None
            self.source_drift_state = {}
            self.mount_drift_state = {}
            return
        self.latest_drift_report = dict(report)
        governance = report.get("drift_governance")
        if isinstance(governance, dict):
            self.source_drift_state = {
                str(key): dict(value) for key, value in (governance.get("sources") or {}).items() if isinstance(value, dict)
            }
            self.mount_drift_state = {
                str(key): dict(value) for key, value in (governance.get("mounts") or {}).items() if isinstance(value, dict)
            }
            self._annotate_drift_report_path(str(self.discovery_store.latest_sync_report_path()))
            self._apply_drift_reconciliations()
            return
        computed = self._build_drift_governance(
            list(report.get("items") or []),
            report_generated_at=report.get("generated_at"),
        )
        self.source_drift_state = computed["sources"]
        self.mount_drift_state = computed["mounts"]
        self._annotate_drift_report_path(str(self.discovery_store.latest_sync_report_path()))
        self._apply_drift_reconciliations()

    def _ensure_drift_governance_loaded(self) -> None:
        if self._drift_governance_loaded:
            return
        if not self.load_drift_governance:
            self._drift_governance_loaded = True
            return
        self._load_drift_governance()

    def _annotate_drift_report_path(self, report_path: str) -> None:
        if not self.latest_drift_report:
            return
        self.latest_drift_report["report_path"] = report_path
        for source_state in self.source_drift_state.values():
            source_state.setdefault("report_path", report_path)
        for mount_state in self.mount_drift_state.values():
            mount_state.setdefault("report_path", report_path)

    def _build_drift_governance(
        self,
        items: List[Dict[str, Any]],
        *,
        report_generated_at: Optional[str] = None,
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        sources: Dict[str, Dict[str, Any]] = {}
        mounts: Dict[str, Dict[str, Any]] = {}
        effective_generated_at = report_generated_at or utc_now_iso()
        for item in items:
            source_name = str(item.get("source") or "")
            if not source_name:
                continue
            drift = dict(item.get("drift") or {})
            affected_mount_ids: List[str] = []
            affected_aliases: List[List[str]] = []
            blocked_mount_ids: List[str] = []
            source_state = {
                "source": source_name,
                "provider_type": item.get("provider_type"),
                "drift": drift,
                "status": "clean" if not drift.get("changed") else drift.get("severity") or "changed",
                "report_generated_at": effective_generated_at,
                "affected_mount_ids": affected_mount_ids,
                "affected_aliases": affected_aliases,
                "blocked_mount_ids": blocked_mount_ids,
            }
            sources[source_name] = source_state
            if not drift.get("changed"):
                source_state["accepted_mount_ids"] = []
                source_state["accepted_mount_count"] = 0
                source_state["affected_mount_count"] = 0
                source_state["blocked_mount_count"] = 0
                continue

            all_changes_accepted = True
            for change in drift.get("changes") or []:
                change_severity = str(change.get("severity") or drift.get("severity") or "compatible").strip().lower()
                impacted = self._affected_mount_ids_for_change(source_name, change)
                affected_mount_ids.extend(item for item in impacted if item not in affected_mount_ids)
                impacted_mounts = self._affected_mounts_for_change(source_name, change)
                change_actions: List[str] = []
                for mount in impacted_mounts:
                    action = self._resolve_drift_action(mount, change_severity)
                    change_actions.append(action)
                    state = mounts.setdefault(
                        mount.mount_id,
                        {
                            "mount_id": mount.mount_id,
                            "source": mount.source_name,
                            "operation_id": mount.operation.id,
                            "provider_type": mount.provider_type,
                            "status": "warning",
                            "blocked": False,
                            "action": action,
                            "severity": change_severity,
                            "reasons": [],
                            "changes": [],
                            "report_generated_at": effective_generated_at,
                            "aliases": [list(alias) for alias in mount.aliases],
                            "supported_surfaces": list(mount.operation.supported_surfaces),
                        },
                    )
                    state["action"] = _more_restrictive_action(state.get("action"), action)
                    state["severity"] = _max_summary_severity(str(state.get("severity") or "none"), change_severity)
                    if state["action"] in {"freeze_mount", "disable_mount"}:
                        state["status"] = "frozen"
                        state["blocked"] = True
                    elif state["action"] == "require_manual_review":
                        state["status"] = "review_required"
                        state["blocked"] = True
                    elif _is_accepting_drift_action(state["action"]):
                        state["status"] = "accepted"
                        state["blocked"] = False
                    else:
                        state["status"] = "warning"
                        state["blocked"] = False
                    state["reasons"] = sorted(set(list(state.get("reasons") or []) + list(change.get("reasons") or [])))
                    state["changes"] = _merge_drift_changes(state.get("changes") or [], [change])
                    for alias in state.get("aliases") or []:
                        if alias not in affected_aliases:
                            affected_aliases.append(alias)
                if not change_actions:
                    change_actions.append(self._resolve_drift_action(None, change_severity, source_name=source_name))
                if not all(_is_accepting_drift_action(action) for action in change_actions):
                    all_changes_accepted = False
            accepted_mount_ids: List[str] = []
            for mount in self.catalog.mounts:
                if mount.source_name != source_name:
                    continue
                mount_state = mounts.get(mount.mount_id)
                if not mount_state:
                    continue
                if mount_state.get("blocked") and mount.mount_id not in blocked_mount_ids:
                    blocked_mount_ids.append(mount.mount_id)
                if mount_state.get("status") == "accepted" and mount.mount_id not in accepted_mount_ids:
                    accepted_mount_ids.append(mount.mount_id)
            source_state["affected_mount_count"] = len(affected_mount_ids)
            source_state["blocked_mount_count"] = len(blocked_mount_ids)
            source_state["accepted_mount_ids"] = accepted_mount_ids
            source_state["accepted_mount_count"] = len(accepted_mount_ids)
            if all_changes_accepted:
                source_state["status"] = "accepted"
                source_state["accepted_by_policy"] = True
        return {"sources": sources, "mounts": mounts}

    def _affected_mounts_for_change(self, source_name: str, change: Dict[str, Any]) -> List[MountRecord]:
        operation_id = change.get("operation_id")
        mounts = [mount for mount in self.catalog.mounts if mount.source_name == source_name]
        if operation_id:
            mounts = [mount for mount in mounts if mount.operation.id == operation_id]
        return mounts

    def _affected_mount_ids_for_change(self, source_name: str, change: Dict[str, Any]) -> List[str]:
        operation_id = str(change.get("operation_id") or "")
        result: List[str] = []
        for mount in self._affected_mounts_for_change(source_name, change):
            if mount.mount_id not in result:
                result.append(mount.mount_id)
        for mount_config in self.config.mounts:
            if mount_config.source != source_name:
                continue
            if mount_config.select:
                if operation_id:
                    candidate = f"{mount_config.id}.{operation_id}"
                    if candidate not in result:
                        result.append(candidate)
                continue
            configured_operation = mount_config.operation or mount_config.id
            if operation_id and configured_operation == operation_id and mount_config.id not in result:
                result.append(mount_config.id)
        return result

    def _resolve_drift_action(
        self,
        mount: Optional[MountRecord],
        severity: str,
        *,
        source_name: Optional[str] = None,
    ) -> str:
        mount_policy = dict(getattr(mount.mount_config, "drift_policy", {}) or {}) if mount else {}
        if mount is not None:
            source_policy = dict(getattr(mount.source_config, "drift_policy", {}) or {})
        else:
            source_config = self.config.sources.get(str(source_name or ""))
            source_policy = dict(getattr(source_config, "drift_policy", {}) or {}) if source_config else {}
        defaults = dict((self.config.drift.get("defaults") or {})) if isinstance(self.config.drift, dict) else {}
        policy_key = _drift_policy_key(severity)
        alias_key = f"accept_{severity}_changes"
        for policy in [mount_policy, source_policy, defaults]:
            if not policy:
                continue
            action = policy.get(policy_key)
            if action is not None:
                return str(action).strip().lower()
            if policy.get(alias_key) is True:
                return "auto_accept"
        return "warn"

    def _apply_drift_reconciliations(self) -> None:
        reconciliations = self.discovery_store.load_drift_reconciliations()
        items = [item for item in reconciliations.get("items", []) if isinstance(item, dict)]
        if not items:
            return
        index = {
            (str(item.get("source") or ""), str(item.get("report_generated_at") or "")): item
            for item in items
            if item.get("source") and item.get("report_generated_at")
        }
        for source_name, state in self.source_drift_state.items():
            key = (source_name, str(state.get("report_generated_at") or ""))
            reconcile = index.get(key)
            if not reconcile:
                continue
            action = str(reconcile.get("action") or "").strip().lower()
            if action != "accept_breaking":
                continue
            state["reconciled"] = True
            state["reconcile_action"] = action
            state["reconciled_at"] = reconcile.get("updated_at")
            if state.get("status") in {"breaking", "changed"}:
                state["status"] = "accepted"
        for mount_id, state in self.mount_drift_state.items():
            key = (str(state.get("source") or ""), str(state.get("report_generated_at") or ""))
            reconcile = index.get(key)
            if not reconcile:
                continue
            action = str(reconcile.get("action") or "").strip().lower()
            if action != "accept_breaking":
                continue
            state["blocked"] = False
            state["status"] = "accepted"
            state["reconciled"] = True
            state["reconcile_action"] = action
            state["reconciled_at"] = reconcile.get("updated_at")

    def _discover_source(self, source_name: str, source_config: SourceConfig, *, mode: str) -> Dict[str, Any]:
        cached_snapshot = self.discovery_store.load_source_snapshot(source_name)
        if mode == "compile" and source_name not in self.sync_baselines:
            self.sync_baselines[source_name] = dict(cached_snapshot["snapshot"]) if cached_snapshot else None
        cache_decision = self._cache_decision_for_source(source_config, mode=mode, cached=cached_snapshot)
        if cache_decision and cached_snapshot:
            state = self._state_from_cached_snapshot(
                source_name,
                source_config,
                cached_snapshot,
                mode=mode,
                reason=cache_decision["reason"],
                cache_age_seconds=cache_decision.get("cache_age_seconds"),
            )
            self._apply_source_state(
                source_name,
                source_config,
                cached_snapshot["operations"],
                cached_snapshot["schema_index"],
                state,
            )
            self.discovery_errors.pop(source_name, None)
            emit_app_event(
                self,
                event="discover_cache_loaded",
                source=source_name,
                data={
                    "provider_type": source_config.type,
                    "mode": mode,
                    "reason": cache_decision["reason"],
                    "snapshot_path": str(cached_snapshot["path"]),
                    "cache_age_seconds": cache_decision.get("cache_age_seconds"),
                    "operation_count": len(cached_snapshot["operations"]),
                },
            )
            return dict(state)

        if cache_decision and not cached_snapshot:
            state = {
                "source": source_name,
                "provider_type": source_config.type,
                "ok": False,
                "usable": False,
                "fallback": None,
                "mode": mode,
                "operation_count": 0,
                "schema_count": 0,
                "snapshot_path": None,
                "snapshot_fingerprint": None,
                "generated_at": None,
                "error": "discovery cache required but no snapshot available",
                "discovery_strategy": "cache",
                "cache_status": "miss",
                "cache_age_seconds": None,
            }
            self._apply_source_state(source_name, source_config, [], {}, state)
            self.discovery_errors[source_name] = state["error"]
            emit_app_event(
                self,
                event="discover_cache_miss",
                level="ERROR",
                source=source_name,
                data={"provider_type": source_config.type, "mode": mode, "reason": cache_decision["reason"]},
            )
            return dict(state)

        provider = self.get_provider(source_config)
        hook_payload = self.dispatch_hooks(
            "discovery.before",
            {"source_name": source_name, "source_config": source_config, "provider": provider, "mode": mode},
        )
        source_config = hook_payload.get("source_config", source_config)
        provider = hook_payload.get("provider", provider)
        emit_app_event(
            self,
            event="discover_start",
            source=source_name,
            data={"provider_type": source_config.type, "mode": mode},
        )

        previous_operations = list(self.source_operations.get(source_name, {}).values())
        previous_schema_index = self._schema_index_for_source(source_name)
        previous_state = dict(self.discovery_state.get(source_name, {}))

        try:
            operations = provider.discover(source_name, source_config, self)
            emit_app_event(
                self,
                event="discover_complete",
                source=source_name,
                data={"provider_type": source_config.type, "operation_count": len(operations), "mode": mode},
            )
            completed_payload = self.dispatch_hooks(
                "discovery.after",
                {
                    "source_name": source_name,
                    "source_config": source_config,
                    "provider": provider,
                    "operations": operations,
                    "mode": mode,
                },
            )
            operations = list(completed_payload.get("operations", operations))
            schema_index = self._capture_schema_index(source_name, source_config, provider, operations)
            snapshot_record = self.discovery_store.write_source_snapshot(
                source_name=source_name,
                provider_type=source_config.type,
                source_origin=str(self.origin_file_for(source_config)) if self.origin_file_for(source_config) else None,
                operations=operations,
                schema_index=schema_index,
                mode=mode,
            )
            baseline_snapshot = None
            baseline_defined = False
            if mode == "sync":
                baseline_defined = source_name in self.sync_baselines
                baseline_snapshot = self.sync_baselines.get(source_name)
            if baseline_snapshot is None and cached_snapshot and not baseline_defined:
                baseline_snapshot = cached_snapshot["snapshot"]
            drift = compare_discovery_snapshots(baseline_snapshot, snapshot_record["snapshot"])
            state = {
                "source": source_name,
                "provider_type": source_config.type,
                "ok": True,
                "usable": True,
                "fallback": None,
                "mode": mode,
                "operation_count": len(operations),
                "schema_count": len(schema_index),
                "snapshot_path": str(snapshot_record["path"]),
                "snapshot_fingerprint": snapshot_record["snapshot"].get("snapshot_fingerprint"),
                "generated_at": snapshot_record["snapshot"].get("generated_at"),
                "error": None,
                "discovery_strategy": "live",
                "cache_status": "refreshed",
                "cache_age_seconds": 0,
                "drift": drift,
            }
            self._apply_source_state(source_name, source_config, operations, schema_index, state)
            self.discovery_errors.pop(source_name, None)
            emit_app_event(
                self,
                event="discover_snapshot_written",
                source=source_name,
                data={
                    "provider_type": source_config.type,
                    "mode": mode,
                    "snapshot_path": str(snapshot_record["path"]),
                    "schema_count": len(schema_index),
                },
            )
            if drift.get("changed"):
                emit_app_event(
                    self,
                    event="drift_detected",
                    level="WARNING" if drift.get("severity") == "breaking" else "INFO",
                    source=source_name,
                    data={
                        "provider_type": source_config.type,
                        "severity": drift.get("severity"),
                        "status": drift.get("status"),
                        "summary": drift.get("summary"),
                    },
                )
            if mode == "sync":
                self.sync_baselines[source_name] = dict(snapshot_record["snapshot"])
            return dict(state)
        except Exception as exc:  # pragma: no cover - defensive path
            self.discovery_errors[source_name] = str(exc)
            self.dispatch_hooks(
                "discovery.error",
                {
                    "source_name": source_name,
                    "source_config": source_config,
                    "provider": provider,
                    "error": exc,
                    "mode": mode,
                },
            )
            emit_app_event(
                self,
                event="discover_failed",
                level="ERROR",
                source=source_name,
                data={"provider_type": source_config.type, "error": str(exc), "mode": mode},
            )

            fallback = None
            operations = []
            schema_index: Dict[str, Dict[str, Any]] = {}
            snapshot_path = None
            snapshot_fingerprint = None
            generated_at = None

            if previous_operations:
                fallback = "memory"
                operations = previous_operations
                schema_index = previous_schema_index
                snapshot_path = previous_state.get("snapshot_path")
                snapshot_fingerprint = previous_state.get("snapshot_fingerprint")
                generated_at = previous_state.get("generated_at")
            else:
                cached = self.discovery_store.load_source_snapshot(source_name)
                if cached:
                    fallback = "cache"
                    operations = cached["operations"]
                    schema_index = cached["schema_index"]
                    snapshot_path = str(cached["path"])
                    snapshot_fingerprint = cached["snapshot"].get("snapshot_fingerprint")
                    generated_at = cached["snapshot"].get("generated_at")

            state = {
                "source": source_name,
                "provider_type": source_config.type,
                "ok": False,
                "usable": bool(operations),
                "fallback": fallback,
                "mode": mode,
                "operation_count": len(operations),
                "schema_count": len(schema_index),
                "snapshot_path": snapshot_path,
                "snapshot_fingerprint": snapshot_fingerprint,
                "generated_at": generated_at,
                "error": str(exc),
                "discovery_strategy": "fallback" if fallback else "live",
                "cache_status": fallback or "miss",
                "cache_age_seconds": _snapshot_age_seconds(generated_at),
                "drift": None,
            }
            self._apply_source_state(source_name, source_config, operations, schema_index, state)
            if fallback:
                emit_app_event(
                    self,
                    event="discover_fallback_loaded",
                    level="WARNING",
                    source=source_name,
                    data={
                        "provider_type": source_config.type,
                        "mode": mode,
                        "fallback": fallback,
                        "operation_count": len(operations),
                        "snapshot_path": snapshot_path,
                    },
                )
            return dict(state)

    def _cache_decision_for_source(
        self,
        source_config: SourceConfig,
        *,
        mode: str,
        cached: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if mode == "help":
            if cached:
                return {"reason": "help_cached_snapshot"}
            return None
        discovery_mode = str(source_config.discovery.mode or "manual").lower()
        if mode == "sync":
            return None
        if discovery_mode == "cache_only":
            return {"reason": "cache_only"}
        if discovery_mode != "live":
            return None
        ttl = source_config.discovery.cache_ttl
        if ttl is None or ttl < 0 or not cached:
            return None
        cache_age_seconds = _snapshot_age_seconds(cached["snapshot"].get("generated_at"))
        if cache_age_seconds is None:
            return None
        if cache_age_seconds <= ttl:
            return {"reason": "cache_ttl", "cache_age_seconds": cache_age_seconds}
        return None

    def _state_from_cached_snapshot(
        self,
        source_name: str,
        source_config: SourceConfig,
        cached: Dict[str, Any],
        *,
        mode: str,
        reason: str,
        cache_age_seconds: Optional[int],
    ) -> Dict[str, Any]:
        snapshot = cached["snapshot"]
        operations = cached["operations"]
        schema_index = cached["schema_index"]
        return {
            "source": source_name,
            "provider_type": source_config.type,
            "ok": True,
            "usable": True,
            "fallback": None,
            "mode": mode,
            "operation_count": len(operations),
            "schema_count": len(schema_index),
            "snapshot_path": str(cached["path"]),
            "snapshot_fingerprint": snapshot.get("snapshot_fingerprint"),
            "generated_at": snapshot.get("generated_at"),
            "error": None,
            "discovery_strategy": "cache",
            "cache_status": reason,
            "cache_age_seconds": cache_age_seconds,
        }

    def _apply_source_state(
        self,
        source_name: str,
        source_config: SourceConfig,
        operations: List[OperationDescriptor],
        schema_index: Dict[str, Dict[str, Any]],
        state: Dict[str, Any],
    ) -> None:
        self.source_operations[source_name] = {operation.id: operation for operation in operations}
        self.schema_cache[source_name] = {}
        self.schema_provenance_index[source_name] = {}

        for operation in operations:
            schema_record = dict(schema_index.get(operation.id) or {})
            schema = dict(schema_record.get("input_schema") or operation.input_schema or {})
            provenance = schema_record.get("provenance") or self._default_schema_provenance(source_config, operation)
            if schema:
                operation.input_schema = schema
            self._remember_schema_info(source_name, operation.id, schema, provenance)

        self.discovery_state[source_name] = dict(state)

    def _capture_schema_index(
        self,
        source_name: str,
        source_config: SourceConfig,
        provider: Any,
        operations: List[OperationDescriptor],
    ) -> Dict[str, Dict[str, Any]]:
        schema_index: Dict[str, Dict[str, Any]] = {}
        for operation in operations:
            schema = dict(operation.input_schema or {})
            provenance: Optional[Dict[str, Any]] = None
            try:
                schema_info = provider.get_schema(source_name, source_config, operation.id, self)
            except Exception as exc:  # pragma: no cover - defensive path
                emit_app_event(
                    self,
                    event="schema_capture_failed",
                    level="WARNING",
                    source=source_name,
                    operation_id=operation.id,
                    data={"provider_type": source_config.type, "error": str(exc)},
                )
                schema_info = None

            if schema_info:
                schema = dict(schema_info[0] or schema or {})
                provenance = dict(schema_info[1] or {})
            elif schema:
                provenance = self._default_schema_provenance(source_config, operation)

            if not schema and not provenance:
                continue
            if schema:
                operation.input_schema = schema
            schema_index[operation.id] = {
                "input_schema": schema,
                "provenance": provenance,
            }
        return schema_index

    def _schema_index_for_source(self, source_name: str) -> Dict[str, Dict[str, Any]]:
        schema_index: Dict[str, Dict[str, Any]] = {}
        for operation_id, operation in self.source_operations.get(source_name, {}).items():
            schema = dict(self.schema_cache.get(source_name, {}).get(operation_id) or operation.input_schema or {})
            provenance = self.schema_provenance_index.get(source_name, {}).get(operation_id)
            if not schema and not provenance:
                continue
            schema_index[operation_id] = {
                "input_schema": schema,
                "provenance": dict(provenance) if provenance else None,
            }
        return schema_index

    def _schema_info_from_memory(
        self,
        source_name: str,
        operation_id: str,
    ) -> Optional[tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
        schema = self.schema_cache.get(source_name, {}).get(operation_id)
        provenance = self.schema_provenance_index.get(source_name, {}).get(operation_id)
        if schema is None and provenance is None:
            return None

        resolved_schema = dict(schema or {})
        if not resolved_schema:
            operation = self.source_operations.get(source_name, {}).get(operation_id)
            resolved_schema = dict(operation.input_schema or {}) if operation else {}
        return resolved_schema, dict(provenance) if provenance else None

    def _remember_schema_info(
        self,
        source_name: str,
        operation_id: str,
        schema: Dict[str, Any],
        provenance: Optional[Dict[str, Any]],
    ) -> None:
        normalized_schema = dict(schema or {})
        normalized_provenance = dict(provenance or {})
        if normalized_provenance and normalized_provenance.get("fetched_at") is None:
            normalized_provenance["fetched_at"] = utc_now_iso()
        self.schema_cache.setdefault(source_name, {})[operation_id] = normalized_schema
        if normalized_provenance:
            self.schema_provenance_index.setdefault(source_name, {})[operation_id] = normalized_provenance

    def _default_schema_provenance(
        self,
        source_config: SourceConfig,
        operation: OperationDescriptor,
    ) -> Dict[str, Any]:
        if source_config.type == "openapi" and source_config.spec:
            spec_origin = source_config.spec.get("path") or source_config.spec.get("file") or source_config.spec.get("url")
            if spec_origin and source_config.spec.get("path"):
                spec_origin = str(self.resolve_path(str(spec_origin), owner=source_config))
            return {
                "strategy": "authoritative",
                "origin": spec_origin or "openapi",
                "confidence": 1.0,
                "fetched_at": utc_now_iso(),
            }
        if source_config.type == "graphql" and source_config.schema_config:
            schema_origin = (
                source_config.schema_config.get("path")
                or source_config.schema_config.get("file")
                or source_config.schema_config.get("url")
                or source_config.endpoint
                or source_config.base_url
                or "graphql"
            )
            if source_config.schema_config.get("path") or source_config.schema_config.get("file"):
                schema_origin = str(self.resolve_path(str(schema_origin), owner=source_config))
            return {
                "strategy": "authoritative",
                "origin": schema_origin,
                "confidence": 1.0,
                "fetched_at": utc_now_iso(),
            }
        manifest = source_config.discovery.manifest
        if operation.provider_config.get("discovered_via") == "mcp_bridge":
            return {
                "strategy": "probed",
                "origin": operation.provider_config.get("discovered_origin", "mcp"),
                "confidence": 0.95,
                "fetched_at": utc_now_iso(),
            }
        if operation.id in source_config.operations:
            return {
                "strategy": "manual",
                "origin": "source.operations",
                "confidence": 1.0,
                "fetched_at": utc_now_iso(),
            }
        if manifest:
            return {
                "strategy": "declared",
                "origin": str(self.resolve_path(manifest, owner=source_config)),
                "confidence": 0.9,
                "fetched_at": utc_now_iso(),
            }
        return {
            "strategy": source_config.discovery.schema_strategy or "declared",
            "origin": source_config.type,
            "confidence": 0.6,
            "fetched_at": utc_now_iso(),
        }


def _snapshot_age_seconds(raw_timestamp: Optional[str]) -> Optional[int]:
    if not raw_timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw_timestamp))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(int(age.total_seconds()), 0)


def _aggregate_drift(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = {
        "status": "none",
        "severity": "none",
        "source_count": len(items),
        "changed_sources": 0,
        "breaking_sources": 0,
        "additive_sources": 0,
        "compatible_sources": 0,
    }
    for item in items:
        drift = item.get("drift") or {}
        if not drift.get("changed"):
            continue
        summary["status"] = "changed"
        summary["changed_sources"] += 1
        severity = str(drift.get("severity") or "none")
        summary["severity"] = _max_summary_severity(summary["severity"], severity)
        if severity == "breaking":
            summary["breaking_sources"] += 1
        elif severity == "additive":
            summary["additive_sources"] += 1
        elif severity == "compatible":
            summary["compatible_sources"] += 1
    return summary


def _max_summary_severity(current: str, new: str) -> str:
    rank = {"none": 0, "compatible": 1, "additive": 2, "breaking": 3}
    return new if rank.get(new, 0) > rank.get(current, 0) else current


def _more_restrictive_action(current: Any, new: Any) -> str:
    rank = {
        "ignore": 0,
        "auto_accept": 0,
        "accept": 0,
        "warn": 1,
        "warning": 1,
        "warn_and_keep_cached": 1,
        "require_manual_review": 2,
        "freeze_mount": 3,
        "disable_mount": 3,
    }
    current_value = str(current or "warn").strip().lower()
    new_value = str(new or "warn").strip().lower()
    return new_value if rank.get(new_value, 0) > rank.get(current_value, 0) else current_value


def _drift_policy_key(severity: Any) -> str:
    normalized = str(severity or "compatible").strip().lower()
    if normalized not in {"compatible", "additive", "breaking"}:
        normalized = "compatible"
    return f"on_{normalized}_change"


def _is_accepting_drift_action(action: Any) -> bool:
    return str(action or "").strip().lower() in {"ignore", "auto_accept", "accept"}


def _merge_drift_changes(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[tuple[str, str], Dict[str, Any]] = {}
    for item in list(existing) + list(incoming):
        if not isinstance(item, dict):
            continue
        key = (str(item.get("change_type") or ""), str(item.get("operation_id") or ""))
        current = merged.get(key)
        if current is None:
            merged[key] = dict(item)
            continue
        current["reasons"] = sorted(set(list(current.get("reasons") or []) + list(item.get("reasons") or [])))
        current["severity"] = _max_summary_severity(str(current.get("severity") or "none"), str(item.get("severity") or "none"))
    return list(merged.values())


def build_app(
    config_path: Optional[str] = None,
    profile: Optional[str] = None,
    *,
    compile_mode: str = "full",
    target_source_names: Optional[List[str]] = None,
    load_drift_governance: bool = True,
) -> CTSApp:
    return CTSApp(
        load_config(config_path, target_source_names=target_source_names),
        active_profile=profile,
        explicit_config_path=config_path,
        requested_profile=profile,
        compile_mode=compile_mode,
        target_source_names=target_source_names,
        load_drift_governance=load_drift_governance,
    )


def build_generated_mount(mount: MountConfig, source_config: SourceConfig, operation: OperationDescriptor) -> MountRecord:
    command_prefix = list(mount.command.under or mount.command.path)
    if not command_prefix:
        command_prefix = tokenize_identifier(mount.id)
    operation_tokens = tokenize_identifier(operation.id)
    if command_prefix and operation_tokens and command_prefix[-1] == operation_tokens[0]:
        operation_tokens = operation_tokens[1:]
    command_path = command_prefix + operation_tokens

    stable_name = operation.stable_name or f"{mount.source}.{operation.id}".replace("_", ".")
    return MountRecord(
        mount_id=f"{mount.id}.{operation.id}",
        source_name=mount.source,
        provider_type=source_config.type,
        operation=operation,
        command_path=command_path,
        aliases=[],
        stable_name=stable_name,
        summary=operation.title,
        description=operation.description,
        source_config=source_config,
        mount_config=mount,
        generated=True,
        generated_from=mount.id,
    )


def build_mount_record(
    mount: MountConfig,
    source_config: SourceConfig,
    operation: OperationDescriptor,
    generated: bool,
) -> MountRecord:
    command_path = list(mount.command.path or [])
    if not command_path:
        command_path = list(mount.command.under or []) + tokenize_identifier(operation.id)
    if not command_path:
        command_path = tokenize_identifier(mount.id)

    stable_name = mount.machine.stable_name or operation.stable_name or f"{mount.source}.{operation.id}".replace("_", ".")

    return MountRecord(
        mount_id=mount.id,
        source_name=mount.source,
        provider_type=source_config.type,
        operation=operation,
        command_path=command_path,
        aliases=[list(alias) for alias in mount.command.aliases],
        stable_name=stable_name,
        summary=mount.help.summary or operation.title,
        description=mount.help.description or operation.description,
        source_config=source_config,
        mount_config=mount,
        generated=generated,
    )


def synthesize_operation(mount: MountConfig, source_config: SourceConfig, operation_id: str) -> OperationDescriptor:
    return OperationDescriptor(
        id=operation_id,
        source=mount.source,
        provider_type=source_config.type,
        title=mount.help.summary or operation_id,
        stable_name=mount.machine.stable_name,
        description=mount.help.description,
        kind="action",
        risk=mount.policy.get("risk", "read"),
        input_schema=schema_from_mount_params(mount.params),
        examples=[{"cli": example} for example in mount.help.examples],
        supported_surfaces=list(mount.machine.expose_via or source_config.expose_to_surfaces),
    )


def schema_from_mount_params(params: Dict[str, ParamConfig]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in params.items():
        if param.type == "array":
            schema = {"type": "array", "items": {"type": "string"}}
        else:
            schema = {"type": normalize_schema_type(param.type)}
        if param.help:
            schema["description"] = param.help
        if param.default is not None:
            schema["default"] = param.default
        if param.enum:
            schema["enum"] = list(param.enum)
        if param.required:
            required.append(name)
        properties[name] = schema
    return {"type": "object", "properties": properties, "required": required}


def normalize_schema_type(param_type: str) -> str:
    mapping = {
        "str": "string",
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "number": "number",
        "float": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "object": "object",
        "array": "array",
    }
    return mapping.get(param_type, "string")


def tokenize_identifier(value: str) -> List[str]:
    parts = [segment for segment in re.split(r"[_./:\-]+", value) if segment]
    return [part.lower() for part in parts] or [value]


def operation_matches_select(operation: OperationDescriptor, select: Dict[str, Any]) -> bool:
    includes = list(select.get("include", []))
    excludes = list(select.get("exclude", []))
    tags = set(select.get("tags", []))

    haystacks = [operation.id, operation.stable_name or ""] + list(operation.tags)
    if includes and not any(any(fnmatch.fnmatch(item, pattern) for item in haystacks) for pattern in includes):
        return False
    if excludes and any(any(fnmatch.fnmatch(item, pattern) for item in haystacks) for pattern in excludes):
        return False
    if tags and not tags.intersection(set(operation.tags)):
        return False
    return True
