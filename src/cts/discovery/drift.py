from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, List, Optional


def compare_discovery_snapshots(
    previous_snapshot: Optional[Dict[str, Any]],
    current_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    if not previous_snapshot:
        return {
            "status": "initial",
            "changed": False,
            "severity": "none",
            "summary": _build_summary([]),
            "changes": [],
        }

    if previous_snapshot.get("snapshot_fingerprint") == current_snapshot.get("snapshot_fingerprint"):
        previous_count = len(previous_snapshot.get("operations") or [])
        return {
            "status": "unchanged",
            "changed": False,
            "severity": "none",
            "summary": {
                **_build_summary([]),
                "previous_operation_count": previous_count,
                "current_operation_count": previous_count,
            },
            "changes": [],
        }

    previous_ops = {item.get("id"): item for item in previous_snapshot.get("operations") or [] if isinstance(item, dict) and item.get("id")}
    current_ops = {item.get("id"): item for item in current_snapshot.get("operations") or [] if isinstance(item, dict) and item.get("id")}
    previous_schema = dict(previous_snapshot.get("schema_index") or {})
    current_schema = dict(current_snapshot.get("schema_index") or {})
    changes: List[Dict[str, Any]] = []

    for operation_id in sorted(set(previous_ops) | set(current_ops)):
        before = previous_ops.get(operation_id)
        after = current_ops.get(operation_id)
        if before is None and after is not None:
            changes.append(
                {
                    "operation_id": operation_id,
                    "change_type": "operation_added",
                    "severity": "additive",
                    "reasons": ["operation_added"],
                }
            )
            continue
        if before is not None and after is None:
            changes.append(
                {
                    "operation_id": operation_id,
                    "change_type": "operation_removed",
                    "severity": "breaking",
                    "reasons": ["operation_removed"],
                }
            )
            continue
        assert before is not None and after is not None
        current_change = _compare_operation(
            operation_id,
            before,
            after,
            previous_schema.get(operation_id),
            current_schema.get(operation_id),
        )
        if current_change is not None:
            changes.append(current_change)

    severity = _max_severity(change["severity"] for change in changes) if changes else "none"
    status = "changed" if changes else "unchanged"
    return {
        "status": status,
        "changed": bool(changes),
        "severity": severity,
        "summary": _build_summary(
            changes,
            previous_operation_count=len(previous_ops),
            current_operation_count=len(current_ops),
        ),
        "changes": changes,
    }


def _compare_operation(
    operation_id: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    previous_schema_record: Optional[Dict[str, Any]],
    current_schema_record: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    reasons: List[str] = []
    severity = "compatible"

    if before.get("stable_name") != after.get("stable_name"):
        severity = _raise_severity(severity, "breaking")
        reasons.append("stable_name_changed")

    before_risk = str(before.get("risk") or "read")
    after_risk = str(after.get("risk") or "read")
    if before_risk != after_risk:
        if _risk_rank(after_risk) > _risk_rank(before_risk):
            severity = _raise_severity(severity, "breaking")
        else:
            severity = _raise_severity(severity, "compatible")
        reasons.append("risk_changed")

    before_surfaces = set(before.get("supported_surfaces") or [])
    after_surfaces = set(after.get("supported_surfaces") or [])
    if before_surfaces - after_surfaces:
        severity = _raise_severity(severity, "breaking")
        reasons.append("supported_surfaces_removed")
    if after_surfaces - before_surfaces:
        severity = _raise_severity(severity, "additive")
        reasons.append("supported_surfaces_added")

    schema_change = _compare_input_schema(
        (previous_schema_record or {}).get("input_schema") or before.get("input_schema") or {},
        (current_schema_record or {}).get("input_schema") or after.get("input_schema") or {},
    )
    if schema_change["severity"] != "none":
        severity = _raise_severity(severity, schema_change["severity"])
        reasons.extend(schema_change["reasons"])

    if before.get("description") != after.get("description"):
        severity = _raise_severity(severity, "compatible")
        reasons.append("description_changed")

    if not reasons:
        if _fingerprint(before) != _fingerprint(after):
            reasons.append("operation_metadata_changed")
        else:
            return None

    return {
        "operation_id": operation_id,
        "change_type": "operation_changed",
        "severity": severity,
        "reasons": sorted(set(reasons)),
    }


def _compare_input_schema(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    before_properties = dict(before.get("properties") or {})
    after_properties = dict(after.get("properties") or {})
    before_required = set(before.get("required") or [])
    after_required = set(after.get("required") or [])
    reasons: List[str] = []
    severity = "none"

    for key in sorted(before_properties.keys() - after_properties.keys()):
        severity = _raise_severity(severity, "breaking")
        reasons.append(f"param_removed:{key}")

    for key in sorted(after_properties.keys() - before_properties.keys()):
        if key in after_required:
            severity = _raise_severity(severity, "breaking")
            reasons.append(f"required_param_added:{key}")
        else:
            severity = _raise_severity(severity, "additive")
            reasons.append(f"optional_param_added:{key}")

    for key in sorted(before_properties.keys() & after_properties.keys()):
        before_prop = dict(before_properties.get(key) or {})
        after_prop = dict(after_properties.get(key) or {})
        before_type = _schema_type_signature(before_prop)
        after_type = _schema_type_signature(after_prop)
        if before_type != after_type:
            severity = _raise_severity(severity, "breaking")
            reasons.append(f"param_type_changed:{key}")
        if (key in before_required) != (key in after_required):
            if key in after_required:
                severity = _raise_severity(severity, "breaking")
                reasons.append(f"param_now_required:{key}")
            else:
                severity = _raise_severity(severity, "compatible")
                reasons.append(f"param_no_longer_required:{key}")
        enum_change = _compare_enum(before_prop.get("enum"), after_prop.get("enum"))
        if enum_change:
            severity = _raise_severity(severity, enum_change)
            reasons.append(f"param_enum_changed:{key}")
        if before_prop.get("default") != after_prop.get("default"):
            severity = _raise_severity(severity, "compatible")
            reasons.append(f"param_default_changed:{key}")

    return {"severity": severity, "reasons": reasons}


def _compare_enum(before: Any, after: Any) -> Optional[str]:
    if before is None and after is None:
        return None
    before_values = set(before or [])
    after_values = set(after or [])
    if before_values == after_values:
        return None
    if before_values and after_values and not before_values.issubset(after_values):
        return "breaking"
    if after_values - before_values:
        return "additive"
    return "compatible"


def _schema_type_signature(schema: Dict[str, Any]) -> str:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return "|".join(sorted(str(item) for item in schema_type))
    return str(schema_type)


def _build_summary(
    changes: List[Dict[str, Any]],
    *,
    previous_operation_count: int = 0,
    current_operation_count: int = 0,
) -> Dict[str, Any]:
    summary = {
        "previous_operation_count": previous_operation_count,
        "current_operation_count": current_operation_count,
        "added": 0,
        "removed": 0,
        "changed": 0,
        "breaking": 0,
        "additive": 0,
        "compatible": 0,
    }
    for change in changes:
        if change["change_type"] == "operation_added":
            summary["added"] += 1
        elif change["change_type"] == "operation_removed":
            summary["removed"] += 1
        else:
            summary["changed"] += 1
        if change["severity"] in {"breaking", "additive", "compatible"}:
            summary[change["severity"]] += 1
    return summary


def _raise_severity(current: str, new: str) -> str:
    if _severity_rank(new) > _severity_rank(current):
        return new
    return current


def _severity_rank(value: str) -> int:
    return {"none": 0, "compatible": 1, "additive": 2, "breaking": 3}.get(value, 0)


def _max_severity(items: Any) -> str:
    result = "none"
    for item in items:
        result = _raise_severity(result, str(item))
    return result


def _risk_rank(value: str) -> int:
    return {"read": 0, "write": 1, "destructive": 2}.get(value, 0)


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
