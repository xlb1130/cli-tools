from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.execution.logging import emit_app_event, utc_now_iso


class AuthState(str, Enum):
    """Auth session states."""
    UNCONFIGURED = "unconfigured"
    CONFIGURED = "configured"
    LOGIN_REQUIRED = "login_required"
    ACTIVE = "active"
    EXPIRING = "expiring"
    REFRESHING = "refreshing"
    EXPIRED = "expired"
    FAILED = "failed"
    REVOKED = "revoked"


AUTH_ACTIVE_STATES = {AuthState.ACTIVE.value, AuthState.EXPIRING.value}
AUTH_SECRET_FIELDS = {
    "access_token",
    "api_key",
    "password",
    "refresh_token",
    "token",
    "authorization",
    "secret",
    "client_secret",
}


class AuthManager:
    def __init__(self, app: Any) -> None:
        self.app = app

    @property
    def sessions_path(self) -> Path:
        state_dir = self.app.discovery_store.paths.state_dir
        return (state_dir / "auth" / "sessions.json").resolve()

    def list_profiles(self) -> List[Dict[str, Any]]:
        items = []
        profiles = dict(self.app.config.auth_profiles)
        for name in sorted(profiles.keys()):
            items.append(self.get_profile_status(name))
        return items

    def build_summary(self) -> Dict[str, Any]:
        items = self.list_profiles()
        state_counts: Dict[str, int] = {}
        for item in items:
            state = str(item.get("state") or "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1
        return {
            "profile_count": len(items),
            "state_counts": state_counts,
            "active_count": sum(1 for item in items if item.get("state") in AUTH_ACTIVE_STATES),
            "login_required_count": sum(1 for item in items if item.get("state") == "login_required"),
            "expired_count": sum(1 for item in items if item.get("state") == "expired"),
        }

    def get_profile_status(self, name: str) -> Dict[str, Any]:
        profiles = dict(self.app.config.auth_profiles)
        profile = profiles.get(name)
        session = self._load_sessions().get(name)
        source_names = sorted([source_name for source_name, source in self.app.config.sources.items() if source.auth_ref == name])
        source_types = sorted({self.app.config.sources[source_name].type for source_name in source_names})

        if profile is None:
            return {
                "name": name,
                "configured": False,
                "state": "unconfigured",
                "reason": "auth_profile_not_found",
                "profile": None,
                "session": _redact_auth_value(session),
                "source_names": source_names,
                "source_count": len(source_names),
                "source_types": source_types,
                "resolved_credentials": None,
            }

        resolved = self.resolve_profile(name)
        return {
            "name": name,
            "configured": True,
            "state": resolved["state"],
            "reason": resolved.get("reason"),
            "profile": _redact_auth_value(dict(profile)),
            "session": _redact_auth_value(session),
            "source_names": source_names,
            "source_count": len(source_names),
            "source_types": source_types,
            "resolved_credentials": _summarize_credentials(resolved.get("resolved_credentials")),
            "status": resolved.get("status"),
        }

    def resolve_profile(self, name: str) -> Dict[str, Any]:
        profiles = dict(self.app.config.auth_profiles)
        profile = profiles.get(name)
        if profile is None:
            return {"state": "unconfigured", "reason": "auth_profile_not_found", "resolved_credentials": None}

        session = self._load_sessions().get(name)
        profile_type = str(profile.get("type") or "bearer").strip().lower()
        source_kind = str(profile.get("source") or "session").strip().lower()
        status = {
            "type": profile_type,
            "source": source_kind,
            "expires_at": None,
            "expired": False,
            "expiring": False,
            "refresh_supported": False,
            "session_store": str(profile.get("session_store") or "file"),
        }

        if session and session.get("revoked"):
            status["revoked_at"] = session.get("revoked_at")
            return {"state": "revoked", "reason": "session_revoked", "resolved_credentials": None, "status": status}

        if source_kind == "secret":
            credentials = _credentials_from_secret(self.app, profile, profile_type)
            if credentials is None:
                return {"state": "login_required", "reason": "secret_credentials_missing", "resolved_credentials": None, "status": status}
            status["refresh_supported"] = False
            return {"state": "active", "reason": "secret_credentials_available", "resolved_credentials": credentials, "status": status}

        if source_kind == "env":
            credentials = _credentials_from_env(profile, profile_type)
            if credentials is None:
                return {"state": "login_required", "reason": "env_credentials_missing", "resolved_credentials": None, "status": status}
            status["refresh_supported"] = False
            return {"state": "active", "reason": "env_credentials_available", "resolved_credentials": credentials, "status": status}

        if not session:
            return {"state": "configured", "reason": "session_not_initialized", "resolved_credentials": None, "status": status}

        credentials = _credentials_from_session(session, profile_type, profile)
        status["expires_at"] = session.get("expires_at")
        status["refresh_supported"] = bool(session.get("refresh_token"))
        expiration = _expiration_state(session.get("expires_at"), skew_seconds=int(profile.get("refresh", {}).get("skew_seconds", 300) or 300))
        status["expired"] = expiration["expired"]
        status["expiring"] = expiration["expiring"]
        if session.get("error"):
            status["last_error"] = session.get("error")
            return {"state": "failed", "reason": "session_error", "resolved_credentials": credentials, "status": status}
        if expiration["expired"]:
            return {"state": "expired", "reason": "session_expired", "resolved_credentials": credentials, "status": status}
        if expiration["expiring"]:
            return {"state": "expiring", "reason": "session_expiring", "resolved_credentials": credentials, "status": status}
        if credentials is None:
            return {"state": "login_required", "reason": "session_credentials_missing", "resolved_credentials": None, "status": status}
        return {"state": "active", "reason": "session_active", "resolved_credentials": credentials, "status": status}

    def auth_state_for_source(self, source_name: str, source_config: Any) -> Dict[str, Any]:
        auth_ref = getattr(source_config, "auth_ref", None)
        if not auth_ref:
            return {"required": False, "state": "unconfigured", "auth_ref": None}
        resolved = self.get_profile_status(auth_ref)
        return {
            "required": True,
            "auth_ref": auth_ref,
            "state": resolved.get("state"),
            "reason": resolved.get("reason"),
            "status": resolved.get("status"),
        }

    def credentials_for_source(self, source_name: str, source_config: Any) -> Optional[Dict[str, Any]]:
        auth_ref = getattr(source_config, "auth_ref", None)
        if not auth_ref:
            return None
        resolved = self.resolve_profile(auth_ref)
        if resolved["state"] not in AUTH_ACTIVE_STATES:
            return None
        return dict(resolved["resolved_credentials"] or {})

    def login(
        self,
        name: str,
        *,
        token: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        expires_at: Optional[str] = None,
        refresh_token: Optional[str] = None,
        header_name: Optional[str] = None,
        location: Optional[str] = None,
        query_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        profile = self.app.config.auth_profiles.get(name)
        if profile is None:
            raise KeyError(f"auth profile not found: {name}")

        profile_type = str(profile.get("type") or "bearer").strip().lower()
        entry = {
            "profile": name,
            "type": profile_type,
            "access_token": token,
            "api_key": api_key,
            "username": username,
            "password": password,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "header_name": header_name,
            "in": location,
            "query_name": query_name,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "metadata": dict(metadata or {}),
            "revoked": False,
        }
        if not any([token, api_key, username and password]):
            raise ValueError("login requires token/api-key or username+password credentials")
        sessions = self._load_sessions()
        sessions[name] = entry
        self._write_sessions(sessions)
        emit_app_event(self.app, event="auth_login_complete", source=None, data={"auth_profile": name, "auth_type": profile_type})
        return self.get_profile_status(name)

    def logout(self, name: str) -> Dict[str, Any]:
        if name not in self.app.config.auth_profiles:
            raise KeyError(f"auth profile not found: {name}")
        sessions = self._load_sessions()
        entry = dict(sessions.get(name) or {})
        entry["revoked"] = True
        entry["revoked_at"] = utc_now_iso()
        entry["updated_at"] = utc_now_iso()
        sessions[name] = entry
        self._write_sessions(sessions)
        emit_app_event(self.app, event="auth_logout", data={"auth_profile": name})
        return self.get_profile_status(name)

    def refresh(self, name: str) -> Dict[str, Any]:
        profiles = dict(self.app.config.auth_profiles)
        profile = profiles.get(name)
        if profile is None:
            raise KeyError(f"auth profile not found: {name}")

        source_names = [source_name for source_name, source in self.app.config.sources.items() if source.auth_ref == name]
        emit_app_event(self.app, event="auth_refresh_start", data={"auth_profile": name, "source_count": len(source_names)})
        refreshed_payload = None
        refreshed_from = None
        for source_name in source_names:
            source_config = self.app.config.sources[source_name]
            provider = self.app.get_provider(source_config)
            result = provider.refresh_auth(source_name, source_config, self.app)
            if result:
                refreshed_payload = dict(result)
                refreshed_from = source_name
                break

        sessions = self._load_sessions()
        entry = dict(sessions.get(name) or {})
        if refreshed_payload:
            entry.update(refreshed_payload)
            entry["updated_at"] = utc_now_iso()
            entry["revoked"] = False
            sessions[name] = entry
            self._write_sessions(sessions)
            emit_app_event(self.app, event="auth_refresh_complete", data={"auth_profile": name, "source": refreshed_from})
            return self.get_profile_status(name)

        entry["updated_at"] = utc_now_iso()
        sessions[name] = entry
        self._write_sessions(sessions)
        emit_app_event(self.app, event="auth_refresh_complete", data={"auth_profile": name, "source": None, "mode": "noop"})
        return self.get_profile_status(name)

    def validate(self, name: str) -> Dict[str, Any]:
        """Validate an auth profile's current state.
        
        Returns detailed validation result including:
        - Whether auth is ready for use
        - Current state and any issues
        - Recommended actions
        """
        profile = self.app.config.auth_profiles.get(name)
        if profile is None:
            return {
                "valid": False,
                "auth_profile": name,
                "state": AuthState.UNCONFIGURED.value,
                "issues": [{"code": "profile_not_found", "message": f"Auth profile '{name}' not found"}],
                "actions": [],
            }
        
        status = self.get_profile_status(name)
        state = status.get("state", "unknown")
        issues = []
        actions = []
        
        # Check configuration issues
        if state == "unconfigured":
            issues.append({"code": "not_configured", "message": "Auth profile is not properly configured"})
            actions.append({"action": "configure", "message": "Configure the auth profile in config"})
        
        elif state == "login_required":
            issues.append({"code": "login_required", "message": "Login is required"})
            actions.append({"action": "login", "command": f"cts auth login {name}"})
        
        elif state == "expired":
            issues.append({"code": "expired", "message": "Session has expired"})
            profile_obj = self.app.config.auth_profiles.get(name, {})
            if profile_obj.get("refresh", {}).get("enabled"):
                actions.append({"action": "refresh", "command": f"cts auth refresh {name}"})
            else:
                actions.append({"action": "login", "command": f"cts auth login {name}"})
        
        elif state == "expiring":
            profile_obj = self.app.config.auth_profiles.get(name, {})
            if profile_obj.get("refresh", {}).get("enabled"):
                actions.append({"action": "refresh_soon", "message": "Session expiring soon, consider refreshing"})
            issues.append({"code": "expiring", "message": "Session will expire soon", "level": "warning"})
        
        elif state == "failed":
            issues.append({"code": "failed", "message": status.get("reason", "Authentication failed")})
            actions.append({"action": "retry", "command": f"cts auth login {name}"})
        
        elif state == "revoked":
            issues.append({"code": "revoked", "message": "Session has been revoked"})
            actions.append({"action": "login", "command": f"cts auth login {name}"})
        
        valid = state in AUTH_ACTIVE_STATES
        
        return {
            "valid": valid,
            "auth_profile": name,
            "state": state,
            "issues": issues,
            "actions": actions,
            "status": status.get("status"),
        }

    def validate_all(self) -> Dict[str, Any]:
        """Validate all auth profiles."""
        results = {}
        for name in self.app.config.auth_profiles:
            results[name] = self.validate(name)
        
        valid_count = sum(1 for r in results.values() if r.get("valid"))
        total_count = len(results)
        
        return {
            "ok": valid_count == total_count,
            "valid_count": valid_count,
            "total_count": total_count,
            "profiles": results,
        }

    def auto_refresh_if_needed(self, name: str, force: bool = False) -> Dict[str, Any]:
        """Auto-refresh auth if session is expiring or expired.
        
        Args:
            name: Auth profile name
            force: Force refresh even if not expiring
            
        Returns:
            Result including whether refresh was attempted and current state
        """
        profile = self.app.config.auth_profiles.get(name)
        if profile is None:
            return {
                "refreshed": False,
                "reason": "profile_not_found",
                "state": AuthState.UNCONFIGURED.value,
            }
        
        # Check if refresh is enabled for this profile
        refresh_config = profile.get("refresh", {})
        if not refresh_config.get("enabled", False):
            return {
                "refreshed": False,
                "reason": "refresh_not_enabled",
                "state": self.get_profile_status(name).get("state"),
            }
        
        status = self.get_profile_status(name)
        state = status.get("state")
        
        # Determine if refresh is needed
        needs_refresh = force or state in ("expiring", "expired")
        
        if not needs_refresh:
            return {
                "refreshed": False,
                "reason": "not_needed",
                "state": state,
            }
        
        # Attempt refresh
        try:
            result = self.refresh(name)
            return {
                "refreshed": True,
                "previous_state": state,
                "current_state": result.get("state"),
                "result": result,
            }
        except Exception as e:
            return {
                "refreshed": False,
                "reason": "refresh_failed",
                "error": str(e),
                "state": state,
            }

    def get_credentials_or_refresh(self, name: str) -> Optional[Dict[str, Any]]:
        """Get credentials, auto-refreshing if needed.
        
        This is the recommended method for getting credentials before
        an operation that requires authentication.
        """
        profile = self.app.config.auth_profiles.get(name)
        if profile is None:
            return None
        
        # Check current state
        status = self.get_profile_status(name)
        state = status.get("state")
        
        # If already active, return credentials
        if state in AUTH_ACTIVE_STATES:
            return self.credentials_for_source(
                next((s for s, c in self.app.config.sources.items() if c.auth_ref == name), ""),
                self.app.config.sources.get(next((s for s, c in self.app.config.sources.items() if c.auth_ref == name), "")),
            )
        
        # Try auto-refresh if enabled
        refresh_config = profile.get("refresh", {})
        if refresh_config.get("enabled") and state in ("expiring", "expired"):
            refresh_result = self.auto_refresh_if_needed(name)
            if refresh_result.get("refreshed"):
                # Re-get credentials after refresh
                return self.credentials_for_source(
                    next((s for s, c in self.app.config.sources.items() if c.auth_ref == name), ""),
                    self.app.config.sources.get(next((s for s, c in self.app.config.sources.items() if c.auth_ref == name), "")),
                )
        
        return None

    def _load_sessions(self) -> Dict[str, Dict[str, Any]]:
        path = self.sessions_path
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): value for key, value in payload.items() if isinstance(value, dict)}

    def _write_sessions(self, payload: Dict[str, Dict[str, Any]]) -> None:
        path = self.sessions_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _credentials_from_env(profile: Dict[str, Any], profile_type: str) -> Optional[Dict[str, Any]]:
    if profile_type == "bearer":
        token_env = profile.get("token_env")
        token = os.environ.get(str(token_env)) if token_env else None
        if not token:
            return None
        return {"type": "bearer", "token": token}
    if profile_type == "api_key":
        key_env = profile.get("key_env") or profile.get("token_env")
        api_key = os.environ.get(str(key_env)) if key_env else None
        if not api_key:
            return None
        return {
            "type": "api_key",
            "api_key": api_key,
            "header_name": profile.get("header_name", "X-API-Key"),
            "in": profile.get("in", "header"),
            "query_name": profile.get("query_name", "api_key"),
        }
    if profile_type == "basic":
        user_env = profile.get("username_env")
        password_env = profile.get("password_env")
        username = os.environ.get(str(user_env)) if user_env else None
        password = os.environ.get(str(password_env)) if password_env else None
        if not username or not password:
            return None
        return {"type": "basic", "username": username, "password": password}
    return None


