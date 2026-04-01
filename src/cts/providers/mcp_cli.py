from __future__ import annotations

import json
import locale
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.config.models import SourceConfig
from cts.imports.models import (
    ImportArgumentDescriptor,
    ImportDescriptor,
    ImportFileWrite,
    ImportPlan,
    ImportPostAction,
    ImportRequest,
    ImportWizardDescriptor,
    ImportWizardField,
    ImportWizardStep,
)
from cts.imports.selectors import import_operation_select_arguments, import_operation_select_wizard_fields
from cts.models import ExecutionPlan, InvokeRequest, InvokeResult, OperationDescriptor
from cts.providers.base import ProviderError, build_help_descriptor
from cts.providers.cli import load_manifest, manifest_operations_from_data, operation_from_config


class MCPCLIProvider:
    provider_type = "mcp"

    def describe_import(self, app: "CTSApp") -> ImportDescriptor:
        return ImportDescriptor(
            provider_type=self.provider_type,
            title="MCP Server",
            summary="Import tools from an MCP server.",
            arguments=[
                ImportArgumentDescriptor(name="source_name", kind="argument", value_type="string", required=True),
                ImportArgumentDescriptor(name="server_config", kind="option", value_type="json", flags=["--server-config", "server_config"]),
                ImportArgumentDescriptor(name="server_name", kind="option", value_type="string"),
                ImportArgumentDescriptor(name="config_file", kind="option", value_type="path"),
                ImportArgumentDescriptor(name="under_values", kind="option", value_type="string_list", repeated=True, flags=["--under", "under_values"]),
                *import_operation_select_arguments(),
            ],
            wizard=ImportWizardDescriptor(
                steps=[
                    ImportWizardStep(
                        id="mcp",
                        title="MCP Import",
                        fields=[
                            ImportWizardField(name="source_name", label="Source name", required=True),
                            ImportWizardField(name="server_config", label="Server config JSON", value_type="json"),
                            ImportWizardField(name="server_name", label="Existing server name"),
                            ImportWizardField(name="config_file", label="servers.json path", value_type="path"),
                            ImportWizardField(name="under_text", label="Mount prefix"),
                            *import_operation_select_wizard_fields(),
                        ],
                    )
                ]
            ),
        )

    def plan_import(self, request: ImportRequest, app: "CTSApp") -> ImportPlan:
        values = dict(request.values)
        source_name = request.source_name or str(values.get("source_name") or "")
        server_config = values.get("server_config")
        server_name = values.get("server_name")
        config_file = values.get("config_file")
        if server_config is None and not server_name:
            raise ProviderError("Either server_config or server_name is required")
        if isinstance(server_config, str) and server_config.strip():
            server_config = json.loads(server_config)
        if config_file:
            servers_path = Path(str(config_file))
        else:
            servers_path = Path(str(values.get("__target_dir__") or app.primary_config_dir)) / "servers.json"
        actual_server_name = str(server_name or f"{source_name}-server")
        files_to_write = []
        if server_config is not None:
            files_to_write.append(
                ImportFileWrite(
                    path=str(servers_path),
                    format="json",
                    content={"mcpServers": {actual_server_name: server_config}},
                    merge_strategy="merge_json",
                )
            )
        source_patch = {
            "type": "mcp",
            "adapter": "mcp-cli",
            "config_file": str(servers_path),
            "server": actual_server_name,
            "discovery": {"mode": "live"},
            "imported_cli_groups": [build_mcp_group_help(source_name, actual_server_name)],
        }
        under_values = list(values.get("under_values") or shlex.split(str(values.get("under_text") or "")))
        preview = {
            "ok": True,
            "action": "import_mcp_preview",
            "apply_action": "import_mcp_apply",
            "source_name": source_name,
            "server_name": actual_server_name,
            "config_file": str(servers_path),
            "servers_file": str(servers_path),
            "under": under_values,
        }
        operation_select = dict(request.operation_select)
        return ImportPlan(
            provider_type=self.provider_type,
            source_name=source_name,
            summary=f"Import MCP source '{source_name}'",
            source_patch=source_patch,
            operation_select=operation_select,
            files_to_write=files_to_write,
            post_compile_actions=[
                ImportPostAction(action="sync_source", payload={"source_name": source_name}),
                ImportPostAction(
                    action="create_mounts_from_source_operations",
                    payload={
                        "source_name": source_name,
                        "under": under_values or [source_name],
                        "select": operation_select,
                    },
                ),
            ],
            preview=preview,
            runtime_data={
                "progress_labels": {
                    "files_to_write": "Writing server config",
                    "compile": "Compiling source config",
                    "sync_source": "Discovering tools",
                    "create_mounts_from_source_operations": "Creating mounts",
                }
            },
        )

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

        timeout_seconds = request.timeout_seconds or source_config.reliability.get("timeout_seconds")
        try:
            data = _invoke_command(plan.rendered_request["argv"], plan.rendered_request["strategy"], timeout_seconds)
            strategy_used = plan.rendered_request["strategy"]
            argv_used = plan.rendered_request["argv"]
        except ProviderError as exc:
            if not _should_retry_with_bridge(plan.rendered_request["strategy"], str(exc)):
                raise
            bridge_argv = _build_bridge_argv(
                source_config,
                app,
                plan.rendered_request.get("primitive_type"),
                plan.rendered_request.get("target"),
                plan.rendered_request.get("args") or {},
            )
            data = _invoke_command(bridge_argv, "node-bridge", timeout_seconds)
            strategy_used = "node-bridge"
            argv_used = bridge_argv

        return InvokeResult(
            ok=True,
            status_code=0,
            data=data,
            metadata={
                "provider_type": self.provider_type,
                "argv": argv_used,
                "strategy": strategy_used,
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


def _mcp_group_summary(source_name: str, server_name: str) -> str:
    if server_name == source_name:
        return f"MCP tools for '{source_name}'"
    return f"MCP tools for '{source_name}' from '{server_name}'"


def _mcp_group_description(source_name: str, server_name: str) -> str:
    if server_name == source_name:
        return f"Tools imported from MCP source '{source_name}'."
    return f"Tools imported from MCP source '{source_name}' using server '{server_name}'."


def build_mcp_group_help(
    source_name: str,
    server_name: str,
    *,
    server_info: Optional[Dict[str, Any]] = None,
    instructions: Optional[str] = None,
) -> Dict[str, Any]:
    instructions_text = str(instructions or "").strip()
    if instructions_text:
        return {
            "path": [source_name],
            "summary": _first_summary_line(instructions_text),
            "description": instructions_text,
        }

    server_display_name = str((server_info or {}).get("name") or "").strip()
    if server_display_name:
        return {
            "path": [source_name],
            "summary": server_display_name,
            "description": _mcp_group_description(source_name, server_display_name),
        }

    return {
        "path": [source_name],
        "summary": _mcp_group_summary(source_name, server_name),
        "description": _mcp_group_description(source_name, server_name),
    }


def build_mcp_group_help_from_discovery(
    source_name: str,
    source_config: Dict[str, Any],
    discovery: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    server_name = str(source_config.get("server") or source_name)
    discovery_payload = discovery if isinstance(discovery, dict) else {}
    return build_mcp_group_help(
        source_name,
        server_name,
        server_info=discovery_payload.get("server_info"),
        instructions=discovery_payload.get("instructions"),
    )


def _first_summary_line(text: str, limit: int = 80) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return "MCP tools"
    return first_line if len(first_line) <= limit else first_line[: limit - 1].rstrip() + "..."


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
    completed = _run_command(argv, timeout_seconds=timeout_seconds)
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
        completed = _run_command(
            [npm, "install", "--no-audit", "--no-fund", "--omit=dev"],
            cwd=runtime_dir,
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


def _invoke_command(argv: List[str], strategy: str, timeout_seconds: Optional[int]) -> Any:
    completed = _run_command(argv, timeout_seconds=timeout_seconds)

    if completed.returncode != 0:
        error_text = completed.stderr.strip() or completed.stdout.strip() or "MCP command failed"
        raise ProviderError(error_text)

    parsed = _parse_json_output(completed.stdout)
    if strategy == "node-bridge":
        return parsed.get("result") if isinstance(parsed, dict) and parsed.get("ok") else parsed
    return parsed


def _should_retry_with_bridge(strategy: str, error_text: str) -> bool:
    if strategy != "mcp-cli":
        return False

    normalized = error_text.lower()
    compatibility_markers = (
        "server_not_found",
        "server \"call-tool\" not found",
        "server 'call-tool' not found",
        "available servers:",
        "use one of:",
        "spawn call-tool enoent",
    )
    return any(marker in normalized for marker in compatibility_markers)


def _kind_for_primitive(primitive_type: str) -> str:
    if primitive_type == "tool":
        return "action"
    if primitive_type == "prompt":
        return "prompt"
    return "query"


def _sanitize_identifier(value: str) -> str:
    return value.replace("://", "_").replace("/", "_").replace(":", "_").replace(".", "_").replace("-", "_")


def _run_command(
    argv: List[str],
    *,
    cwd: Optional[Path] = None,
    timeout_seconds: Optional[int] = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=False,
        timeout=timeout_seconds,
        check=False,
    )
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        _decode_subprocess_output(completed.stdout),
        _decode_subprocess_output(completed.stderr),
    )


def _decode_subprocess_output(payload: Optional[bytes]) -> str:
    if payload is None:
        return ""
    if not payload:
        return ""

    preferred_encoding = locale.getpreferredencoding(False) or "utf-8"
    for encoding in ("utf-8", preferred_encoding, "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _should_use_live_discovery(source_config: SourceConfig) -> bool:
    mode = source_config.discovery.mode
    return mode in {"live", "import", "hybrid"} or bool(source_config.url) or bool(source_config.config_file)


def _dedupe_operations(operations: List[OperationDescriptor]) -> List[OperationDescriptor]:
    seen: Dict[str, OperationDescriptor] = {}
    for operation in operations:
        seen[operation.id] = operation
    return list(seen.values())
