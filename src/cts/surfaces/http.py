from __future__ import annotations

import json
import mimetypes
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from cts.app import build_app
from cts.config.management import add_alias, add_mount, add_source, get_source_detail, list_aliases, remove_alias, remove_mount, remove_source
from cts.execution.logging import emit_app_event, emit_audit_event, get_run, list_runs, record_run, summarize_result, utc_now_iso
from cts.execution.runtime import build_error_envelope, explain_mount, invoke_mount
from cts.presentation import (
    build_app_summary,
    build_auth_inventory,
    build_auth_profile,
    build_extension_events,
    build_extensions_summary,
    build_hook_inventory,
    build_hook_contracts,
    build_mount_details,
    build_mount_help,
    build_plugin_inventory,
    build_provider_inventory,
    build_reliability_status,
    build_secret_detail,
    build_secret_inventory,
    build_source_check_result,
    build_source_details,
    build_source_summary,
    filter_mount_summary,
)


@dataclass
class HTTPServeResult:
    host: str
    port: int
    base_url: str


class CTSHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, app, ui_dir: Optional[Path] = None):  # noqa: N803
        super().__init__(server_address, RequestHandlerClass)
        self.app = app
        self.ui_dir = ui_dir

    def reload_app(self) -> Any:
        config_path = self.app.explicit_config_path
        profile = self.app.requested_profile
        next_app = build_app(config_path, profile=profile)
        self.app = next_app
        emit_app_event(next_app, event="surface_reload_complete", data={"surface": "http"})
        return next_app


def create_http_server(app, host: str = "127.0.0.1", port: int = 8787, ui_dir: Optional[Path] = None) -> CTSHTTPServer:
    return CTSHTTPServer((host, port), CTSHTTPRequestHandler, app, ui_dir=ui_dir)


def serve_http(app, host: str = "127.0.0.1", port: int = 8787) -> HTTPServeResult:
    server = create_http_server(app, host=host, port=port)
    actual_host, actual_port = server.server_address
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return HTTPServeResult(host=actual_host, port=actual_port, base_url=f"http://{actual_host}:{actual_port}")


