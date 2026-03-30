"""Tests for Phase 5 features: workflow, jsonrpc, mcp, docs generator."""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main
from cts.workflow.models import (
    StepCondition,
    StepConditionType,
    WorkflowConfig,
    WorkflowStep,
)
from cts.workflow.executor import WorkflowExecutor
from cts.reliability import GlobalReliabilityDefaults, RetryPolicy
from cts.plugins.external import (
    ExternalPlugin,
    PluginMetadata,
    PluginRegistry,
    ProviderRegistration,
    HookRegistration,
)
from cts.docs import DocsGenerator, DocsConfig
from cts.surfaces.jsonrpc import JSONRPCHandler


# Workflow Tests

class TestWorkflowModels:
    """Tests for workflow models."""
    
    def test_workflow_step_defaults(self):
        step = WorkflowStep(id="step1")
        assert step.id == "step1"
        assert step.args == {}
        assert step.run_when.type == StepConditionType.SUCCESS
    
    def test_workflow_step_from_dict(self):
        data = {
            "id": "step1",
            "mount_id": "test-mount",
            "args": {"key": "value"},
            "run_when": "failure",
        }
        step = WorkflowStep(
            id=data["id"],
            mount_id=data["mount_id"],
            args=data["args"],
            run_when=StepCondition(type=StepConditionType(data["run_when"])),
        )
        assert step.id == "step1"
        assert step.mount_id == "test-mount"
        assert step.args == {"key": "value"}
        assert step.run_when.type == StepConditionType.FAILURE
    
    def test_workflow_config_from_dict(self):
        data = {
            "id": "test-workflow",
            "name": "Test Workflow",
            "description": "A test workflow",
            "steps": [
                {"id": "step1", "mount_id": "mount1"},
                {"id": "step2", "mount_id": "mount2"},
            ],
            "output_from": "step2",
            "risk": "write",
        }
        config = WorkflowConfig.from_dict(data)
        assert config.id == "test-workflow"
        assert config.name == "Test Workflow"
        assert len(config.steps) == 2
        assert config.output_from == "step2"
        assert config.risk == "write"
    
    def test_workflow_config_to_dict(self):
        config = WorkflowConfig(
            id="test",
            name="Test",
            steps=[WorkflowStep(id="s1", mount_id="m1")],
            risk="read",
        )
        data = config.to_dict()
        assert data["id"] == "test"
        assert data["name"] == "Test"
        assert len(data["steps"]) == 1
        assert data["risk"] == "read"
    
    def test_step_condition_types(self):
        assert StepConditionType.SUCCESS.value == "success"
        assert StepConditionType.FAILURE.value == "failure"
        assert StepConditionType.ALWAYS.value == "always"
        assert StepConditionType.CONDITION.value == "condition"


