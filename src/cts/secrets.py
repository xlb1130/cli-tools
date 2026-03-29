from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


SECRET_SECRET_FIELDS = {"value"}


class SecretManager:
    def __init__(self, app: Any) -> None:
        self.app = app

    def list_secrets(self) -> list[Dict[str, Any]]:
        return [self.get_secret_status(name) for name in sorted(self.app.config.secrets.keys())]

    def build_summary(self) -> Dict[str, Any]:
        items = self.list_secrets()
        state_counts: Dict[str, int] = {}
        for item in items:
            state = str(item.get("state") or "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1
        return {
            "secret_count": len(items),
            "state_counts": state_counts,
            "active_count": sum(1 for item in items if item.get("state") == "active"),
            "missing_count": sum(1 for item in items if item.get("state") == "missing"),
            "error_count": sum(1 for item in items if item.get("state") == "error"),
        }

    def get_secret_status(self, name: str) -> Dict[str, Any]:
        config = self.app.config.secrets.get(name)
        if config is None:
            raise KeyError(f"secret not found: {name}")
        resolved = self.resolve_secret(name)
        return {
            "name": name,
            "provider": str(config.get("provider") or "literal"),
            "config": redact_secret_config(dict(config)),
            "state": resolved.get("state"),
            "reason": resolved.get("reason"),
            "value_present": bool(resolved.get("value")),
            "metadata": dict(resolved.get("metadata") or {}),
        }

    def resolve_secret(self, name: str) -> Dict[str, Any]:
        config = self.app.config.secrets.get(name)
        if config is None:
            return {"state": "missing", "reason": "secret_not_found", "value": None, "metadata": {}}
        provider = str(config.get("provider") or "literal").strip().lower()
        try:
            if provider == "env":
                return self._resolve_env_secret(config)
            if provider == "file":
                return self._resolve_file_secret(config)
            if provider == "literal":
                return self._resolve_literal_secret(config)
            return {"state": "error", "reason": "unsupported_secret_provider", "value": None, "metadata": {"provider": provider}}
        except Exception as exc:
            return {"state": "error", "reason": "secret_resolution_failed", "value": None, "metadata": {"error": str(exc), "provider": provider}}

    def resolve_ref(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        resolved = self.resolve_secret(str(name))
        if resolved.get("state") != "active":
            return None
        value = resolved.get("value")
        return None if value is None else str(value)

    def resolve_refs_in_value(self, value: Any) -> Any:
        return _resolve_secret_refs(self, value)

    def redact_resolved_values(self, value: Any) -> Any:
        secret_values = self._resolved_secret_values()
        return _redact_secret_values(value, secret_values)

    def _resolve_env_secret(self, config: Dict[str, Any]) -> Dict[str, Any]:
        key = config.get("key") or config.get("env") or config.get("name")
        if not key:
            return {"state": "error", "reason": "env_key_required", "value": None, "metadata": {}}
        value = os.environ.get(str(key))
        if value in {None, ""}:
            return {"state": "missing", "reason": "env_value_missing", "value": None, "metadata": {"key": str(key)}}
        return {"state": "active", "reason": "env_value_available", "value": value, "metadata": {"key": str(key)}}

    def _resolve_file_secret(self, config: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = config.get("path") or config.get("file")
        if not raw_path:
            return {"state": "error", "reason": "file_path_required", "value": None, "metadata": {}}
        path = self.app.resolve_path(str(raw_path))
        if not path.exists():
            return {"state": "missing", "reason": "file_not_found", "value": None, "metadata": {"path": str(path)}}
        text = path.read_text(encoding="utf-8")
        format_name = str(config.get("format") or "text").strip().lower()
        if format_name == "json":
            payload = json.loads(text)
            json_key = config.get("json_key")
            if json_key:
                value = payload.get(str(json_key)) if isinstance(payload, dict) else None
            else:
                value = payload
        else:
            value = text.strip()
        if value in {None, ""}:
            return {"state": "missing", "reason": "file_value_missing", "value": None, "metadata": {"path": str(path)}}
        return {"state": "active", "reason": "file_value_available", "value": value, "metadata": {"path": str(path), "format": format_name}}

    def _resolve_literal_secret(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if "value" not in config:
            return {"state": "missing", "reason": "literal_value_missing", "value": None, "metadata": {}}
        value = config.get("value")
        if value in {None, ""}:
            return {"state": "missing", "reason": "literal_value_missing", "value": None, "metadata": {}}
        return {"state": "active", "reason": "literal_value_available", "value": value, "metadata": {}}

    def _resolved_secret_values(self) -> set[str]:
        values: set[str] = set()
        for name in self.app.config.secrets.keys():
            resolved = self.resolve_secret(name)
            value = resolved.get("value")
            if resolved.get("state") == "active" and value not in {None, ""}:
                values.add(str(value))
        return values


def redact_secret_config(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_SECRET_FIELDS:
                redacted[key] = "***" if item else None
            else:
                redacted[key] = redact_secret_config(item)
        return redacted
    if isinstance(value, list):
        return [redact_secret_config(item) for item in value]
    return value


def _resolve_secret_refs(manager: SecretManager, value: Any) -> Any:
    if isinstance(value, dict):
        if "secret_ref" in value:
            resolved = manager.resolve_ref(value.get("secret_ref"))
            if resolved is not None:
                return resolved
            return value.get("default")
        return {key: _resolve_secret_refs(manager, item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_secret_refs(manager, item) for item in value]
    return value


def _redact_secret_values(value: Any, secret_values: set[str]) -> Any:
    if isinstance(value, dict):
        return {key: _redact_secret_values(item, secret_values) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secret_values(item, secret_values) for item in value]
    if isinstance(value, str) and value in secret_values:
        return "***"
    return value
