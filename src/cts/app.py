from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.app_drift import (
    snapshot_age_seconds as _snapshot_age_seconds,
)
from cts.app_discovery import (
    apply_source_state,
    cache_decision_for_source,
    capture_schema_index,
    default_schema_provenance,
    discover_source,
    remember_schema_info,
    schema_index_for_source,
    schema_info_from_memory,
    state_from_cached_snapshot,
)
from cts.app_governance import (
    annotate_drift_report_path,
    apply_drift_reconciliations,
    build_capability_snapshot,
    build_drift_governance,
    ensure_drift_governance_loaded,
    load_drift_governance,
    resolve_drift_action,
    sync,
)
from cts.app_mounts import (
    build_generated_mount,
    build_mount_record,
    operation_matches_select,
    synthesize_operation,
    tokenize_identifier,
)
from cts.auth import AuthManager
from cts.catalog import Catalog
from cts.config.loader import LoadedConfig, load_config
from cts.config.models import MountConfig, SourceConfig
from cts.discovery import DiscoveryStore
from cts.execution.errors import PolicyError
from cts.execution.logging import emit_app_event, utc_now_iso
from cts.models import MountRecord, OperationDescriptor
from cts.plugins import PluginManager
from cts.providers.registry import ProviderRegistry
from cts.secrets import SecretManager


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
        return sync(self, source_name=source_name)

    def build_capability_snapshot(self) -> Dict[str, Any]:
        return build_capability_snapshot(self)

    def _load_drift_governance(self) -> None:
        load_drift_governance(self)

    def _ensure_drift_governance_loaded(self) -> None:
        ensure_drift_governance_loaded(self)

    def _annotate_drift_report_path(self, report_path: str) -> None:
        annotate_drift_report_path(self, report_path)

    def _build_drift_governance(
        self,
        items: List[Dict[str, Any]],
        *,
        report_generated_at: Optional[str] = None,
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return build_drift_governance(self, items, report_generated_at=report_generated_at)

    def _affected_mounts_for_change(self, source_name: str, change: Dict[str, Any]) -> List[MountRecord]:
        from cts.app_governance import affected_mounts_for_change

        return affected_mounts_for_change(self, source_name, change)

    def _affected_mount_ids_for_change(self, source_name: str, change: Dict[str, Any]) -> List[str]:
        from cts.app_governance import affected_mount_ids_for_change

        return affected_mount_ids_for_change(self, source_name, change)

    def _resolve_drift_action(
        self,
        mount: Optional[MountRecord],
        severity: str,
        *,
        source_name: Optional[str] = None,
    ) -> str:
        return resolve_drift_action(self, mount, severity, source_name=source_name)

    def _apply_drift_reconciliations(self) -> None:
        apply_drift_reconciliations(self)

    def _discover_source(self, source_name: str, source_config: SourceConfig, *, mode: str) -> Dict[str, Any]:
        return discover_source(self, source_name, source_config, mode=mode)

    def _cache_decision_for_source(
        self,
        source_config: SourceConfig,
        *,
        mode: str,
        cached: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        return cache_decision_for_source(source_config, mode=mode, cached=cached)

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
        return state_from_cached_snapshot(source_name, source_config, cached, mode=mode, reason=reason, cache_age_seconds=cache_age_seconds)

    def _apply_source_state(
        self,
        source_name: str,
        source_config: SourceConfig,
        operations: List[OperationDescriptor],
        schema_index: Dict[str, Dict[str, Any]],
        state: Dict[str, Any],
    ) -> None:
        apply_source_state(self, source_name, source_config, operations, schema_index, state)

    def _capture_schema_index(
        self,
        source_name: str,
        source_config: SourceConfig,
        provider: Any,
        operations: List[OperationDescriptor],
    ) -> Dict[str, Dict[str, Any]]:
        return capture_schema_index(self, source_name, source_config, provider, operations)

    def _schema_index_for_source(self, source_name: str) -> Dict[str, Dict[str, Any]]:
        return schema_index_for_source(self, source_name)

    def _schema_info_from_memory(
        self,
        source_name: str,
        operation_id: str,
    ) -> Optional[tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
        return schema_info_from_memory(self, source_name, operation_id)

    def _remember_schema_info(
        self,
        source_name: str,
        operation_id: str,
        schema: Dict[str, Any],
        provenance: Optional[Dict[str, Any]],
    ) -> None:
        remember_schema_info(self, source_name, operation_id, schema, provenance)

    def _default_schema_provenance(
        self,
        source_config: SourceConfig,
        operation: OperationDescriptor,
    ) -> Dict[str, Any]:
        return default_schema_provenance(self, source_config, operation)


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