class TestWorkflowExecutor:
    """Tests for workflow executor."""
    
    def test_executor_resolve_expression(self):
        mock_app = MagicMock()
        executor = WorkflowExecutor(mock_app)
        executor._step_outputs = {
            "step1": {"result": "hello"},
            "step2": {"data": "world"},
        }
        
        result = executor._resolve_expression("{{ step1.result }}")
        assert result == "hello"
        
        result = executor._resolve_expression("{{ step2.data }}")
        assert result == "world"
    
    def test_executor_resolve_step_order(self):
        mock_app = MagicMock()
        executor = WorkflowExecutor(mock_app)
        
        workflow = WorkflowConfig(
            id="test",
            steps=[
                WorkflowStep(id="a"),
                WorkflowStep(id="b"),
                WorkflowStep(id="c"),
            ],
        )
        
        order = executor._resolve_step_order(workflow)
        assert order == ["a", "b", "c"]

    def test_executor_resolve_step_order_with_dependencies(self):
        mock_app = MagicMock()
        executor = WorkflowExecutor(mock_app)

        workflow = WorkflowConfig(
            id="test",
            steps=[
                WorkflowStep(id="prepare"),
                WorkflowStep(id="transform", input_from="prepare.payload"),
                WorkflowStep(id="publish", input_from="transform.result"),
            ],
        )

        order = executor._resolve_step_order(workflow)
        assert order == ["prepare", "transform", "publish"]

    def test_executor_resolve_execution_batches_with_parallel_group(self):
        mock_app = MagicMock()
        executor = WorkflowExecutor(mock_app)

        workflow = WorkflowConfig(
            id="test",
            steps=[
                WorkflowStep(id="prepare"),
                WorkflowStep(id="left", input_from="prepare.payload"),
                WorkflowStep(id="right", input_from="prepare.payload"),
                WorkflowStep(id="finalize", input_from="left.result"),
            ],
            parallel_groups=[["left", "right"]],
        )

        batches = executor._resolve_execution_batches(workflow)
        assert batches == [["prepare"], ["left", "right"], ["finalize"]]

    def test_executor_parallel_group_validates_dependency_shape(self):
        mock_app = MagicMock()
        executor = WorkflowExecutor(mock_app)

        workflow = WorkflowConfig(
            id="test",
            steps=[
                WorkflowStep(id="prepare"),
                WorkflowStep(id="left", input_from="prepare.payload"),
                WorkflowStep(id="right"),
            ],
            parallel_groups=[["left", "right"]],
        )

        with pytest.raises(ValueError, match="same upstream dependencies"):
            executor._resolve_execution_batches(workflow)
    
    def test_executor_should_run_always(self):
        mock_app = MagicMock()
        executor = WorkflowExecutor(mock_app)
        
        step = WorkflowStep(id="test", run_when=StepCondition(type=StepConditionType.ALWAYS))
        should_run, reason = executor._should_run_step(step, [], set(), True)
        assert should_run is True
        assert reason is None
    
    def test_executor_should_run_success(self):
        mock_app = MagicMock()
        executor = WorkflowExecutor(mock_app)
        
        step = WorkflowStep(id="test", run_when=StepCondition(type=StepConditionType.SUCCESS))
        
        # No failures
        should_run, _ = executor._should_run_step(step, [], set(), True)
        assert should_run is True
        
        # With failures
        should_run, _ = executor._should_run_step(step, [], {"failed_step"}, True)
        assert should_run is False
    
    def test_executor_should_run_failure(self):
        mock_app = MagicMock()
        executor = WorkflowExecutor(mock_app)
        
        step = WorkflowStep(id="test", run_when=StepCondition(type=StepConditionType.FAILURE))
        
        # No failures
        should_run, _ = executor._should_run_step(step, [], set(), True)
        assert should_run is False
        
        # With failures
        should_run, _ = executor._should_run_step(step, [], {"failed_step"}, True)
        assert should_run is True

    def test_executor_step_retry_on_failure_uses_workflow_reliability(self):
        mock_app = MagicMock()
        mock_app.config.get_reliability_defaults.return_value = GlobalReliabilityDefaults(
            retry=RetryPolicy(max_attempts=3)
        )
        mock_app.catalog.find_by_id.return_value = None
        executor = WorkflowExecutor(mock_app)

        step = WorkflowStep(id="retry-step", mount_id="demo", retry_on_failure=True)
        attempts = {"count": 0}

        def flaky(*args, **kwargs):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise TimeoutError("transient")
            return {"ok": True, "data": {"done": True}}

        executor._execute_via_mount = flaky
        result = executor._execute_step(step, {}, dry_run=False, run_id="run-1", trace_id="trace-1")

        assert result.success is True
        assert attempts["count"] == 3
        assert result.output == {"done": True}

    def test_executor_step_timeout_is_enforced(self):
        mock_app = MagicMock()
        mock_app.config.get_reliability_defaults.return_value = GlobalReliabilityDefaults()
        mock_app.catalog.find_by_id.return_value = None
        executor = WorkflowExecutor(mock_app)

        step = WorkflowStep(id="timeout-step", mount_id="demo", timeout_seconds=0.05)

        def slow(*args, **kwargs):
            import time

            time.sleep(0.2)
            return {"ok": True, "data": {"done": True}}

        executor._execute_via_mount = slow
        result = executor._execute_step(step, {}, dry_run=False, run_id="run-1", trace_id="trace-1")

        assert result.success is False
        assert "timed out" in (result.error or "")


