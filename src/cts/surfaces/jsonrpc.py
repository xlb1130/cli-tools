"""JSON-RPC 2.0 surface for CTS."""

from __future__ import annotations

import json
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional

from cts.app import CTSApp
from cts.execution.logging import emit_app_event
from cts.execution.runtime import build_error_envelope, explain_mount, invoke_mount


class JSONRPCError(Exception):
    """JSON-RPC error."""
    
    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class JSONRPCRequest:
    """JSON-RPC request."""
    
    def __init__(
        self,
        method: str,
        params: Optional[Any] = None,
        request_id: Optional[str] = None,
    ):
        self.method = method
        self.params = params
        self.request_id = request_id
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> JSONRPCRequest:
        """Parse from dictionary."""
        if data.get("jsonrpc") != "2.0":
            raise JSONRPCError(-32600, "Invalid Request: jsonrpc must be '2.0'")
        
        method = data.get("method")
        if not method or not isinstance(method, str):
            raise JSONRPCError(-32600, "Invalid Request: method required")
        
        return cls(
            method=method,
            params=data.get("params"),
            request_id=data.get("id"),
        )


class JSONRPCResponse:
    """JSON-RPC response."""
    
    def __init__(
        self,
        result: Optional[Any] = None,
        error: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        self.result = result
        self.error = error
        self.request_id = request_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        response = {"jsonrpc": "2.0", "id": self.request_id}
        if self.error is not None:
            response["error"] = self.error
        else:
            response["result"] = self.result
        return response


class JSONRPCHandler:
    """Handles JSON-RPC method calls."""
    
    def __init__(self, app: CTSApp):
        self.app = app
        self._methods: Dict[str, Callable] = {}
        self._register_builtin_methods()
    
    def _register_builtin_methods(self) -> None:
        """Register built-in JSON-RPC methods."""
        self.register("system.listMethods", self._list_methods)
        self.register("system.version", self._get_version)
        self.register("app.summary", self._app_summary)
        self.register("app.reload", self._app_reload)
        self.register("sources.list", self._sources_list)
        self.register("sources.get", self._sources_get)
        self.register("sources.test", self._sources_test)
        self.register("mounts.list", self._mounts_list)
        self.register("mounts.get", self._mounts_get)
        self.register("mounts.explain", self._mounts_explain)
        self.register("mounts.invoke", self._mounts_invoke)
        self.register("catalog.export", self._catalog_export)
        self.register("sync.run", self._sync_run)
        self.register("workflow.execute", self._workflow_execute)
    
    def register(self, method: str, handler: Callable) -> None:
        """Register a method handler."""
        self._methods[method] = handler
    
    def handle(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """Handle a JSON-RPC request."""
        try:
            handler = self._methods.get(request.method)
            if not handler:
                raise JSONRPCError(-32601, f"Method not found: {request.method}")
            
            result = handler(request.params)
            return JSONRPCResponse(result=result, request_id=request.request_id)
        
        except JSONRPCError as e:
            return JSONRPCResponse(
                error={"code": e.code, "message": e.message, "data": e.data},
                request_id=request.request_id,
            )
        except Exception as e:
            return JSONRPCResponse(
                error={"code": -32603, "message": "Internal error", "data": str(e)},
                request_id=request.request_id,
            )
    
    def _list_methods(self, params: Optional[Any]) -> List[str]:
        """List available methods."""
        return sorted(self._methods.keys())
    
    def _get_version(self, params: Optional[Any]) -> Dict[str, str]:
        """Get CTS version info."""
        from cts import __version__
        return {"version": __version__, "protocol": "jsonrpc-2.0"}
    
    def _app_summary(self, params: Optional[Any]) -> Dict[str, Any]:
        """Get app summary."""
        from cts.presentation import build_app_summary
        return build_app_summary(self.app)
    
    def _app_reload(self, params: Optional[Any]) -> Dict[str, Any]:
        """Reload app configuration."""
        from cts.app import build_app
        config_path = self.app.explicit_config_path
        profile = self.app.requested_profile
        self.app = build_app(config_path, profile=profile)
        emit_app_event(self.app, event="surface_reload_complete", data={"surface": "jsonrpc"})
        return {"ok": True, "message": "Configuration reloaded"}
    
    def _sources_list(self, params: Optional[Any]) -> List[Dict[str, Any]]:
        """List all sources."""
        from cts.presentation import build_source_summary
        return [
            build_source_summary(self.app, name, source)
            for name, source in self.app.config.sources.items()
        ]
    
    def _sources_get(self, params: Optional[Any]) -> Dict[str, Any]:
        """Get source details."""
        if not params or not isinstance(params, dict):
            raise JSONRPCError(-32602, "Invalid params: source name required")
        
        name = params.get("name")
        if not name:
            raise JSONRPCError(-32602, "Invalid params: name required")
        
        source = self.app.config.sources.get(name)
        if not source:
            raise JSONRPCError(-32602, f"Source not found: {name}")
        
        from cts.presentation import build_source_details
        return build_source_details(self.app, name, source)
    
    def _sources_test(self, params: Optional[Any]) -> Dict[str, Any]:
        """Test source connectivity."""
        if not params or not isinstance(params, dict):
            raise JSONRPCError(-32602, "Invalid params: source name required")
        
        name = params.get("name")
        if not name:
            raise JSONRPCError(-32602, "Invalid params: name required")
        
        source = self.app.config.sources.get(name)
        if not source:
            raise JSONRPCError(-32602, f"Source not found: {name}")
        
        from cts.presentation import build_source_check_result
        return build_source_check_result(self.app, name, source)
    
    def _mounts_list(self, params: Optional[Any]) -> List[Dict[str, Any]]:
        """List all mounts."""
        from cts.presentation import filter_mount_summary
        filters: Dict[str, Any] = {}
        if params and isinstance(params, dict):
            filters = {
                k: v for k, v in params.items()
                if k in ("q", "risk", "source", "surface")
            }
        items: List[Dict[str, Any]] = []
        for mount in self.app.catalog.mounts:
            item = mount.to_summary()
            item["id"] = item["mount_id"]
            item["operation"] = mount.operation.id
            item["supported_surfaces"] = list(mount.operation.supported_surfaces)
            if filter_mount_summary(
                item,
                q=filters.get("q"),
                risk=filters.get("risk"),
                source=filters.get("source"),
                surface=filters.get("surface"),
            ):
                items.append(item)
        return items
    
    def _mounts_get(self, params: Optional[Any]) -> Dict[str, Any]:
        """Get mount details."""
        if not params or not isinstance(params, dict):
            raise JSONRPCError(-32602, "Invalid params: mount_id required")
        
        mount_id = params.get("mount_id")
        if not mount_id:
            raise JSONRPCError(-32602, "Invalid params: mount_id required")
        
        mount = self.app.catalog.find_by_id(mount_id)
        if not mount:
            raise JSONRPCError(-32602, f"Mount not found: {mount_id}")
        
        from cts.presentation import build_mount_details
        return build_mount_details(self.app, mount)
    
    def _mounts_explain(self, params: Optional[Any]) -> Dict[str, Any]:
        """Explain a mount execution plan."""
        if not params or not isinstance(params, dict):
            raise JSONRPCError(-32602, "Invalid params: mount_id required")
        
        mount_id = params.get("mount_id")
        if not mount_id:
            raise JSONRPCError(-32602, "Invalid params: mount_id required")
        
        mount = self.app.catalog.find_by_id(mount_id)
        if not mount:
            raise JSONRPCError(-32602, f"Mount not found: {mount_id}")
        
        args = params.get("args", {})
        runtime = {
            "run_id": str(uuid.uuid4()),
            "trace_id": str(uuid.uuid4()),
            "dry_run": True,
        }
        
        return explain_mount(self.app, mount, args, runtime)
    
    def _mounts_invoke(self, params: Optional[Any]) -> Dict[str, Any]:
        """Invoke a mount."""
        if not params or not isinstance(params, dict):
            raise JSONRPCError(-32602, "Invalid params: mount_id required")
        
        mount_id = params.get("mount_id")
        if not mount_id:
            raise JSONRPCError(-32602, "Invalid params: mount_id required")
        
        mount = self.app.catalog.find_by_id(mount_id)
        if not mount:
            raise JSONRPCError(-32602, f"Mount not found: {mount_id}")
        
        args = params.get("args", {})
        dry_run = params.get("dry_run", False)
        runtime = {
            "run_id": str(uuid.uuid4()),
            "trace_id": str(uuid.uuid4()),
            "dry_run": dry_run,
        }
        
        return invoke_mount(self.app, mount, args, runtime)
    
    def _catalog_export(self, params: Optional[Any]) -> Dict[str, Any]:
        """Export catalog."""
        return self.app.export_catalog()
    
    def _sync_run(self, params: Optional[Any]) -> Dict[str, Any]:
        """Run sync."""
        source_name = None
        if params and isinstance(params, dict):
            source_name = params.get("source")
        
        return self.app.sync(source_name)
    
    def _workflow_execute(self, params: Optional[Any]) -> Dict[str, Any]:
        """Execute a workflow."""
        if not params or not isinstance(params, dict):
            raise JSONRPCError(-32602, "Invalid params: workflow_id and args required")
        
        workflow_id = params.get("workflow_id")
        if not workflow_id:
            raise JSONRPCError(-32602, "Invalid params: workflow_id required")
        
        # Find workflow
        workflow_config = None
        for wf in self.app.config.workflows if hasattr(self.app.config, 'workflows') else []:
            if wf.get("id") == workflow_id:
                workflow_config = wf
                break
        
        if not workflow_config:
            raise JSONRPCError(-32602, f"Workflow not found: {workflow_id}")
        
        from cts.workflow import WorkflowConfig, WorkflowExecutor
        
        workflow = WorkflowConfig.from_dict(workflow_config)
        executor = WorkflowExecutor(self.app)
        
        result = executor.execute(
            workflow,
            params.get("args", {}),
            dry_run=params.get("dry_run", False),
        )
        
        return result.__dict__


class CTSJSONRPCServer(ThreadingHTTPServer):
    """JSON-RPC server for CTS."""
    
    def __init__(self, server_address, RequestHandlerClass, app):  # noqa: N803
        super().__init__(server_address, RequestHandlerClass)
        self.app = app
        self.handler = JSONRPCHandler(app)


def create_jsonrpc_server(app: CTSApp, host: str = "127.0.0.1", port: int = 8788) -> CTSJSONRPCServer:
    """Create a JSON-RPC server."""
    return CTSJSONRPCServer((host, port), JSONRPCRequestHandler, app)


def serve_jsonrpc(app: CTSApp, host: str = "127.0.0.1", port: int = 8788) -> None:
    """Serve JSON-RPC API."""
    server = create_jsonrpc_server(app, host=host, port=port)
    actual_host, actual_port = server.server_address
    print(f"CTS JSON-RPC server running at http://{actual_host}:{actual_port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()


class JSONRPCRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for JSON-RPC."""
    
    server: CTSJSONRPCServer
    
    def do_POST(self) -> None:  # noqa: N802
        """Handle POST request."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
        except Exception as e:
            self._write_error(-32700, f"Parse error: {e}")
            return
        
        # Handle batch requests
        if isinstance(data, list):
            responses = [self._handle_single(req) for req in data]
            self._write_response(responses)
        else:
            response = self._handle_single(data)
            self._write_response(response)
    
    def _handle_single(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a single JSON-RPC request."""
        try:
            request = JSONRPCRequest.from_dict(data)
            response = self.server.handler.handle(request)
            return response.to_dict()
        except JSONRPCError as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": e.code, "message": e.message, "data": e.data},
                "id": data.get("id"),
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": "Internal error", "data": str(e)},
                "id": data.get("id"),
            }
    
    def _write_response(self, response: Any) -> None:
        """Write JSON response."""
        body = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def _write_error(self, code: int, message: str) -> None:
        """Write error response."""
        response = {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": None,
        }
        self._write_response(response)
    
    def log_message(self, format, *args):  # noqa: N802
        """Override to suppress default logging."""
        pass
