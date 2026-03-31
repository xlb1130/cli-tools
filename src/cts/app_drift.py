from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def snapshot_age_seconds(raw_timestamp: Optional[str]) -> Optional[int]:
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


def aggregate_drift(items: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        summary["severity"] = max_summary_severity(summary["severity"], severity)
        if severity == "breaking":
            summary["breaking_sources"] += 1
        elif severity == "additive":
            summary["additive_sources"] += 1
        elif severity == "compatible":
            summary["compatible_sources"] += 1
    return summary


def max_summary_severity(current: str, new: str) -> str:
    rank = {"none": 0, "compatible": 1, "additive": 2, "breaking": 3}
    return new if rank.get(new, 0) > rank.get(current, 0) else current


def more_restrictive_action(current: Any, new: Any) -> str:
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


def drift_policy_key(severity: Any) -> str:
    normalized = str(severity or "compatible").strip().lower()
    if normalized not in {"compatible", "additive", "breaking"}:
        normalized = "compatible"
    return f"on_{normalized}_change"


def is_accepting_drift_action(action: Any) -> bool:
    return str(action or "").strip().lower() in {"ignore", "auto_accept", "accept"}


def merge_drift_changes(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        current["severity"] = max_summary_severity(str(current.get("severity") or "none"), str(item.get("severity") or "none"))
    return list(merged.values())
