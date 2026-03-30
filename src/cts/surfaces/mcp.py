"""MCP Bridge surface for CTS.

This module provides an MCP (Model Context Protocol) server that exposes
CTS mounts as MCP tools, allowing MCP clients to invoke CTS capabilities.
"""

from __future__ import annotations

import json
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

from cts.app import CTSApp
from cts.execution.logging import emit_app_event
from cts.execution.runtime import invoke_mount


class MCPTool:
    """Represents an MCP tool definition."""
    
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        mount_id: str,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.mount_id = mount_id
    
    def to_mcp_format(self) -> Dict[str, Any]:
        """Convert to MCP tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class MCPBridge:
    """Bridge between CTS and MCP protocol."""
    
    def __init__(self, app: CTSApp):
        self.app = app
        self._tools: Dict[str, MCPTool] = {}
        self._build_tools()
    
    def _build_tools(self) -> None:
        """Build MCP tools from CTS mounts."""
        for mount in self.app.catalog.mounts:
            # Only expose mounts that are configured for MCP surface
            surfaces = getattr(mount, "supported_surfaces", []) or []
            if "mcp" not in surfaces and "invoke" not in surfaces:
                continue
            
            tool_name = self._make_tool_name(mount)
            description = mount.operation.title or mount.operation.summary or f"Execute {mount.mount_id}"
            
            # Build input schema
            input_schema = self._build_input_schema(mount)
            
            self._tools[tool_name] = MCPTool(
                name=tool_name,
                description=description,
                input_schema=input_schema,
                mount_id=mount.mount_id,
            )
    
    def _make_tool_name(self, mount) -> str:
        """Create a valid MCP tool name from mount."""
        # Use stable_name if available, otherwise derive from mount_id
        if mount.stable_name:
            return mount.stable_name.replace(".", "_").replace("-", "_")
        return mount.mount_id.replace(".", "_").replace("-", "_")
    
    def _build_input_schema(self, mount) -> Dict[str, Any]:
        """Build JSON Schema for tool input."""
        schema = mount.operation.input_schema or {}
        
        # Ensure it's a valid JSON Schema for MCP
        if not schema:
            schema = {"type": "object", "properties": {}, "required": []}
        
        if "type" not in schema:
            schema["type"] = "object"
        
        return schema
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available MCP tools."""
        return [tool.to_mcp_format() for tool in self._tools.values()]
    
    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def invoke_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke an MCP tool."""
        tool = self._tools.get(name)
        if not tool:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Tool not found: {name}"}],
            }
        
        mount = self.app.catalog.find_by_id(tool.mount_id)
        if not mount:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Mount not found: {tool.mount_id}"}],
            }
        
        try:
            runtime = {
                "run_id": str(uuid.uuid4()),
                "trace_id": str(uuid.uuid4()),
                "dry_run": False,
            }
            
            result = invoke_mount(self.app, mount, arguments, runtime)
            
            if result.get("ok"):
                return {
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result.get("data", {}), ensure_ascii=False, indent=2),
                        }
                    ],
                }
            else:
                error = result.get("error", {})
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error: {error.get('message', 'Unknown error')}",
                        }
                    ],
                }
        
        except Exception as e:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Exception: {str(e)}"}],
            }


class MCPServer:
    """MCP Server implementation for CTS."""
    
    def __init__(self, app: CTSApp):
        self.app = app
        self.bridge = MCPBridge(app)
        self._server_info = {
            "name": "cts-mcp-bridge",
            "version": "1.0.0",
        }
        self._capabilities = {
            "tools": {},
        }
    
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an MCP request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")
        
        handler = getattr(self, f"_handle_{method.replace('/', '_')}", None)
        if not handler:
            return self._error_response(request_id, -32601, f"Method not found: {method}")
        
        try:
            result = handler(params)
            return self._success_response(request_id, result)
        except Exception as e:
            return self._error_response(request_id, -32603, str(e))
    
    def _success_response(self, request_id: Any, result: Any) -> Dict[str, Any]:
        """Create a success response."""
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    
    def _error_response(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    
    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": self._server_info,
            "capabilities": self._capabilities,
        }
    
    def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request."""
        return {"tools": self.bridge.list_tools()}
    
    def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        name = params.get("name")
        if not name:
            raise ValueError("Tool name required")
        
        arguments = params.get("arguments", {})
        return self.bridge.invoke_tool(name, arguments)
    
    def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping request."""
        return {}


class CTSMCPServer(ThreadingHTTPServer):
    """HTTP server for MCP."""
    
    def __init__(self, server_address, RequestHandlerClass, app):  # noqa: N803
        super().__init__(server_address, RequestHandlerClass)
        self.app = app
        self.mcp_server = MCPServer(app)


def create_mcp_server(app: CTSApp, host: str = "127.0.0.1", port: int = 8789) -> CTSMCPServer:
    """Create an MCP server."""
    return CTSMCPServer((host, port), MCPRequestHandler, app)


def serve_mcp(app: CTSApp, host: str = "127.0.0.1", port: int = 8789) -> None:
    """Serve MCP API."""
    server = create_mcp_server(app, host=host, port=port)
    actual_host, actual_port = server.server_address
    print(f"CTS MCP server running at http://{actual_host}:{actual_port}")
    emit_app_event(app, event="mcp_server_start", data={"host": actual_host, "port": actual_port})
    try:
        server.serve_forever()
    finally:
        server.server_close()


class MCPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for MCP."""
    
    server: CTSMCPServer
    
    def do_GET(self) -> None:  # noqa: N802
        """Handle GET request (SSE endpoint)."""
        if self.path == "/sse":
            self._handle_sse()
        elif self.path == "/health":
            self._handle_health()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
    
    def do_POST(self) -> None:  # noqa: N802
        """Handle POST request."""
        if self.path in ["/", "/mcp", "/message"]:
            self._handle_message()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
    
    def _handle_message(self) -> None:
        """Handle MCP message."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            request = json.loads(body)
        except Exception as e:
            self._write_error(-32700, f"Parse error: {e}")
            return
        
        response = self.server.mcp_server.handle_request(request)
        self._write_json(response)
    
    def _handle_sse(self) -> None:
        """Handle SSE connection (for future streaming support)."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        
        # Send initial connection message
        event = f"event: connected\ndata: {{\"server\": \"cts-mcp-bridge\"}}\n\n"
        self.wfile.write(event.encode("utf-8"))
        self.wfile.flush()
    
    def _handle_health(self) -> None:
        """Handle health check."""
        self._write_json({"status": "ok", "server": "cts-mcp-bridge"})
    
    def _write_json(self, data: Any) -> None:
        """Write JSON response."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
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
        self._write_json(response)
    
    def log_message(self, format, *args):  # noqa: N802
        """Override to suppress default logging."""
        pass