class CTSHTTPRequestHandler(BaseHTTPRequestHandler):
    server: CTSHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api") and parsed.path not in {"/healthz", "/api/healthz"}:
            if self._try_static(parsed.path):
                return
        try:
            self._dispatch_surface_hook("surface.http.request.before", {"method": "GET", "path": parsed.path, "query": parse_qs(parsed.query)})
            payload = self._route_get(parsed.path, parse_qs(parsed.query))
            self._dispatch_surface_hook(
                "surface.http.request.after",
                {"method": "GET", "path": parsed.path, "query": parse_qs(parsed.query), "response": payload},
            )
            self._write_json(payload, status=HTTPStatus.OK)
        except KeyError as exc:
            self._dispatch_surface_hook(
                "surface.http.request.error",
                {"method": "GET", "path": parsed.path, "query": parse_qs(parsed.query), "error": exc},
            )
            payload = build_error_envelope(exc, "surface_http")
            self._write_json(payload, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._dispatch_surface_hook(
                "surface.http.request.error",
                {"method": "GET", "path": parsed.path, "query": parse_qs(parsed.query), "error": exc},
            )
            payload = build_error_envelope(exc, "surface_http")
            self._write_json(payload, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._dispatch_surface_hook(
                "surface.http.request.error",
                {"method": "GET", "path": parsed.path, "query": parse_qs(parsed.query), "error": exc},
            )
            payload = build_error_envelope(exc, "surface_http")
            self._write_json(payload, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
            self._dispatch_surface_hook(
                "surface.http.request.before",
                {"method": "POST", "path": parsed.path, "body": body},
            )
            payload = self._route_post(parsed.path, body)
            self._dispatch_surface_hook(
                "surface.http.request.after",
                {"method": "POST", "path": parsed.path, "body": body, "response": payload},
            )
            self._write_json(payload, status=HTTPStatus.OK)
        except KeyError as exc:
            self._dispatch_surface_hook(
                "surface.http.request.error",
                {"method": "POST", "path": parsed.path, "error": exc},
            )
            payload = build_error_envelope(exc, "surface_http")
            self._write_json(payload, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._dispatch_surface_hook(
                "surface.http.request.error",
                {"method": "POST", "path": parsed.path, "error": exc},
            )
            payload = build_error_envelope(exc, "surface_http")
            self._write_json(payload, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._dispatch_surface_hook(
                "surface.http.request.error",
                {"method": "POST", "path": parsed.path, "error": exc},
            )
            payload = build_error_envelope(exc, "surface_http")
            status = HTTPStatus.BAD_REQUEST if payload["error"].get("user_fixable") else HTTPStatus.INTERNAL_SERVER_ERROR
            self._write_json(payload, status=status)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None

    def _route_get(self, path: str, query: Dict[str, list[str]]) -> Dict[str, Any]:
        app = self.server.app

        if path in {"/healthz", "/api/healthz"}:
            return {"ok": True}

        if path == "/api/app/summary":
            return build_app_summary(app)

        if path == "/api/reliability":
            return build_reliability_status(app)

        if path == "/api/auth/profiles":
            return build_auth_inventory(app)

        if path.startswith("/api/auth/profiles/"):
            name = path.split("/", 4)[4]
            return build_auth_profile(app, name)

        if path == "/api/secrets":
            return build_secret_inventory(app)

        if path.startswith("/api/secrets/"):
            name = path.split("/", 3)[3]
            return build_secret_detail(app, name)

        if path == "/api/extensions/summary":
            return build_extensions_summary(app)

        if path == "/api/extensions/plugins":
            return build_plugin_inventory(app)

        if path == "/api/extensions/providers":
            return build_provider_inventory(app)

        if path == "/api/extensions/hooks":
            return build_hook_inventory(app, event=_first(query, "event"), plugin=_first(query, "plugin"))

        if path == "/api/extensions/contracts":
            return build_hook_contracts()

        if path == "/api/extensions/events":
            limit = int(_first(query, "limit") or 50)
            return build_extension_events(
                app,
                limit=limit,
                event=_first(query, "event"),
                plugin=_first(query, "plugin"),
                hook_event=_first(query, "hook_event"),
                level=_first(query, "level"),
                mount_id=_first(query, "mount_id"),
                source=_first(query, "source"),
                before_ts=_first(query, "before_ts"),
            )

        if path == "/api/sources":
            return {
                "items": [
                    {
                        **build_source_summary(app, name, source),
                        "health": build_source_check_result(app, name, source),
                    }
                    for name, source in app.config.sources.items()
                ]
            }

        if path.startswith("/api/sources/"):
            source_name = path.split("/", 3)[3]
            source = app.config.sources.get(source_name)
            if source is None:
                raise KeyError(f"source not found: {source_name}")
            payload = get_source_detail(app, source_name)
            payload["health"] = build_source_check_result(app, source_name, source)
            return payload

        if path == "/api/mounts":
            q = _first(query, "q")
            risk = _first(query, "risk")
            source = _first(query, "source")
            surface = _first(query, "surface")
            items = []
            for mount in app.catalog.mounts:
                item = mount.to_summary()
                item["id"] = item["mount_id"]
                item["operation"] = mount.operation.id
                item["supported_surfaces"] = list(mount.operation.supported_surfaces)
                if filter_mount_summary(item, q=q, risk=risk, source=source, surface=surface):
                    items.append(item)
            return {"items": items}

        if path.startswith("/api/mounts/") and path.endswith("/help"):
            mount_id = path[len("/api/mounts/") : -len("/help")].strip("/")
            mount = app.catalog.find_by_id(mount_id)
            if mount is None:
                raise KeyError(f"mount not found: {mount_id}")
            return build_mount_help(app, mount)

        if path.startswith("/api/mounts/"):
            mount_id = path.split("/", 3)[3]
            mount = app.catalog.find_by_id(mount_id)
            if mount is None:
                raise KeyError(f"mount not found: {mount_id}")
            return build_mount_details(app, mount)

        if path == "/api/catalog":
            return app.export_catalog()

        if path == "/api/aliases":
            return list_aliases(app)

        if path.startswith("/api/catalog/"):
            mount_id = path.split("/", 3)[3]
            mount = app.catalog.find_by_id(mount_id)
            if mount is None:
                raise KeyError(f"mount not found: {mount_id}")
            return {"mount": build_mount_details(app, mount)}

        if path == "/api/drift":
            report = app.get_latest_drift_report()
            if report is None:
                raise KeyError("drift report not found")
            return report

        if path.startswith("/api/drift/"):
            source_name = path.split("/", 3)[3]
            report = app.get_latest_drift_report(source_name)
            if report is None or not report.get("items"):
                raise KeyError(f"drift report not found for source: {source_name}")
            report["source_drift_state"] = app.get_source_drift_state(source_name)
            return report

        if path == "/api/runs":
            limit = int(_first(query, "limit") or 20)
            return {"items": list_runs(app, limit=limit)}

        if path.startswith("/api/runs/"):
            run_id = path.split("/", 3)[3]
            payload = get_run(app, run_id)
            if payload is None:
                raise KeyError(f"run not found: {run_id}")
            return payload

        # Log query APIs
        if path == "/api/logs/config":
            from cts.execution.logging import get_config_events
            limit = int(_first(query, "limit") or 100)
            before_ts = _first(query, "before_ts")
            return {"items": get_config_events(app, limit=limit, before_ts=before_ts)}

        if path == "/api/logs/discovery":
            from cts.execution.logging import get_discovery_events
            limit = int(_first(query, "limit") or 100)
            source = _first(query, "source")
            event_prefix = _first(query, "event_prefix")
            before_ts = _first(query, "before_ts")
            return {"items": get_discovery_events(
                app, limit=limit, source=source, event_prefix=event_prefix, before_ts=before_ts
            )}

        if path == "/api/logs/app":
            from cts.execution.logging import list_app_events
            limit = int(_first(query, "limit") or 100)
            events = _first(query, "events")
            events_list = events.split(",") if events else None
            level = _first(query, "level")
            source = _first(query, "source")
            mount_id = _first(query, "mount_id")
            before_ts = _first(query, "before_ts")
            return {"items": list_app_events(
                app,
                limit=limit,
                events=events_list,
                level=level,
                source=source,
                mount_id=mount_id,
                before_ts=before_ts,
            )}

        raise KeyError(f"route not found: {path}")

    def _route_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        app = self.server.app

        if path == "/api/reload":
            next_app = self.server.reload_app()
            return {
                "ok": True,
                "action": "reload",
                "summary": build_app_summary(next_app),
            }

        if path == "/api/auth/login":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("'name' is required.")
            return {
                "ok": True,
                "action": "auth_login",
                "profile": app.auth_manager.login(
                    name,
                    token=payload.get("token"),
                    api_key=payload.get("api_key"),
                    username=payload.get("username"),
                    password=payload.get("password"),
                    expires_at=payload.get("expires_at"),
                    refresh_token=payload.get("refresh_token"),
                    header_name=payload.get("header_name"),
                    location=payload.get("in"),
                    query_name=payload.get("query_name"),
                    metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
                ),
            }

        if path == "/api/auth/logout":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("'name' is required.")
            return {
                "ok": True,
                "action": "auth_logout",
                "profile": app.auth_manager.logout(name),
            }

        if path.startswith("/api/auth/logout/"):
            name = path.split("/", 4)[4]
            return {
                "ok": True,
                "action": "auth_logout",
                "profile": app.auth_manager.logout(name),
            }

        if path == "/api/auth/refresh":
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("'name' is required.")
            return {
                "ok": True,
                "action": "auth_refresh",
                "profile": app.auth_manager.refresh(name),
            }

        if path.startswith("/api/auth/refresh/"):
            name = path.split("/", 4)[4]
            return {
                "ok": True,
                "action": "auth_refresh",
                "profile": app.auth_manager.refresh(name),
            }

        if path == "/api/sync":
            sync_result = app.sync()
            items = sync_result.get("items", [])
            emit_app_event(app, event="surface_sync_complete", data={"surface": "http", "source": None, "items": items})
            return {
                "ok": all(item.get("ok", False) for item in items) if items else True,
                "action": "sync",
                **sync_result,
            }

        if path.startswith("/api/sync/"):
            source_name = path.split("/", 3)[3]
            sync_result = app.sync(source_name)
            items = sync_result.get("items", [])
            if not items:
                raise KeyError(f"source not found: {source_name}")
            emit_app_event(
                app,
                event="surface_sync_complete",
                data={"surface": "http", "source": source_name, "items": items},
            )
            return {
                "ok": all(item.get("ok", False) for item in items),
                "action": "sync",
                **sync_result,
            }

        if path == "/api/extensions/hooks/explain":
            event, hook_payload = self._build_hook_debug_payload(payload)
            return {
                "ok": True,
                "action": "hook_explain",
                **app.plugin_manager.explain_dispatch(event, hook_payload, app=app),
            }

        if path == "/api/extensions/hooks/simulate":
            event, hook_payload = self._build_hook_debug_payload(payload)
            execute_handlers = bool(payload.get("execute_handlers"))
            return {
                "ok": True,
                "action": "hook_simulate",
                **app.plugin_manager.simulate_dispatch(
                    event,
                    hook_payload,
                    app=app,
                    execute_handlers=execute_handlers,
                ),
            }

        if path.startswith("/api/mounts/") and path.endswith("/explain"):
            mount_id = path[len("/api/mounts/") : -len("/explain")].strip("/")
            mount = app.catalog.find_by_id(mount_id)
            if mount is None:
                raise KeyError(f"mount not found: {mount_id}")
            raw_input = payload.get("input", {})
            if raw_input is None:
                raw_input = {}
            if not isinstance(raw_input, dict):
                raise ValueError("'input' must be a JSON object.")
            return explain_mount(
                app,
                mount,
                raw_input,
                {"non_interactive": True, "run_id": str(uuid.uuid4()), "trace_id": str(uuid.uuid4())},
            )

        if path.startswith("/api/mounts/") and path.endswith("/invoke"):
            mount_id = path[len("/api/mounts/") : -len("/invoke")].strip("/")
            mount = app.catalog.find_by_id(mount_id)
            if mount is None:
                raise KeyError(f"mount not found: {mount_id}")
            raw_input = payload.get("input", {})
            if raw_input is None:
                raw_input = {}
            if not isinstance(raw_input, dict):
                raise ValueError("'input' must be a JSON object.")
            return self._execute_mount_http(app, mount, raw_input, dry_run=bool(payload.get("dry_run", False)))

        if path.startswith("/api/sources/") and path.endswith("/test"):
            source_name = path[len("/api/sources/") : -len("/test")].strip("/")
            source = app.config.sources.get(source_name)
            if source is None:
                raise KeyError(f"source not found: {source_name}")
            discover = bool(payload.get("discover"))
            result = build_source_check_result(app, source_name, source)
            if discover:
                sync_result = app.sync(source_name)
                sync_items = sync_result.get("items", [])
                result["discovery"] = sync_items[0] if sync_items else {"ok": False, "source": source_name, "operation_count": 0}
                result["discovery_report_path"] = sync_result.get("report_path")
                result["capability_snapshot_path"] = sync_result.get("capability_snapshot_path")
                result["ok"] = bool(result.get("ok", False) and result["discovery"].get("ok", False))
            return result

        if path == "/api/sources":
            result = add_source(
                explicit_config_path=app.explicit_config_path,
                profile=app.requested_profile,
                provider_type=str(payload.get("provider_type") or ""),
                source_name=str(payload.get("source_name") or ""),
                description=str(payload.get("description") or "") or None,
                executable=str(payload.get("executable") or "") or None,
                base_url=str(payload.get("base_url") or "") or None,
                manifest=str(payload.get("manifest") or "") or None,
                discover_mode=str(payload.get("discover_mode") or "") or None,
                auth_ref=str(payload.get("auth_ref") or "") or None,
                surfaces=list(payload.get("surfaces") or []),
                enabled=bool(payload.get("enabled", True)),
            )
            next_app = self.server.reload_app()
            result["summary"] = build_app_summary(next_app)
            return result

        if path.startswith("/api/sources/") and path.endswith("/remove"):
            source_name = path[len("/api/sources/") : -len("/remove")].strip("/")
            result = remove_source(
                explicit_config_path=app.explicit_config_path,
                profile=app.requested_profile,
                source_name=source_name,
                force=bool(payload.get("force", False)),
            )
            next_app = self.server.reload_app()
            result["summary"] = build_app_summary(next_app)
            return result

        if path == "/api/mounts":
            result = add_mount(
                explicit_config_path=app.explicit_config_path,
                profile=app.requested_profile,
                source_name=str(payload.get("source_name") or ""),
                operation_id=str(payload.get("operation_id") or ""),
                mount_id=str(payload.get("mount_id") or "") or None,
                command_path=str(payload.get("command_path") or "") or None,
                stable_name=str(payload.get("stable_name") or "") or None,
                summary=str(payload.get("summary") or "") or None,
                description=str(payload.get("description") or "") or None,
                risk=str(payload.get("risk") or "") or None,
                surfaces=list(payload.get("surfaces") or []),
            )
            next_app = self.server.reload_app()
            result["summary"] = build_app_summary(next_app)
            return result

        if path.startswith("/api/mounts/") and path.endswith("/remove"):
            mount_id = path[len("/api/mounts/") : -len("/remove")].strip("/")
            result = remove_mount(
                explicit_config_path=app.explicit_config_path,
                profile=app.requested_profile,
                mount_id=mount_id,
            )
            next_app = self.server.reload_app()
            result["summary"] = build_app_summary(next_app)
            return result

        if path == "/api/aliases":
            result = add_alias(
                explicit_config_path=app.explicit_config_path,
                profile=app.requested_profile,
                alias_from=str(payload.get("alias_from") or ""),
                alias_to=str(payload.get("alias_to") or ""),
            )
            next_app = self.server.reload_app()
            result["summary"] = build_app_summary(next_app)
            return result

        if path.startswith("/api/aliases/") and path.endswith("/remove"):
            alias_from = path[len("/api/aliases/") : -len("/remove")].strip("/")
            result = remove_alias(
                explicit_config_path=app.explicit_config_path,
                profile=app.requested_profile,
                alias_from=unquote(alias_from),
            )
            next_app = self.server.reload_app()
            result["summary"] = build_app_summary(next_app)
            return result

        raise KeyError(f"route not found: {path}")

    def _build_hook_debug_payload(self, payload: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        app = self.server.app
        event = str(payload.get("event") or "").strip()
        if not event:
            raise ValueError("'event' is required.")

        raw_payload = payload.get("payload", {})
        if raw_payload is None:
            raw_payload = {}
        if not isinstance(raw_payload, dict):
            raise ValueError("'payload' must be a JSON object.")

        hook_payload = dict(raw_payload)
        mount_id = payload.get("mount_id")
        if mount_id:
            mount = app.catalog.find_by_id(str(mount_id))
            if mount is None:
                raise KeyError(f"mount not found: {mount_id}")
            hook_payload["mount"] = mount
            hook_payload.setdefault("mount_id", mount.mount_id)

        source_name = payload.get("source_name")
        if source_name:
            source = app.config.sources.get(str(source_name))
            if source is None:
                raise KeyError(f"source not found: {source_name}")
            hook_payload["source_name"] = str(source_name)
            hook_payload["source"] = str(source_name)
            hook_payload["source_config"] = source
            hook_payload["provider"] = app.get_provider(source)
            hook_payload.setdefault("provider_type", source.type)

        hook_payload.setdefault("runtime", {})
        return event, hook_payload

    def _execute_mount_http(self, app: Any, mount: Any, raw_input: Dict[str, Any], *, dry_run: bool) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        started_at = utc_now_iso()
        app.ensure_mount_execution_allowed(mount, mode="invoke", run_id=run_id, trace_id=trace_id)
        emit_app_event(
            app,
            event="invoke_start",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"args": raw_input, "provider_type": mount.provider_type, "surface": "http", "dry_run": dry_run},
        )
        result = invoke_mount(
            app,
            mount,
            raw_input,
            {"run_id": run_id, "trace_id": trace_id, "non_interactive": True, "dry_run": dry_run},
        )
        emit_app_event(
            app,
            event="invoke_complete",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"result": summarize_result(result), "surface": "http", "dry_run": dry_run},
        )
        emit_audit_event(
            app,
            event="invoke_complete",
            run_id=run_id,
            trace_id=trace_id,
            source=mount.source_name,
            mount_id=mount.mount_id,
            operation_id=mount.operation.id,
            data={"ok": result.get("ok"), "risk": mount.operation.risk, "provider_type": mount.provider_type, "surface": "http"},
        )
        record_run(
            app,
            {
                "run_id": run_id,
                "trace_id": trace_id,
                "ts_start": started_at,
                "ts_end": utc_now_iso(),
                "surface": "http",
                "mode": "invoke",
                "ok": result.get("ok", False),
                "exit_code": 0 if result.get("ok") else 6,
                "profile": app.active_profile,
                "mount_id": mount.mount_id,
                "stable_name": mount.stable_name,
                "source": mount.source_name,
                "operation_id": mount.operation.id,
                "provider_type": mount.provider_type,
                "summary": mount.summary or mount.operation.title,
                "metadata": {"result": summarize_result(result), "dry_run": dry_run},
            },
        )
        return result

    def _write_json(self, payload: Dict[str, Any], status: HTTPStatus) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length).decode("utf-8")
        if not raw_body.strip():
            return {}
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object.")
        return payload

    def _try_static(self, path: str) -> bool:
        ui_dir = self.server.ui_dir
        if ui_dir is None:
            return False

        base_dir = ui_dir.resolve()
        target = (base_dir / path.lstrip("/")).resolve() if path not in {"", "/"} else base_dir / "index.html"
        if not _is_subpath(target, base_dir):
            return False

        if target.is_dir():
            target = target / "index.html"

        if not target.exists():
            fallback = base_dir / "index.html"
            if not fallback.exists():
                return False
            target = fallback

        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _dispatch_surface_hook(self, event: str, payload: Dict[str, Any]) -> None:
        try:
            self.server.app.dispatch_hooks(event, payload)
        except Exception:
            return None


def _first(query: Dict[str, list[str]], key: str) -> Optional[str]:
    values = query.get(key)
    return values[0] if values else None


def default_ui_dist_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "ui_dist"


def _is_subpath(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
