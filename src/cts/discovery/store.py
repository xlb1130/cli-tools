from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.models import OperationDescriptor


@dataclass
class DiscoveryPaths:
    cache_dir: Path
    state_dir: Path
    source_cache_dir: Path
    sync_report_dir: Path
    capability_snapshot_dir: Path
    drift_state_dir: Path


def resolve_discovery_paths(app: Any) -> DiscoveryPaths:
    cache_dir = _resolve_optional_path(app, app.config.app.cache_dir, Path("~/.cache/cts").expanduser())
    state_dir = _resolve_optional_path(app, app.config.app.state_dir, Path("~/.local/share/cts").expanduser())
    return DiscoveryPaths(
        cache_dir=cache_dir,
        state_dir=state_dir,
        source_cache_dir=(cache_dir / "discovery").resolve(),
        sync_report_dir=(state_dir / "imports").resolve(),
        capability_snapshot_dir=(state_dir / "capabilities").resolve(),
        drift_state_dir=(state_dir / "drift").resolve(),
    )


class DiscoveryStore:
    version = 1

    def __init__(self, app: Any) -> None:
        self.app = app
        self.paths = resolve_discovery_paths(app)

    def source_snapshot_path(self, source_name: str) -> Path:
        return self.paths.source_cache_dir / f"{_safe_name(source_name)}.json"

    def load_source_snapshot(self, source_name: str) -> Optional[Dict[str, Any]]:
        path = self.source_snapshot_path(source_name)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        operations: List[OperationDescriptor] = []
        schema_index = payload.get("schema_index") or {}
        for raw in payload.get("operations", []):
            try:
                operation = OperationDescriptor.model_validate(raw)
            except Exception:
                continue
            schema_record = schema_index.get(operation.id) or {}
            if schema_record.get("input_schema"):
                operation.input_schema = dict(schema_record["input_schema"])
            operations.append(operation)

        return {
            "path": path,
            "snapshot": payload,
            "operations": operations,
            "schema_index": schema_index,
        }

    def write_source_snapshot(
        self,
        *,
        source_name: str,
        provider_type: str,
        source_origin: Optional[str],
        operations: List[OperationDescriptor],
        schema_index: Dict[str, Dict[str, Any]],
        mode: str,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        operation_payloads = [operation.model_dump(mode="json") for operation in operations]
        operation_fingerprints = {
            operation["id"]: _fingerprint(operation) for operation in operation_payloads if isinstance(operation, dict)
        }
        payload = {
            "version": self.version,
            "kind": "discovery_snapshot",
            "source": source_name,
            "provider_type": provider_type,
            "source_origin": source_origin,
            "mode": mode,
            "generated_at": now,
            "operation_count": len(operation_payloads),
            "schema_count": len(schema_index),
            "operations": operation_payloads,
            "schema_index": schema_index,
            "operation_fingerprints": operation_fingerprints,
            "schema_fingerprints": {
                operation_id: _fingerprint(record.get("input_schema") or {})
                for operation_id, record in schema_index.items()
            },
        }
        payload["snapshot_fingerprint"] = _fingerprint(
            {
                "source": source_name,
                "provider_type": provider_type,
                "operations": operation_payloads,
                "schema_index": schema_index,
            }
        )
        path = self.source_snapshot_path(source_name)
        self._write_json(path, payload)
        return {"path": path, "snapshot": payload}

    def write_sync_report(self, report: Dict[str, Any], *, source_name: Optional[str] = None) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = f"-{_safe_name(source_name)}" if source_name else ""
        path = self.paths.sync_report_dir / f"sync-{stamp}{suffix}.json"
        latest = self.paths.sync_report_dir / ("latest-" + _safe_name(source_name) + ".json" if source_name else "latest.json")
        self._write_json(path, report)
        self._write_json(latest, report)
        return path

    def latest_sync_report_path(self, source_name: Optional[str] = None) -> Path:
        if source_name:
            return self.paths.sync_report_dir / f"latest-{_safe_name(source_name)}.json"
        return self.paths.sync_report_dir / "latest.json"

    def load_latest_sync_report(self, source_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        path = self.latest_sync_report_path(source_name)
        if not path.exists():
            if source_name:
                return self.load_latest_sync_report(None)
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def write_capability_snapshot(self, snapshot: Dict[str, Any], *, source_name: Optional[str] = None) -> Path:
        suffix = f"-{_safe_name(source_name)}" if source_name else ""
        path = self.paths.capability_snapshot_dir / f"capabilities{suffix}.json"
        self._write_json(path, snapshot)
        return path

    def drift_reconciliations_path(self) -> Path:
        return self.paths.drift_state_dir / "reconciliations.json"

    def load_drift_reconciliations(self) -> Dict[str, Any]:
        path = self.drift_reconciliations_path()
        if not path.exists():
            return {"version": 1, "items": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "items": []}
        if not isinstance(payload, dict):
            return {"version": 1, "items": []}
        items = payload.get("items")
        if not isinstance(items, list):
            payload["items"] = []
        return payload

    def upsert_drift_reconciliation(
        self,
        *,
        source_name: str,
        report_generated_at: str,
        action: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = self.load_drift_reconciliations()
        items = [item for item in payload.get("items", []) if isinstance(item, dict)]
        entry = {
            "source": source_name,
            "report_generated_at": report_generated_at,
            "action": action,
            "updated_at": _utc_now_iso(),
            "metadata": dict(metadata or {}),
        }
        replaced = False
        for index, item in enumerate(items):
            if item.get("source") == source_name and item.get("report_generated_at") == report_generated_at:
                items[index] = entry
                replaced = True
                break
        if not replaced:
            items.append(entry)
        payload["version"] = 1
        payload["items"] = items
        self._write_json(self.drift_reconciliations_path(), payload)
        return entry

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_optional_path(app: Any, raw_path: Optional[str], default: Path) -> Path:
    if raw_path is None:
        return default.expanduser().resolve()
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (app.primary_config_dir / candidate).resolve()


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return normalized or "default"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
