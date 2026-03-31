import json
from pathlib import Path

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main
from cts.providers import mcp_cli


OPENAPI_SPEC = """
openapi: 3.1.0
info:
  title: Demo
  version: "1.0"
paths:
  /pets/{petId}:
    get:
      operationId: getPet
      summary: Get pet
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: ok
""".strip()


GRAPHQL_SCHEMA = {
    "data": {
        "__schema": {
            "queryType": {"name": "Query"},
            "mutationType": None,
            "types": [
                {
                    "kind": "OBJECT",
                    "name": "Query",
                    "fields": [
                        {
                            "name": "viewer",
                            "description": "viewer query",
                            "args": [],
                            "type": {"kind": "SCALAR", "name": "String", "ofType": None},
                        }
                    ],
                },
                {"kind": "SCALAR", "name": "String", "fields": None, "inputFields": None, "enumValues": None, "possibleTypes": None},
            ],
        }
    }
}


def _load_trailing_json(output: str):
    lines = [line for line in output.splitlines() if line.strip()]
    for index in range(len(lines)):
        chunk = "\n".join(lines[index:])
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    raise AssertionError(output)


PLUGIN_WITH_IMPORT = """
from cts.imports.models import ImportArgumentDescriptor, ImportDescriptor, ImportPlan, ImportRequest, ImportWizardDescriptor, ImportWizardField, ImportWizardStep
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
                    stable_name=f"{source_name}.{operation_id}",
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
        return InvokeResult(ok=True, status_code=0, data={"args": dict(request.args)})

    def healthcheck(self, source_name, source_config, app):
        return {"ok": True}

    def describe_import(self, app):
        return ImportDescriptor(
            provider_type=self.provider_type,
            title="Plugin Echo",
            summary="Import plugin-backed echo command.",
            arguments=[
                ImportArgumentDescriptor(name="source_name", kind="argument", value_type="string", required=True),
                ImportArgumentDescriptor(name="text", kind="option", value_type="string"),
            ],
            wizard=ImportWizardDescriptor(
                steps=[
                    ImportWizardStep(
                        id="plugin",
                        title="Plugin Import",
                        fields=[
                            ImportWizardField(name="source_name", label="Source name", required=True),
                            ImportWizardField(name="text", label="Default text"),
                        ],
                    )
                ]
            ),
        )

    def plan_import(self, request, app):
        source_name = request.source_name or request.values.get("source_name")
        text = request.values.get("text") or ""
        source_patch = {
            "type": "plugin_echo",
            "operations": {
                "echo": {
                    "title": "Plugin Echo",
                    "description": "Echo from plugin import",
                    "input_schema": {"type": "object", "properties": {"text": {"type": "string", "default": text}}},
                    "provider_config": {},
                }
            },
        }
        mount_patch = {
            "id": f"{source_name}-echo",
            "source": source_name,
            "operation": "echo",
            "command": {"path": [source_name, "echo"]},
        }
        return ImportPlan(
            provider_type=self.provider_type,
            source_name=source_name,
            source_patch=source_patch,
            mount_patches=[mount_patch],
            preview={"ok": True, "action": "import_plugin_echo_preview", "apply_action": "import_plugin_echo_apply", "source_name": source_name},
        )


class Plugin:
    def register_providers(self):
        return {"plugin_echo": EchoProvider()}
"""


def test_import_http_apply_creates_source_and_mount(tmp_path: Path):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text("version: 1\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "http",
            "demo_http",
            "--base-url",
            "https://api.example.com",
            "--operation-id",
            "get_issue",
            "--method",
            "GET",
            "--path",
            "/issues/{key}",
            "--mount-under",
            "issue",
            "--apply",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "import_http_apply"

    app = build_app(str(config_path))
    mount = app.catalog.find_by_path(["issue", "get-issue"])
    assert mount is not None
    assert mount.operation.id == "get_issue"


def test_import_openapi_apply_discovers_operations_and_creates_mounts(tmp_path: Path):
    spec_path = tmp_path / "petstore.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")
    config_path = tmp_path / "cts.yaml"
    config_path.write_text("version: 1\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "openapi",
            "petstore",
            "--spec-file",
            str(spec_path),
            "--mount-under",
            "petstore",
            "--apply",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "import_openapi_apply"

    app = build_app(str(config_path))
    assert "get_pet" in app.source_operations["petstore"]
    assert app.catalog.find_by_path(["petstore", "get-pet"]) is not None


def test_import_graphql_apply_discovers_operations_and_creates_mounts(tmp_path: Path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(GRAPHQL_SCHEMA), encoding="utf-8")
    config_path = tmp_path / "cts.yaml"
    config_path.write_text("version: 1\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "graphql",
            "github_graphql",
            "--endpoint",
            "https://api.example.com/graphql",
            "--schema-file",
            str(schema_path),
            "--mount-under",
            "gql",
            "--apply",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["action"] == "import_graphql_apply"

    app = build_app(str(config_path))
    assert "viewer" in app.source_operations["github_graphql"]
    assert app.catalog.find_by_path(["gql", "viewer"]) is not None


def test_plugin_provider_import_and_wizard_are_available(tmp_path: Path):
    plugin_path = tmp_path / "demo_plugin.py"
    plugin_path.write_text(PLUGIN_WITH_IMPORT, encoding="utf-8")
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
plugins:
  demo:
    path: {plugin_path}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()

    help_result = runner.invoke(main, ["--config", str(config_path), "import", "--help"])
    assert help_result.exit_code == 0
    assert "plugin_echo" in help_result.output

    import_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "import",
            "plugin_echo",
            "plugin_source",
            "--text",
            "hello",
            "--apply",
            "--format",
            "json",
        ],
    )
    assert import_result.exit_code == 0
    payload = json.loads(import_result.output)
    assert payload["action"] == "import_plugin_echo_apply"

    wizard_result = runner.invoke(
        main,
        ["--config", str(config_path), "import", "wizard", "plugin_echo", "--format", "json"],
        input="plugin_source_2\nworld\n",
    )
    assert wizard_result.exit_code == 0
    wizard_payload = _load_trailing_json(wizard_result.output)
    assert wizard_payload["action"] == "import_plugin_echo_preview"
