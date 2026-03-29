from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


DEFAULT_REDACT_FIELDS = {"authorization", "x-api-key", "token", "password", "secret", "api_key"}


@dataclass
class RuntimePaths:
    app_log: Path
    audit_log: Path
    history_db: Path


def resolve_runtime_paths(app: Any) -> RuntimePaths:
    log_dir = _resolve_optional_path(app, app.config.app.log_dir, Path("~/.local/state/cts/logs").expanduser())
    state_dir = _resolve_optional_path(app, app.config.app.state_dir, Path("~/.local/share/cts").expanduser())

    sinks = app.config.logging.sinks or {}
    app_log = _resolve_optional_path(app, sinks.get("app"), log_dir / "app.jsonl")
    audit_log = _resolve_optional_path(app, sinks.get("audit"), log_dir / "audit.jsonl")
    history_db = _resolve_optional_path(app, sinks.get("history"), state_dir / "history.db")
    return RuntimePaths(app_log=app_log, audit_log=audit_log, history_db=history_db)


def emit_app_event(
    app: Any,
    *,
    event: str,
    level: str = "INFO",
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    surface: Optional[str] = "cli",
    source: Optional[str] = None,
    mount_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    message: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        paths = resolve_runtime_paths(app)
        payload = _build_event(
            app,
            level=level,
            event=event,
            run_id=run_id,
            trace_id=trace_id,
            surface=surface,
            source=source,
            mount_id=mount_id,
            operation_id=operation_id,
            message=message,
            data=data,
        )
        _append_jsonl(paths.app_log, payload)
    except Exception:
        return None


def emit_audit_event(
    app: Any,
    *,
    event: str,
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    surface: Optional[str] = "cli",
    source: Optional[str] = None,
    mount_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    message: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        paths = resolve_runtime_paths(app)
        payload = _build_event(
            app,
            level="AUDIT",
            event=event,
            run_id=run_id,
            trace_id=trace_id,
            surface=surface,
            source=source,
            mount_id=mount_id,
            operation_id=operation_id,
            message=message,
            data=data,
        )
        _append_jsonl(paths.audit_log, payload)
    except Exception:
        return None


def record_run(app: Any, record: Dict[str, Any]) -> None:
    try:
        paths = resolve_runtime_paths(app)
        paths.history_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(paths.history_db) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                  run_id TEXT PRIMARY KEY,
                  trace_id TEXT,
                  ts_start TEXT,
                  ts_end TEXT,
                  surface TEXT,
                  mode TEXT,
                  ok INTEGER,
                  exit_code INTEGER,
                  profile TEXT,
                  mount_id TEXT,
                  stable_name TEXT,
                  source TEXT,
                  operation_id TEXT,
                  provider_type TEXT,
                  summary TEXT,
                  error_type TEXT,
                  error_code TEXT,
                  metadata_json TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                  run_id, trace_id, ts_start, ts_end, surface, mode, ok, exit_code, profile,
                  mount_id, stable_name, source, operation_id, provider_type, summary,
                  error_type, error_code, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("run_id"),
                    record.get("trace_id"),
                    record.get("ts_start"),
                    record.get("ts_end"),
                    record.get("surface"),
                    record.get("mode"),
                    1 if record.get("ok") else 0,
                    record.get("exit_code"),
                    record.get("profile"),
                    record.get("mount_id"),
                    record.get("stable_name"),
                    record.get("source"),
                    record.get("operation_id"),
                    record.get("provider_type"),
                    record.get("summary"),
                    record.get("error_type"),
                    record.get("error_code"),
                    json.dumps(_redact_value(app, record.get("metadata", {})), ensure_ascii=False),
                ),
            )
    except Exception:
        return None