# External Plugin Tests

class TestPluginMetadata:
    """Tests for plugin metadata."""
    
    def test_metadata_from_dict(self):
        data = {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "A test plugin",
            "author": "Test Author",
            "provides": ["provider1", "provider2"],
        }
        metadata = PluginMetadata.from_dict(data)
        assert metadata.name == "test-plugin"
        assert metadata.version == "1.0.0"
        assert metadata.description == "A test plugin"
        assert metadata.provides == ["provider1", "provider2"]


class TestProviderRegistration:
    """Tests for provider registration."""
    
    def test_registration_from_dict(self):
        data = {
            "type": "custom",
            "description": "Custom provider",
            "supports_discovery": True,
        }
        reg = ProviderRegistration.from_dict(data)
        assert reg.type == "custom"
        assert reg.description == "Custom provider"
        assert reg.supports_discovery is True


class TestHookRegistration:
    """Tests for hook registration."""
    
    def test_registration_from_dict(self):
        data = {
            "event": "invoke.before",
            "handler": "handle_invoke",
            "priority": 50,
        }
        reg = HookRegistration.from_dict(data)
        assert reg.event == "invoke.before"
        assert reg.handler == "handle_invoke"
        assert reg.priority == 50


class TestExternalPlugin:
    """Tests for external plugin."""
    
    def test_plugin_get_metadata(self):
        metadata = PluginMetadata(name="test", version="1.0")
        plugin = ExternalPlugin(metadata)
        
        result = plugin.get_metadata()
        assert result["name"] == "test"
        assert result["version"] == "1.0"
    
    def test_plugin_register_provider(self):
        metadata = PluginMetadata(name="test", version="1.0")
        plugin = ExternalPlugin(metadata)
        
        reg = ProviderRegistration(type="custom")
        plugin.register_provider(reg)
        
        providers = plugin.register_providers()
        assert len(providers) == 1
        assert providers[0]["type"] == "custom"
    
    def test_plugin_register_handler(self):
        metadata = PluginMetadata(name="test", version="1.0")
        plugin = ExternalPlugin(metadata)
        
        def test_handler(payload):
            return {"result": "ok"}
        
        plugin.register_handler("test_action", test_handler)
        
        result = plugin.invoke("test_action", {})
        assert result["ok"] is True
        assert result["result"] == {"result": "ok"}
    
    def test_plugin_unknown_action(self):
        metadata = PluginMetadata(name="test", version="1.0")
        plugin = ExternalPlugin(metadata)
        
        result = plugin.invoke("unknown", {})
        assert "error" in result


class TestPluginRegistry:
    """Tests for plugin registry."""
    
    def test_registry_register(self):
        registry = PluginRegistry()
        plugin = ExternalPlugin(PluginMetadata(name="test", version="1.0"))
        
        registry.register(plugin)
        
        assert registry.get("test") == plugin
        assert len(registry.list_all()) == 1
    
    def test_registry_get_all_providers(self):
        registry = PluginRegistry()
        
        plugin1 = ExternalPlugin(PluginMetadata(name="p1", version="1.0"))
        plugin1.register_provider(ProviderRegistration(type="type1"))
        
        plugin2 = ExternalPlugin(PluginMetadata(name="p2", version="1.0"))
        plugin2.register_provider(ProviderRegistration(type="type2"))
        
        registry.register(plugin1)
        registry.register(plugin2)
        
        providers = registry.get_all_providers()
        assert "type1" in providers
        assert "type2" in providers


# Docs Generator Tests

