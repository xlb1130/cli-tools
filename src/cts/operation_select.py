from __future__ import annotations

import fnmatch
from typing import Any, Dict, Iterable, List, Set


def normalize_operation_select(select: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = dict(select or {})
    normalized: Dict[str, Any] = {}

    includes = _normalize_patterns(raw.get("include"))
    excludes = _normalize_patterns(raw.get("exclude"))
    tags = _normalize_tags(raw.get("tags"))

    if includes:
        normalized["include"] = includes
    if excludes:
        normalized["exclude"] = excludes
    if tags:
        normalized["tags"] = sorted(tags)
    return normalized


def operation_matches_select(operation: Any, select: Dict[str, Any] | None) -> bool:
    normalized = normalize_operation_select(select)
    if not normalized:
        return True

    includes = list(normalized.get("include", []))
    excludes = list(normalized.get("exclude", []))
    tags = set(normalized.get("tags", []))

    haystacks = [item for item in [_value(operation, "id"), _value(operation, "stable_name")] if item]
    haystacks.extend(str(item) for item in _iterable_value(operation, "tags"))

    if includes and not any(any(fnmatch.fnmatch(item, pattern) for item in haystacks) for pattern in includes):
        return False
    if excludes and any(any(fnmatch.fnmatch(item, pattern) for item in haystacks) for pattern in excludes):
        return False
    if tags and not tags.intersection(set(str(item) for item in _iterable_value(operation, "tags"))):
        return False
    return True


def _normalize_patterns(value: Any) -> List[str]:
    return [item for item in _flatten_to_strings(value) if item]


def _normalize_tags(value: Any) -> Set[str]:
    return {item for item in _flatten_to_strings(value) if item}


def _flatten_to_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: List[str] = []
        for item in value:
            result.extend(_flatten_to_strings(item))
        return result
    return [str(value)]


def _value(operation: Any, name: str) -> Any:
    if isinstance(operation, dict):
        return operation.get(name)
    return getattr(operation, name, None)


def _iterable_value(operation: Any, name: str) -> Iterable[Any]:
    value = _value(operation, name)
    if isinstance(value, (list, tuple, set)):
        return value
    return []
