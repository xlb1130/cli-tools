from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


INDEX_VERSION = 1


def resolve_command_index_path(explicit_config_path: Optional[str]) -> Path:
    base_dir = Path(os.environ.get("CTS_CLI_INDEX_DIR") or "~/.local/share/cts/cli-index").expanduser().resolve()
    fingerprint_source = explicit_config_path or str(Path.cwd().resolve())
    key = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16]
    return base_dir / f"{key}.json"


def load_command_index(explicit_config_path: Optional[str]):
    status = inspect_command_index(explicit_config_path)
    if not status.get("ok"):
        return None

    from cts.cli.static_catalog import deserialize_static_help_catalog

    catalog_payload = status.get("payload", {}).get("catalog")
    if not isinstance(catalog_payload, dict):
        return None
    try:
        return deserialize_static_help_catalog(catalog_payload)
    except Exception:
        return None


def write_command_index(explicit_config_path: Optional[str], loaded, catalog) -> Path:
    from cts.cli.static_catalog import serialize_static_help_catalog, static_catalog_dependency_paths

    dependencies = static_catalog_dependency_paths(loaded)
    payload = {
        "version": INDEX_VERSION,
        "kind": "cts_cli_command_index",
        "config_path": str(explicit_config_path) if explicit_config_path else None,
        "dependencies": [_snapshot_path(path) for path in dependencies],
        "catalog": serialize_static_help_catalog(catalog),
    }
    path = resolve_command_index_path(explicit_config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def rebuild_command_index(explicit_config_path: Optional[str]) -> Dict[str, Any]:
    from cts.cli.static_catalog import build_static_help_catalog
    from cts.config.loader import load_raw_config

    loaded = load_raw_config(explicit_config_path)
    catalog = build_static_help_catalog(loaded)
    index_path = write_command_index(explicit_config_path, loaded, catalog)
    return {
        "index_path": str(index_path),
        "config_path": str(explicit_config_path) if explicit_config_path else None,
        "root_paths": [str(path) for path in loaded.root_paths],
        "loaded_paths": [str(path) for path in loaded.paths],
        "mount_count": len(getattr(catalog, "_path_index", {})),
        "group_count": len(getattr(catalog, "_group_help", {})),
    }


def inspect_command_index(explicit_config_path: Optional[str]) -> Dict[str, Any]:
    path = resolve_command_index_path(explicit_config_path)
    status: Dict[str, Any] = {
        "path": str(path),
        "config_path": str(explicit_config_path) if explicit_config_path else None,
        "exists": path.exists(),
        "ok": False,
        "reason": "missing",
        "dependencies": [],
        "payload": None,
    }
    if not path.exists():
        return status

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        status["reason"] = "invalid_json"
        status["error"] = str(exc)
        return status

    status["payload"] = payload
    if not isinstance(payload, dict):
        status["reason"] = "invalid_payload"
        return status
    if payload.get("version") != INDEX_VERSION:
        status["reason"] = "version_mismatch"
        status["version"] = payload.get("version")
        return status

    dependency_statuses = _dependency_statuses(payload.get("dependencies") or [])
    status["dependencies"] = dependency_statuses
    mismatches = [item for item in dependency_statuses if not item.get("matches")]
    if mismatches:
        status["reason"] = "dependencies_changed"
        status["changed_dependencies"] = mismatches
        return status

    catalog_payload = payload.get("catalog")
    if not isinstance(catalog_payload, dict):
        status["reason"] = "missing_catalog"
        return status

    status["ok"] = True
    status["reason"] = "ready"
    status["mount_count"] = len(catalog_payload.get("mounts") or [])
    status["group_count"] = len(catalog_payload.get("group_help") or [])
    return status


def _snapshot_path(path: Path) -> Dict[str, Any]:
    resolved = path.expanduser().resolve()
    exists = resolved.exists()
    stat = resolved.stat() if exists else None
    return {
        "path": str(resolved),
        "exists": exists,
        "mtime_ns": getattr(stat, "st_mtime_ns", None),
        "size": getattr(stat, "st_size", None),
    }


def _dependencies_match(items: List[Dict[str, Any]]) -> bool:
    return all(item.get("matches") for item in _dependency_statuses(items))


def _dependency_statuses(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    statuses: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            statuses.append({"matches": False, "reason": "invalid_entry", "path": None})
            continue
        raw_path = item.get("path")
        if not raw_path:
            statuses.append({"matches": False, "reason": "missing_path", "path": None})
            continue
        path = Path(str(raw_path)).expanduser().resolve()
        exists = path.exists()
        status = {
            "path": str(path),
            "expected_exists": bool(item.get("exists")),
            "actual_exists": exists,
            "matches": True,
            "reason": "ok",
        }
        if exists != bool(item.get("exists")):
            status["matches"] = False
            status["reason"] = "exists_changed"
            statuses.append(status)
            continue
        if not exists:
            statuses.append(status)
            continue
        stat = path.stat()
        if int(item.get("mtime_ns") or -1) != int(stat.st_mtime_ns):
            status["matches"] = False
            status["reason"] = "mtime_changed"
        elif int(item.get("size") or -1) != int(stat.st_size):
            status["matches"] = False
            status["reason"] = "size_changed"
        status["expected_mtime_ns"] = item.get("mtime_ns")
        status["actual_mtime_ns"] = stat.st_mtime_ns
        status["expected_size"] = item.get("size")
        status["actual_size"] = stat.st_size
        statuses.append(status)
    return statuses