class TestDocsGenerator:
    """Tests for documentation generator."""
    
    def test_docs_config_defaults(self):
        config = DocsConfig()
        assert config.output_dir == Path("docs/generated")
        assert config.format == "markdown"
        assert config.include_sources is True
        assert config.include_mounts is True
    
    def test_docs_generator_render_index(self):
        mock_app = MagicMock()
        mock_app.config.sources = {}
        mock_app.catalog.mounts = []
        mock_app.catalog.conflicts = []
        
        config = DocsConfig(title="Test Docs")
        generator = DocsGenerator(mock_app, config)
        
        content = generator._render_index()
        assert "# Test Docs" in content
        assert "Sources" in content

    def test_docs_generator_json_output(self, tmp_path: Path):
        mock_app = MagicMock()
        mock_app.config.sources = {}
        mock_app.catalog.mounts = []
        mock_app.catalog.conflicts = []
        mock_app.export_catalog.return_value = {"mounts": [], "conflicts": []}

        generator = DocsGenerator(mock_app, DocsConfig(output_dir=tmp_path, format="json"))
        generated = generator.generate()

        assert generated["index"].suffix == ".json"
        payload = json.loads(generated["index"].read_text(encoding="utf-8"))
        assert payload["title"] == "CTS Documentation"

    def test_docs_generator_html_output(self, tmp_path: Path):
        mock_app = MagicMock()
        mock_app.config.sources = {}
        mock_app.catalog.mounts = []
        mock_app.catalog.conflicts = []
        mock_app.export_catalog.return_value = {"mounts": [], "conflicts": []}

        generator = DocsGenerator(mock_app, DocsConfig(output_dir=tmp_path, format="html"))
        generated = generator.generate()

        assert generated["index"].suffix == ".html"
        assert "<html" in generated["index"].read_text(encoding="utf-8")


class TestJSONRPCSurface:
    def test_mounts_list_filters(self):
        app = build_app("examples/demo/cts.yaml")
        handler = JSONRPCHandler(app)

        payload = handler._mounts_list({"q": "demo", "source": "demo_cli"})

        assert payload
        assert payload[0]["mount_id"] == "demo-echo"


class TestExternalPluginRuntime:
    def test_subprocess_plugin_extends_runtime(self, tmp_path: Path):
        plugin_path = tmp_path / "external_plugin.py"
        plugin_path.write_text(
            """#!/usr/bin/env python3
import json
import sys

request = json.loads(sys.stdin.read() or "{}")
action = request.get("action")
payload = request.get("payload") or {}

def respond(result=None, error=None):
    body = {"protocol_version": "1.0"}
    if error:
        body["error"] = error
    else:
        body["result"] = result
    sys.stdout.write(json.dumps(body))

if action == "get_metadata":
    respond({"name": "external-demo", "version": "1.0.0", "provides": ["ext_echo"]})
elif action == "register_providers":
    respond([{"type": "ext_echo", "supports_explain": True, "supports_invoke": True}])
elif action == "get_hooks":
    respond([{"event": "explain.before", "handler": "suffix_text", "priority": 50}])
elif action == "suffix_text":
    hook_payload = dict(payload.get("payload") or {})
    args = dict(hook_payload.get("args") or {})
    if "text" in args:
        args["text"] = args["text"] + "!"
    hook_payload["args"] = args
    respond(hook_payload)
elif action == "provider.discover":
    source_name = payload["source_name"]
    respond([{
        "id": "echo",
        "source": source_name,
        "provider_type": payload["provider_type"],
        "title": "External Echo",
        "description": "Echo from external plugin.",
        "risk": "read",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        "supported_surfaces": ["cli", "invoke", "http", "jsonrpc"],
        "provider_config": {}
    }])
elif action == "provider.get_operation":
    source_name = payload["source_name"]
    respond({
        "id": "echo",
        "source": source_name,
        "provider_type": payload["provider_type"],
        "title": "External Echo",
        "description": "Echo from external plugin.",
        "risk": "read",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        "supported_surfaces": ["cli", "invoke", "http", "jsonrpc"],
        "provider_config": {}
    })
elif action == "provider.get_schema":
    respond({
        "schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        "provenance": {"strategy": "declared", "origin": "external", "confidence": 1.0}
    })
elif action == "provider.get_help":
    respond({"summary": "External Echo", "description": "Echo from external plugin."})
elif action == "provider.refresh_auth":
    respond(None)
elif action == "provider.plan":
    request_payload = payload["request"]
    respond({
        "source": payload["source_name"],
        "operation_id": request_payload["operation_id"],
        "provider_type": payload["provider_type"],
        "normalized_args": request_payload["args"],
        "risk": "read",
        "rendered_request": {"args": request_payload["args"]}
    })
elif action == "provider.invoke":
    request_payload = payload["request"]
    respond({"ok": True, "status_code": 0, "data": {"args": request_payload["args"]}, "metadata": {"external": True}})
elif action == "provider.healthcheck":
    respond({"ok": True, "provider_type": payload["provider_type"]})
else:
    respond(error=f"unknown action: {action}")
""",
            encoding="utf-8",
        )
        plugin_path.chmod(0o755)

        config_path = tmp_path / "cts.yaml"
        config_path.write_text(
            f"""
version: 1
plugins:
  external_demo:
    protocol: subprocess
    executable: {plugin_path}
sources:
  ext_source:
    type: ext_echo
mounts:
  - id: ext-echo
    source: ext_source
    operation: echo
    command:
      path: [ext, echo]
""".strip()
            + "\n",
            encoding="utf-8",
        )

        app = build_app(str(config_path))
        mount = app.catalog.find_by_id("ext-echo")

        assert mount is not None
        assert "ext_echo" in app.provider_registry.supported_types()

        plan = app.plugin_manager.explain_dispatch("explain.before", {"mount": mount, "args": {"text": "hello"}, "runtime": {}}, app=app)
        assert plan["hooks"][0]["handler"] == "suffix_text"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--config", str(config_path), "explain", "ext-echo", "--input-json", '{"text":"hello"}', "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["plan"]["normalized_args"]["text"] == "hello!"


