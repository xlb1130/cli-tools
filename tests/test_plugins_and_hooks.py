import json
from pathlib import Path

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main


PLUGIN_SOURCE = """
from cts.models import ExecutionPlan, HelpDescriptor, InvokeResult, OperationDescriptor


class EchoProvider:
    provider_type = "plugin_echo"

    def discover(self, source_name, source_config, app):
        operations = []
        for operation_id, operation in source_config.operations.items():
            operations.append(
                OperationDescriptor(
                    id=operation_id,
                    source=source_name,
                    provider_type=self.provider_type,
                    title=operation.title or operation_id,
                    stable_name=f"{source_name}.{operation_id}".replace("_", "."),
                    description=operation.description,
                    kind=operation.kind,
                    risk=operation.risk,
                    input_schema=dict(operation.input_schema),
                    output_schema=operation.output_schema,
                    examples=list(operation.examples),
                    supported_surfaces=list(operation.supported_surfaces),
                    provider_config=dict(operation.provider_config),
                )
            )
        return operations

    def get_operation(self, source_name, source_config, operation_id, app):
        return app.source_operations.get(source_name, {}).get(operation_id)

    def get_schema(self, source_name, source_config, operation_id, app):
        operation = self.get_operation(source_name, source_config, operation_id, app)
        if operation is None:
            return None
        return operation.input_schema, {"strategy": "declared", "origin": "plugin", "confidence": 1.0}

    def get_help(self, source_name, source_config, operation_id, app):
        operation = self.get_operation(source_name, source_config, operation_id, app)
        if operation is None:
            return None
        return HelpDescriptor(summary=operation.title, description=operation.description)

    def refresh_auth(self, source_name, source_config, app):
        return None

    def plan(self, source_name, source_config, request, app):
        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk="read",
            rendered_request={"provider": self.provider_type, "args": dict(request.args)},
        )

    def invoke(self, source_name, source_config, request, app):
        return InvokeResult(
            ok=True,
            status_code=0,
            data={"provider": self.provider_type, "args": dict(request.args)},
            metadata={"provider_type": self.provider_type},
        )

    def healthcheck(self, source_name, source_config, app):
        return {"ok": True, "provider_type": self.provider_type}


class Plugin:
    def __init__(self, plugin_name=None, config=None):
        self.plugin_name = plugin_name or "demo"
        self.config = config or {}

    def register_providers(self):
        return {"plugin_echo": EchoProvider()}

    def get_hook_handlers(self):
        return {
            "suffix_text": self.suffix_text,
            "mark_result": self.mark_result,
            "append_help_note": self.append_help_note,
            "record_order": self.record_order,
            "explode": self.explode,
        }

    def suffix_text(self, ctx):
        payload = dict(ctx.payload)
        args = dict(payload.get("args", {}))
        if "text" in args:
            args["text"] = args["text"] + self.config.get("suffix", "")
        payload["args"] = args
        return payload

    def mark_result(self, ctx):
        payload = dict(ctx.payload)
        result = dict(payload.get("result", {}))
        data = dict(result.get("data") or {})
        data["hooked"] = True
        result["data"] = data
        payload["result"] = result
        return payload

    def append_help_note(self, ctx):
        payload = dict(ctx.payload)
        help_payload = dict(payload.get("help", {}))
        description = help_payload.get("description") or ""
        note = self.config.get("help_note", "plugin hook active")
        help_payload["description"] = (description + "\\n\\n" + note).strip()
        payload["help"] = help_payload
        return payload

    def record_order(self, ctx):
        payload = dict(ctx.payload)
        runtime = dict(payload.get("runtime", {}))
        order = list(runtime.get("hook_order", []))
        order.append(self.config.get("order_tag", self.plugin_name))
        runtime["hook_order"] = order
        payload["runtime"] = runtime
        return payload

    def explode(self, ctx):
        raise RuntimeError(self.config.get("boom_message", "boom"))
"""


def test_plugin_provider_and_hooks_extend_core_runtime():
    runner = CliRunner()
    with runner.isolated_filesystem():
        plugin_path = Path("demo_plugin.py")
        plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
        config_path = Path("cts.yaml")
        config_path.write_text(
            """
plugins:
  demo:
    path: ./demo_plugin.py
    config:
      suffix: "!"
      help_note: "Plugin hook note"
hooks:
  - event: help.after
    plugin: demo
    handler: append_help_note
  - event: explain.before
    plugin: demo
    handler: suffix_text
  - event: invoke.before
    plugin: demo
    handler: suffix_text
  - event: invoke.after
    plugin: demo
    handler: mark_result
sources:
  plugin_source:
    type: plugin_echo
    operations:
      echo:
        title: Plugin Echo
        description: Echo from plugin provider.
        input_schema:
          type: object
          properties:
            text:
              type: string
          required: [text]
mounts:
  - id: plugin-echo
    source: plugin_source
    operation: echo
    command:
      path: [plugin, echo]
""".strip()
            + "\n",
            encoding="utf-8",
        )

        app = build_app(str(config_path))
        assert "plugin_echo" in app.provider_registry.supported_types()
        assert app.catalog.find_by_id("plugin-echo") is not None

        help_result = runner.invoke(main, ["--config", str(config_path), "plugin", "echo", "--help"])
        assert help_result.exit_code == 0
        assert "Plugin hook note" in help_result.output

        explain_result = runner.invoke(
            main,
            ["--config", str(config_path), "explain", "plugin-echo", "--input-json", '{"text":"hello"}', "--format", "json"],
        )
        assert explain_result.exit_code == 0
        explain_payload = json.loads(explain_result.output)
        assert explain_payload["plan"]["normalized_args"]["text"] == "hello!"

        invoke_result = runner.invoke(
            main,
            ["--config", str(config_path), "plugin", "echo", "--text", "hello", "--output", "json"],
        )
        assert invoke_result.exit_code == 0
        invoke_payload = json.loads(invoke_result.output)
        assert invoke_payload["data"]["args"]["text"] == "hello!"
        assert invoke_payload["data"]["hooked"] is True