def list_runs(app: Any, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        paths = resolve_runtime_paths(app)
    except Exception:
        return []
    if not paths.history_db.exists():
        return []
    try:
        with sqlite3.connect(paths.history_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT run_id, trace_id, ts_start, ts_end, surface, mode, ok, exit_code, profile,
                       mount_id, stable_name, source, operation_id, provider_type, summary,
                       error_type, error_code
                FROM runs
                ORDER BY ts_start DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except Exception:
        return []
    return [_row_to_dict(row) for row in rows]


def get_run(app: Any, run_id: str) -> Optional[Dict[str, Any]]:
    try:
        paths = resolve_runtime_paths(app)
    except Exception:
        return None
    if not paths.history_db.exists():
        return None
    try:
        with sqlite3.connect(paths.history_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    payload = _row_to_dict(row)
    payload["metadata"] = json.loads(row["metadata_json"] or "{}")
    payload.pop("metadata_json", None)
    return payload


def list_app_events(
    app: Any,
    *,
    limit: int = 50,
    events: Optional[Sequence[str]] = None,
    event_prefixes: Optional[Sequence[str]] = None,
    plugin: Optional[str] = None,
    hook_event: Optional[str] = None,
    level: Optional[str] = None,
    mount_id: Optional[str] = None,
    source: Optional[str] = None,
    before_ts: Optional[str] = None,
) -> List[Dict[str, Any]]:
    try:
        paths = resolve_runtime_paths(app)
    except Exception:
        return []
    if not paths.app_log.exists():
        return []

    normalized_events = {str(item) for item in (events or []) if str(item).strip()}
    normalized_prefixes = [str(item) for item in (event_prefixes or []) if str(item).strip()]
    results: List[Dict[str, Any]] = []

    try:
        lines = paths.app_log.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    for raw in reversed(lines):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        event_name = str(payload.get("event") or "")
        if normalized_events and event_name not in normalized_events:
            continue
        if normalized_prefixes and not any(event_name.startswith(prefix) for prefix in normalized_prefixes):
            continue
        if before_ts and str(payload.get("ts") or "") >= str(before_ts):
            continue
        payload_level = str(payload.get("level") or "").upper()
        if level and payload_level != str(level).upper():
            continue
        if mount_id and str(payload.get("mount_id") or "") != str(mount_id):
            continue
        if source and str(payload.get("source") or "") != str(source):
            continue
        data = payload.get("data") or {}
        if plugin and str(data.get("plugin") or "") != str(plugin):
            continue
        if hook_event and str(data.get("hook_event") or "") != str(hook_event):
            continue
        results.append(payload)
        if len(results) >= limit:
            break
    return results


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    data = result.get("data")
    if isinstance(data, dict):
        data_keys = sorted(data.keys())[:10]
    else:
        data_keys = None
    return {
        "ok": result.get("ok"),
        "status_code": result.get("status_code"),
        "data_keys": data_keys,
        "has_text": bool(result.get("text")),
        "has_stderr": bool(result.get("stderr")),
    }


def redact_value(app: Any, value: Any) -> Any:
    return _redact_value(app, value)


def _build_event(
    app: Any,
    *,
    level: str,
    event: str,
    run_id: Optional[str],
    trace_id: Optional[str],
    surface: Optional[str],
    source: Optional[str],
    mount_id: Optional[str],
    operation_id: Optional[str],
    message: Optional[str],
    data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "ts": utc_now_iso(),
        "level": level,
        "event": event,
        "run_id": run_id,
        "trace_id": trace_id,
        "surface": surface,
        "profile": getattr(app, "active_profile", None),
        "source": source,
        "mount_id": mount_id,
        "operation_id": operation_id,
        "message": message,
        "data": _redact_value(app, data or {}),
    }


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _redact_value(app: Any, value: Any) -> Any:
    extra_fields = set(app.config.logging.redact.get("fields", [])) | set(app.config.logging.redact.get("headers", []))
    redact_fields = {field.lower() for field in DEFAULT_REDACT_FIELDS | extra_fields}

    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in redact_fields:
                redacted[key] = "***"
            else:
                redacted[key] = _redact_value(app, item)
        return redacted
    if isinstance(value, list):
        return [_redact_value(app, item) for item in value]
    return value


def _resolve_optional_path(app: Any, raw_path: Optional[str], default: Path) -> Path:
    if raw_path is None:
        return default.expanduser().resolve()
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (app.primary_config_dir / candidate).resolve()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    payload = dict(row)
    if "ok" in payload:
        payload["ok"] = bool(payload["ok"])
    return payload