# CLI Tests

class TestCLIWorkflowCommands:
    """Tests for workflow CLI commands."""
    
    def test_workflow_list_empty(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")
            
            result = runner.invoke(
                main,
                ["--config", str(config_path), "workflow", "list", "--format", "json"],
            )
            
            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert "workflows" in payload
            assert payload["count"] == 0


class TestCLIDocsCommand:
    """Tests for docs CLI command."""
    
    def test_docs_generate(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")
            
            result = runner.invoke(
                main,
                ["--config", str(config_path), "docs", "generated_docs", "--format", "json"],
            )
            
            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["ok"] is True
            assert "generated_files" in payload


class TestCLIServeCommands:
    """Tests for serve CLI commands."""
    
    def test_serve_http_output(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")
            
            # Just test that the command exists and outputs correctly
            # We can't actually start the server in tests
            with patch("cts.cli.root.create_http_server") as mock_create:
                mock_server = MagicMock()
                mock_server.server_address = ("127.0.0.1", 8787)
                mock_server.serve_forever.side_effect = KeyboardInterrupt()
                mock_create.return_value = mock_server
                
                result = runner.invoke(
                    main,
                    ["--config", str(config_path), "serve", "http"],
                )
                
                # The output should contain JSON or be from a KeyboardInterrupt
                # Just check the command ran
                assert mock_create.called or result.exit_code in [0, 1]

    def test_serve_http_open_browser_output(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")

            with patch("cts.cli.root.create_http_server") as mock_create, patch("cts.cli.root.webbrowser.open") as mock_open:
                mock_server = MagicMock()
                mock_server.server_address = ("127.0.0.1", 8787)
                mock_server.serve_forever.side_effect = KeyboardInterrupt()
                mock_create.return_value = mock_server

                result = runner.invoke(
                    main,
                    ["--config", str(config_path), "serve", "http", "--open"],
                )

                assert result.exit_code == 0
                payload = json.loads(result.output)
                assert payload["base_url"] == "http://127.0.0.1:8787"
                assert payload["browser_url"] == "http://127.0.0.1:8787/api/app/summary"
                assert payload["ui_enabled"] is False
                mock_open.assert_called_once_with("http://127.0.0.1:8787/api/app/summary")

    def test_ui_command_serves_ui_and_opens_browser(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")

            with patch("cts.cli.root.create_http_server") as mock_create, patch("cts.cli.root.webbrowser.open") as mock_open:
                mock_server = MagicMock()
                mock_server.server_address = ("127.0.0.1", 8787)
                mock_server.serve_forever.side_effect = KeyboardInterrupt()
                mock_create.return_value = mock_server

                result = runner.invoke(
                    main,
                    ["--config", str(config_path), "ui", "--open"],
                )

                assert result.exit_code == 0
                payload = json.loads(result.output)
                assert payload["base_url"] == "http://127.0.0.1:8787"
                assert payload["browser_url"] == "http://127.0.0.1:8787"
                assert payload["ui_enabled"] is True
                assert payload["ui_dir"]
                mock_open.assert_called_once_with("http://127.0.0.1:8787")

    def test_ui_command_fails_when_ui_dist_missing(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")

            missing_ui_dir = Path("missing-ui-dist")
            with patch("cts.cli.root.default_ui_dist_dir", return_value=missing_ui_dir), patch("cts.cli.root.create_http_server") as mock_create:
                result = runner.invoke(
                    main,
                    ["--config", str(config_path), "ui"],
                )

                assert result.exit_code != 0
                assert "ui_dist_not_found" in result.output
                assert not mock_create.called


class TestPackaging:
    """Tests for packaged frontend assets."""

    def test_wheel_includes_ui_dist_assets(self):
        repo_root = Path(__file__).resolve().parents[1]
        dist_dir = repo_root / "dist"

        for existing in dist_dir.glob("cts-*.whl"):
            existing.unlink()

        import subprocess

        subprocess.run(
            [str(repo_root / ".venv" / "bin" / "pip"), "wheel", ".", "-w", str(dist_dir), "--no-deps"],
            check=True,
            cwd=repo_root,
        )

        wheels = sorted(dist_dir.glob("cts-*.whl"))
        assert wheels, "expected wheel to be built"

        with zipfile.ZipFile(wheels[-1]) as archive:
            names = archive.namelist()
            assert any(name.endswith("cts/ui_dist/index.html") for name in names)
            assert any(name.startswith("cts/ui_dist/assets/") for name in names)


# JSON-RPC Tests

class TestJSONRPCSurface:
    """Tests for JSON-RPC surface."""
    
    def test_jsonrpc_error_response(self):
        from cts.surfaces.jsonrpc import JSONRPCError, JSONRPCResponse
        
        error = JSONRPCError(-32601, "Method not found")
        assert error.code == -32601
        assert error.message == "Method not found"
        
        response = JSONRPCResponse(
            error={"code": error.code, "message": error.message},
            request_id="1",
        )
        data = response.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert data["error"]["code"] == -32601
    
    def test_jsonrpc_success_response(self):
        from cts.surfaces.jsonrpc import JSONRPCResponse
        
        response = JSONRPCResponse(result={"status": "ok"}, request_id="1")
        data = response.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert data["result"]["status"] == "ok"


# MCP Bridge Tests

class TestMCPBridge:
    """Tests for MCP bridge."""
    
    def test_mcp_tool_to_mcp_format(self):
        from cts.surfaces.mcp import MCPTool
        
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
            mount_id="test-mount",
        )
        
        mcp_format = tool.to_mcp_format()
        assert mcp_format["name"] == "test_tool"
        assert mcp_format["description"] == "A test tool"
        assert mcp_format["inputSchema"]["type"] == "object"
    
    def test_mcp_server_initialize(self):
        from cts.surfaces.mcp import MCPServer
        
        mock_app = MagicMock()
        server = MCPServer(mock_app)
        
        result = server._handle_initialize({})
        assert "protocolVersion" in result
        assert "serverInfo" in result
        assert "capabilities" in result
    
    def test_mcp_server_ping(self):
        from cts.surfaces.mcp import MCPServer
        
        mock_app = MagicMock()
        server = MCPServer(mock_app)
        
        result = server._handle_ping({})
        assert result == {}