def test_source_add_accepts_plugin_registered_provider_type():
    runner = CliRunner()
    with runner.isolated_filesystem():
        plugin_path = Path("demo_plugin.py")
        plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
        config_path = Path("cts.yaml")
        config_path.write_text(
            """
plugins:
  demo:
    path: ./demo_plugin.py
""".strip()
            + "\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "source",
                "add",
                "plugin_echo",
                "plugin_source",
                "--description",
                "Plugin backed source",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["provider_type"] == "plugin_echo"

        raw = config_path.read_text(encoding="utf-8")
        assert "plugin_echo" in raw


def test_hook_priority_and_when_filter_are_applied():
    runner = CliRunner()
    with runner.isolated_filesystem():
        plugin_path = Path("demo_plugin.py")
        plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
        config_path = Path("cts.yaml")
        config_path.write_text(
            """
plugins:
  first:
    path: ./demo_plugin.py
    config:
      order_tag: "first"
  second:
    path: ./demo_plugin.py
    config:
      order_tag: "second"
hooks:
  - event: explain.before
    plugin: second
    handler: record_order
    priority: 200
    when:
      mount_id: plugin-echo
  - event: explain.before
    plugin: first
    handler: record_order
    priority: 10
    when:
      source: plugin_source
sources:
  plugin_source:
    type: plugin_echo
    operations:
      echo:
        title: Plugin Echo
        description: Echo from plugin provider.
        input_schema:
          type: object
          properties:
            text:
              type: string
          required: [text]
mounts:
  - id: plugin-echo
    source: plugin_source
    operation: echo
    command:
      path: [plugin, echo]
""".strip()
            + "\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            ["--config", str(config_path), "explain", "plugin-echo", "--input-json", '{"text":"hello"}', "--format", "json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["plan"]["normalized_args"]["text"] == "hello"
        assert payload["trace_id"]
        assert payload["run_id"]
        # We attach order into runtime, so it should survive into plan metadata via hook-mutated runtime.
        assert payload["plan"]["rendered_request"]["args"]["text"] == "hello"

        app = build_app(str(config_path))
        hook_result = app.dispatch_hooks(
            "explain.before",
            {
                "mount": app.catalog.find_by_id("plugin-echo"),
                "args": {"text": "hello"},
                "runtime": {},
            },
        )
        assert hook_result["runtime"]["hook_order"] == ["first", "second"]
        assert app.plugin_manager.provider_conflicts == [
            {
                "provider_type": "plugin_echo",
                "plugin": "second",
                "existing_owner": "first",
                "action": "skipped",
            }
        ]

        doctor_result = runner.invoke(main, ["--config", str(config_path), "doctor", "--format", "json"])
        assert doctor_result.exit_code == 0
        assert '"plugin_provider_conflicts"' in doctor_result.output


def test_hook_when_source_alias_matches_source_name_payload():
    runner = CliRunner()
    with runner.isolated_filesystem():
        plugin_path = Path("demo_plugin.py")
        plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
        config_path = Path("cts.yaml")
        config_path.write_text(
            """
plugins:
  demo:
    path: ./demo_plugin.py
    config:
      order_tag: "demo"
hooks:
  - event: discovery.before
    plugin: demo
    handler: record_order
    when:
      source: plugin_source
sources:
  plugin_source:
    type: plugin_echo
    operations:
      echo:
        title: Plugin Echo
        description: Echo from plugin provider.
        input_schema:
          type: object
          properties:
            text:
              type: string
          required: [text]
""".strip()
            + "\n",
            encoding="utf-8",
        )

        app = build_app(str(config_path))
        hook_result = app.dispatch_hooks(
            "discovery.before",
            {
                "source_name": "plugin_source",
                "source_config": app.config.sources["plugin_source"],
                "provider": app.get_provider(app.config.sources["plugin_source"]),
                "mode": "compile",
                "runtime": {},
            },
        )
        assert hook_result["runtime"]["hook_order"] == ["demo"]


def test_hook_fail_mode_raise_interrupts_flow():
    runner = CliRunner()
    with runner.isolated_filesystem():
        plugin_path = Path("demo_plugin.py")
        plugin_path.write_text(PLUGIN_SOURCE, encoding="utf-8")
        config_path = Path("cts.yaml")
        config_path.write_text(
            """
plugins:
  demo:
    path: ./demo_plugin.py
    config:
      boom_message: "hook exploded"
hooks:
  - event: invoke.before
    plugin: demo
    handler: explode
    fail_mode: raise
sources:
  plugin_source:
    type: plugin_echo
    operations:
      echo:
        title: Plugin Echo
        description: Echo from plugin provider.
        input_schema:
          type: object
          properties:
            text:
              type: string
          required: [text]
mounts:
  - id: plugin-echo
    source: plugin_source
    operation: echo
    command:
      path: [plugin, echo]
""".strip()
            + "\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            main,
            ["--config", str(config_path), "plugin", "echo", "--text", "hello", "--output", "json"],
        )
        assert result.exit_code != 0
        assert "HookError" in result.output
        assert "hook exploded" in result.output