def _credentials_from_secret(app: Any, profile: Dict[str, Any], profile_type: str) -> Optional[Dict[str, Any]]:
    if profile_type == "bearer":
        secret_ref = profile.get("secret_ref") or profile.get("token_ref")
        token = app.secret_manager.resolve_ref(secret_ref)
        if not token:
            return None
        return {"type": "bearer", "token": token}
    if profile_type == "api_key":
        secret_ref = profile.get("secret_ref") or profile.get("api_key_ref") or profile.get("token_ref")
        api_key = app.secret_manager.resolve_ref(secret_ref)
        if not api_key:
            return None
        return {
            "type": "api_key",
            "api_key": api_key,
            "header_name": profile.get("header_name", "X-API-Key"),
            "in": profile.get("in", "header"),
            "query_name": profile.get("query_name", "api_key"),
        }
    if profile_type == "basic":
        username_ref = profile.get("username_ref")
        password_ref = profile.get("password_ref")
        username = app.secret_manager.resolve_ref(username_ref)
        password = app.secret_manager.resolve_ref(password_ref)
        if not username or not password:
            return None
        return {"type": "basic", "username": username, "password": password}
    return None


def _credentials_from_session(session: Dict[str, Any], profile_type: str, profile: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    profile = dict(profile or {})
    if profile_type == "bearer":
        token = session.get("access_token")
        return {"type": "bearer", "token": token} if token else None
    if profile_type == "api_key":
        api_key = session.get("api_key") or session.get("access_token")
        return (
            {
                "type": "api_key",
                "api_key": api_key,
                "header_name": session.get("header_name") or profile.get("header_name", "X-API-Key"),
                "in": session.get("in") or profile.get("in", "header"),
                "query_name": session.get("query_name") or profile.get("query_name", "api_key"),
            }
            if api_key
            else None
        )
    if profile_type == "basic":
        username = session.get("username")
        password = session.get("password")
        if username and password:
            return {"type": "basic", "username": username, "password": password}
        return None
    token = session.get("access_token")
    return {"type": profile_type, "token": token} if token else None


def apply_auth_to_request(
    credentials: Optional[Dict[str, Any]],
    *,
    headers: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    next_headers = dict(headers or {})
    next_params = dict(params or {})
    if not credentials:
        return next_headers, next_params

    auth_type = str(credentials.get("type") or "").strip().lower()
    if auth_type == "bearer" and credentials.get("token"):
        next_headers["Authorization"] = f"Bearer {credentials['token']}"
    elif auth_type == "api_key" and credentials.get("api_key"):
        header_name = str(credentials.get("header_name") or "X-API-Key")
        location = str(credentials.get("in") or "header").strip().lower()
        if location == "query":
            next_params[str(credentials.get("query_name") or "api_key")] = credentials["api_key"]
        else:
            next_headers[header_name] = credentials["api_key"]
    elif auth_type == "basic" and credentials.get("username") and credentials.get("password"):
        raw = f"{credentials['username']}:{credentials['password']}".encode("utf-8")
        next_headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    return next_headers, next_params


def _expiration_state(raw_expires_at: Optional[str], *, skew_seconds: int) -> Dict[str, bool]:
    if not raw_expires_at:
        return {"expired": False, "expiring": False}
    try:
        parsed = datetime.fromisoformat(str(raw_expires_at))
    except ValueError:
        return {"expired": False, "expiring": False}
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    remaining = (parsed.astimezone(timezone.utc) - now).total_seconds()
    return {"expired": remaining <= 0, "expiring": 0 < remaining <= skew_seconds}


def _summarize_credentials(credentials: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not credentials:
        return None
    auth_type = str(credentials.get("type") or "").strip().lower()
    if auth_type == "bearer":
        return {"type": "bearer", "present": bool(credentials.get("token"))}
    if auth_type == "api_key":
        return {
            "type": "api_key",
            "present": bool(credentials.get("api_key")),
            "in": credentials.get("in", "header"),
            "header_name": credentials.get("header_name"),
            "query_name": credentials.get("query_name"),
        }
    if auth_type == "basic":
        return {
            "type": "basic",
            "username": credentials.get("username"),
            "password_present": bool(credentials.get("password")),
        }
    return {"type": auth_type or "unknown", "present": True}


def _redact_auth_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in AUTH_SECRET_FIELDS:
                redacted[key] = "***" if item else None
            else:
                redacted[key] = _redact_auth_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_auth_value(item) for item in value]
    return value
