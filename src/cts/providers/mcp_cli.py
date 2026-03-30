from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.config.models import SourceConfig
from cts.models import ExecutionPlan, InvokeRequest, InvokeResult, OperationDescriptor
from cts.providers.base import ProviderError, build_help_descriptor
from cts.providers.cli import load_manifest, manifest_operations_from_data, operation_from_config


class MCPCLIProvider:
    provider_type = "mcp"

    def discover(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> List[OperationDescriptor]:
        operations: List[OperationDescriptor] = []
        manifest_loaded = False

        if source_config.discovery.manifest:
            manifest = app.resolve_path(source_config.discovery.manifest, owner=source_config)
            if manifest.exists():
                operations.extend(manifest_operations_from_data(source_name, self.provider_type, load_manifest(manifest)))
                manifest_loaded = True

        if _should_use_live_discovery(source_config) and not manifest_loaded and getattr(app, "compile_mode", "full") != "help":
            try:
                payload = _run_bridge_command(
                    source_config,
                    app,
                    "list-primitives",
                    timeout_seconds=source_config.reliability.get("timeout_seconds"),
                )
                operations.extend(_operations_from_bridge_payload(source_name, payload))
            except Exception as exc:
                raise ProviderError(f"MCP discovery failed for source '{source_name}': {exc}") from exc

        for operation_id, operation in source_config.operations.items():
            operations.append(operation_from_config(source_name, self.provider_type, operation_id, operation))

        return _dedupe_operations(operations)

    def get_operation(
        self,
        source_name: str,
        source_config: SourceConfig,
        operation_id: str,
        app: "CTSApp",
    ) -> Optional[OperationDescriptor]:
        return app.source_operations.get(source_name, {}).get(operation_id)

    def get_schema(
        self,
        source_name: str,
        source_config: SourceConfig,
        operation_id: str,
        app: "CTSApp",
    ) -> Optional[tuple]:
        operation = self.get_operation(source_name, source_config, operation_id, app)
        if not operation:
            return None
        return operation.input_schema, {
            "strategy": "probed" if operation.provider_config.get("discovered_via") == "mcp_bridge" else "manual",
            "origin": operation.provider_config.get("discovered_origin", "mcp"),
            "confidence": 0.95 if operation.provider_config.get("discovered_via") == "mcp_bridge" else 0.7,
        }

    def get_help(
        self,
        source_name: str,
        source_config: SourceConfig,
        operation_id: str,
        app: "CTSApp",
    ):
        operation = self.get_operation(source_name, source_config, operation_id, app)
        if not operation:
            return None
        help_descriptor = build_help_descriptor(operation)
        primitive_type = operation.provider_config.get("mcp_primitive_type")
        server = source_config.server or source_name
        if primitive_type:
            help_descriptor.notes.append(f"MCP primitive: {primitive_type}")
        help_descriptor.notes.append(f"MCP server: {server}")
        return help_descriptor

    def refresh_auth(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Optional[Dict]:
        return None

    def plan(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> ExecutionPlan:
        operation = self.get_operation(source_name, source_config, request.operation_id, app)
        if not operation:
            raise ProviderError(f"operation not found: {source_name}.{request.operation_id}")

        primitive_type = operation.provider_config.get("mcp_primitive_type", "tool")
        target = operation.provider_config.get("mcp_target") or operation.id
        transport_type = _resolve_transport_type(source_config, app)
        rendered_request: Dict[str, Any] = {
            "adapter": source_config.adapter or "mcp-cli",
            "server": source_config.server or source_name,
            "transport_type": transport_type,
            "primitive_type": primitive_type,
            "target": target,
            "args": dict(request.args),
        }

        server_config = _load_server_config(source_config, app)
        use_native_mcp_cli = (
            primitive_type in {"tool", "resource", "prompt"}
            and server_config is not None
            and _supports_mcp_cli_noninteractive(server_config)
        )

        if use_native_mcp_cli:
            rendered_request["strategy"] = "mcp-cli"
            rendered_request["argv"] = _build_mcp_cli_argv(
                source_config,
                app,
                primitive_type,
                target,
                request.args,
            )
        else:
            rendered_request["strategy"] = "node-bridge"
            rendered_request["argv"] = _build_bridge_argv(
                source_config,
                app,
                primitive_type,
                target,
                request.args,
            )

        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk=operation.risk,
            rendered_request=rendered_request,
        )

    def invoke(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> InvokeResult:
        plan = self.plan(source_name, source_config, request, app)
        if request.dry_run:
            return InvokeResult(
                ok=True,
                data={"dry_run": True, "plan": plan.model_dump(mode="json")},
                metadata={"provider_type": self.provider_type},
            )

        completed = subprocess.run(
            plan.rendered_request["argv"],
            capture_output=True,
            text=True,
            timeout=request.timeout_seconds or source_config.reliability.get("timeout_seconds"),
            check=False,
        )

        if completed.returncode != 0:
            error_text = completed.stderr.strip() or completed.stdout.strip() or "MCP command failed"
            raise ProviderError(error_text)

        parsed = _parse_json_output(completed.stdout)
        if plan.rendered_request["strategy"] == "node-bridge":
            data = parsed.get("result") if isinstance(parsed, dict) and parsed.get("ok") else parsed
        else:
            data = parsed

        return InvokeResult(
            ok=True,
            status_code=0,
            data=data,
            metadata={
                "provider_type": self.provider_type,
                "argv": plan.rendered_request["argv"],
                "strategy": plan.rendered_request["strategy"],
                "transport_type": plan.rendered_request.get("transport_type"),
            },
        )

    def healthcheck(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Dict[str, Any]:
        mcp_cli_path = _resolve_mcp_cli_binary(source_config)
        bridge_script = _bridge_script_path()
        return {
            "ok": bool(source_config.config_file or source_config.url or source_config.server or source_config.discovery.manifest),
            "provider_type": self.provider_type,
            "adapter": source_config.adapter or "mcp-cli",
            "mcp_cli_available": bool(mcp_cli_path),
            "node_available": shutil.which("node") is not None,
            "bridge_script": str(bridge_script),
            "bridge_script_exists": bridge_script.exists(),
            "server": source_config.server,
            "transport_type": _resolve_transport_type(source_config, app),
        }


def _operations_from_bridge_payload(source_name: str, payload: Dict[str, Any]) -> List[OperationDescriptor]:
    operations: List[OperationDescriptor] = []
    for primitive in payload.get("primitives", []):
        primitive_type = primitive.get("primitive_type")
        if primitive_type == "resource-template":
            continue

        name = primitive.get("name")
        target = primitive.get("target") or name
        operation_id = name if primitive_type == "tool" else f"{primitive_type}.{_sanitize_identifier(str(target))}"
        description = primitive.get("description")
        input_schema = primitive.get("input_schema") or {"type": "object", "properties": {}}
        stable_name = f"{source_name}.{primitive_type}.{_sanitize_identifier(name)}".replace("_", ".")

        operations.append(
            OperationDescriptor(
                id=operation_id,
                source=source_name,
                provider_type="mcp",
                title=name,
                stable_name=stable_name,
                description=description,
                kind=_kind_for_primitive(primitive_type),
                risk="read",
                input_schema=input_schema,
                output_schema=None,
                supported_surfaces=["cli", "invoke", "mcp"],
                provider_config={
                    "mcp_primitive_type": primitive_type,
                    "mcp_target": target,
                    "discovered_via": "mcp_bridge",
                    "discovered_origin": payload.get("server"),
                    "transport_type": payload.get("transport_type"),
                    "raw": primitive.get("raw"),
                },
            )
        )
    return operations


def _run_bridge_command(
    source_config: SourceConfig,
    app: "CTSApp",
    command: str,
    primitive_type: Optional[str] = None,
    target: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    argv = _build_bridge_argv(source_config, app, primitive_type, target, args or {}, command=command)
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        error_text = completed.stderr.strip() or completed.stdout.strip() or "MCP bridge command failed"
        raise ProviderError(error_text)
    return _parse_json_output(completed.stdout)


def _build_bridge_argv(
    source_config: SourceConfig,
    app: "CTSApp",
    primitive_type: Optional[str],
    target: Optional[str],
    args: Dict[str, Any],
    command: Optional[str] = None,
) -> List[str]:
    action = command or _bridge_command_for_primitive(primitive_type)
    argv = ["node", str(_bridge_launch_script_path()), action]

    if source_config.config_file and source_config.server:
        argv.extend(
            [
                "--config",
                str(app.resolve_path(source_config.config_file, owner=source_config)),
                "--server",
                source_config.server,
            ]
        )
    elif source_config.url:
        argv.extend(
            [
                "--url",
                source_config.url,
                "--transport",
                (source_config.transport_type or "streamable_http"),
                "--server",
                source_config.server or "remote",
            ]
        )
    else:
        raise ProviderError("MCP source requires config_file+server or direct url")

    if primitive_type == "tool" and target:
        argv.extend(["--tool", target, "--args", json.dumps(args, ensure_ascii=False)])
    elif primitive_type == "resource" and target:
        argv.extend(["--uri", target])
    elif primitive_type == "prompt" and target:
        argv.extend(["--prompt", target, "--args", json.dumps(args, ensure_ascii=False)])

    return argv


def _build_mcp_cli_argv(
    source_config: SourceConfig,
    app: "CTSApp",
    primitive_type: str,
    target: str,
    args: Dict[str, Any],
) -> List[str]:
    config_file = source_config.config_file
    server = source_config.server
    if not config_file or not server:
        raise ProviderError("mcp-cli mode requires config_file and server")

    command = _mcp_cli_command_for_primitive(primitive_type)
    argv = [
        _resolve_mcp_cli_binary(source_config) or "mcp-cli",
        "-c",
        str(app.resolve_path(config_file)),
        
        command,
        f"{server}:{target}",
    ]
    if primitive_type in {"tool", "prompt"} and args:
        argv.extend(["--args", json.dumps(args, ensure_ascii=False)])
    return argv


def _load_server_config(source_config: SourceConfig, app: "CTSApp") -> Optional[Dict[str, Any]]:
    if not source_config.config_file or not source_config.server:
        return None
    try:
        config = json.loads(app.resolve_path(source_config.config_file, owner=source_config).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise ProviderError(f"invalid MCP config file: {exc}") from exc
    return config.get("mcpServers", {}).get(source_config.server)


def _resolve_transport_type(source_config: SourceConfig, app: "CTSApp") -> str:
    server_config = _load_server_config(source_config, app)
    if server_config:
        return str(server_config.get("type") or ("streamable_http" if server_config.get("url") else "stdio")).lower()
    if source_config.transport_type:
        return source_config.transport_type
    if source_config.url:
        return "streamable_http"
    return "stdio"


def _supports_mcp_cli_noninteractive(server_config: Dict[str, Any]) -> bool:
    transport_type = str(server_config.get("type") or ("streamable_http" if server_config.get("url") else "stdio")).lower()
    # Prefer the Node bridge for streamable_http because some mcp-cli builds
    # fail non-interactive tool calls on remote HTTP transports.
    return transport_type in {"stdio", "sse"} and (
        transport_type == "stdio" and bool(server_config.get("command")) or
        transport_type == "sse" and bool(server_config.get("url"))
    )


def _resolve_mcp_cli_binary(source_config: SourceConfig) -> Optional[str]:
    adapter = source_config.adapter or "mcp-cli"
    if shutil.which(adapter):
        return adapter
    npm_bin = Path.home() / ".nvm" / "versions" / "node"
    if npm_bin.exists():
        matches = sorted(npm_bin.glob("*/bin/mcp-cli"))
        if matches:
            return str(matches[-1])
    return None


def _bridge_script_path() -> Path:
    current = Path(__file__).resolve()
    candidates = [
        Path.cwd() / "scripts" / "mcp_bridge.mjs",  # local workspace with node_modules
        current.parents[1] / "scripts" / "mcp_bridge.mjs",  # packaged with cts
        current.parents[3] / "scripts" / "mcp_bridge.mjs",  # source tree / legacy layout
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _bridge_launch_script_path() -> Path:
    script_path = _bridge_script_path()
    if _bridge_dependency_available(script_path):
        return script_path
    runtime_dir = _bridge_runtime_root()
    return _ensure_bridge_runtime(script_path, runtime_dir)


def _bridge_dependency_available(script_path: Path) -> bool:
    return _find_bridge_dependency_dir(script_path) is not None


def _find_bridge_dependency_dir(script_path: Path) -> Optional[Path]:
    current = script_path.parent
    package_dir = Path("@modelcontextprotocol/sdk")
    while True:
        candidate = current / "node_modules" / package_dir
        if candidate.exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _bridge_runtime_root() -> Path:
    return Path("~/.local/share/cts/node-bridge").expanduser()


def _ensure_bridge_runtime(script_path: Path, runtime_dir: Path) -> Path:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_script = runtime_dir / script_path.name
    shutil.copy2(script_path, runtime_script)

    package_json = script_path.with_name("package.json")
    runtime_package_json = runtime_dir / "package.json"
    if package_json.exists():
        shutil.copy2(package_json, runtime_package_json)
    elif not runtime_package_json.exists():
        runtime_package_json.write_text(
            json.dumps(
                {
                    "private": True,
                    "type": "module",
                    "dependencies": {"@modelcontextprotocol/sdk": "^1.28.0"},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    if not _bridge_dependency_available(runtime_script):
        npm = shutil.which("npm")
        if not npm:
            raise ProviderError(
                "MCP bridge requires npm to auto-install '@modelcontextprotocol/sdk', but npm was not found in PATH"
            )
        completed = subprocess.run(
            [npm, "install", "--no-audit", "--no-fund", "--omit=dev"],
            cwd=runtime_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            error_text = completed.stderr.strip() or completed.stdout.strip() or "npm install failed for MCP bridge runtime"
            raise ProviderError(f"failed to prepare MCP bridge runtime: {error_text}")

    return runtime_script


def _bridge_command_for_primitive(primitive_type: Optional[str]) -> str:
    mapping = {
        "tool": "call-tool",
        "resource": "read-resource",
        "prompt": "get-prompt",
    }
    if primitive_type not in mapping:
        raise ProviderError(f"unsupported MCP primitive type: {primitive_type}")
    return mapping[primitive_type]


def _mcp_cli_command_for_primitive(primitive_type: str) -> str:
    mapping = {
        "tool": "call-tool",
        "resource": "read-resource",
        "prompt": "get-prompt",
    }
    if primitive_type not in mapping:
        raise ProviderError(f"unsupported MCP primitive type for mcp-cli: {primitive_type}")
    return mapping[primitive_type]


def _parse_json_output(output: str) -> Dict[str, Any]:
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"failed to parse JSON output from MCP command: {exc}") from exc


def _kind_for_primitive(primitive_type: str) -> str:
    if primitive_type == "tool":
        return "action"
    if primitive_type == "prompt":
        return "prompt"
    return "query"


def _sanitize_identifier(value: str) -> str:
    return value.replace("://", "_").replace("/", "_").replace(":", "_").replace(".", "_").replace("-", "_")


def _should_use_live_discovery(source_config: SourceConfig) -> bool:
    mode = source_config.discovery.mode
    return mode in {"live", "import", "hybrid"} or bool(source_config.url) or bool(source_config.config_file)


def _dedupe_operations(operations: List[OperationDescriptor]) -> List[OperationDescriptor]:
    seen: Dict[str, OperationDescriptor] = {}
    for operation in operations:
        seen[operation.id] = operation
    return list(seen.values())
