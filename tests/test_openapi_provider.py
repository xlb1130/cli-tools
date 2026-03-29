import json
from pathlib import Path

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main


OPENAPI_SPEC = """
openapi: 3.1.0
info:
  title: Petstore
  version: "1.0"
servers:
  - url: https://api.example.com/v1
paths:
  /pets/{petId}:
    get:
      operationId: getPet
      summary: Get pet
      description: Fetch one pet by id.
      tags: [pets]
      parameters:
        - name: petId
          in: path
          required: true
          description: Pet identifier
          schema:
            type: string
        - name: includeVaccines
          in: query
          description: Include vaccine details
          schema:
            type: boolean
            default: false
        - name: X-Trace-Id
          in: header
          description: Trace id
          schema:
            type: string
      responses:
        "200":
          description: Pet detail
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Pet"
  /pets:
    post:
      operationId: createPet
      summary: Create pet
      description: Create a new pet.
      tags: [pets]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                  description: Pet name
                age:
                  type: integer
              required: [name]
      responses:
        "201":
          description: Created pet
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Pet"
components:
  schemas:
    Pet:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
      required: [id, name]
"""


def test_openapi_import_generates_operations_and_help(tmp_path: Path):
    spec_path = tmp_path / "petstore.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")

    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
auth_profiles:
  petstore_auth:
    type: bearer
    source: env
    token_env: PETSTORE_TOKEN
sources:
  petstore:
    type: openapi
    auth_ref: petstore_auth
    spec:
      path: {spec_path}
    discovery:
      mode: import
mounts:
  - id: pet
    source: petstore
    select:
      include: ["*"]
    command:
      under: [pet]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app = build_app(str(config_path))
    mounts = {mount.mount_id: mount for mount in app.catalog.mounts}

    assert "pet.get_pet" in mounts
    assert "pet.create_pet" in mounts
    assert mounts["pet.get_pet"].command_path == ["pet", "get", "pet"]
    assert mounts["pet.create_pet"].command_path == ["pet", "create", "pet"]

    operation = app.source_operations["petstore"]["get_pet"]
    assert operation.input_schema["properties"]["pet_id"]["type"] == "string"
    assert operation.input_schema["properties"]["include_vaccines"]["type"] == "boolean"
    assert operation.input_schema["properties"]["x_trace_id"]["type"] == "string"
    assert operation.output_schema["properties"]["id"]["type"] == "string"

    runner = CliRunner()
    help_result = runner.invoke(main, ["--config", str(config_path), "pet", "get", "pet", "--help"])
    assert help_result.exit_code == 0
    normalized_help_output = " ".join(help_result.output.split())
    assert "HTTP: GET /pets/{petId}" in normalized_help_output
    assert "OpenAPI spec:" in normalized_help_output
    assert "Schema provenance:" in normalized_help_output
    assert "authoritative" in normalized_help_output

    inspect_result = runner.invoke(
        main,
        ["--config", str(config_path), "inspect", "operation", "petstore", "get_pet", "--format", "json"],
    )
    assert inspect_result.exit_code == 0
    inspect_payload = json.loads(inspect_result.output)
    assert inspect_payload["schema_provenance"]["strategy"] == "authoritative"
    assert inspect_payload["schema_provenance"]["origin"] == str(spec_path)


def test_openapi_dynamic_command_dry_run_builds_http_request(tmp_path: Path):
    spec_path = tmp_path / "petstore.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")

    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
auth_profiles:
  petstore_auth:
    type: bearer
    source: env
    token_env: PETSTORE_TOKEN
sources:
  petstore:
    type: openapi
    auth_ref: petstore_auth
    spec:
      path: {spec_path}
    discovery:
      mode: import
mounts:
  - id: pet
    source: petstore
    select:
      include: ["*"]
    command:
      under: [pet]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()

    get_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "pet",
            "get",
            "pet",
            "--pet-id",
            "pet-123",
            "--include-vaccines",
            "--x-trace-id",
            "trace-1",
            "--dry-run",
            "--output",
            "json",
        ],
        env={"PETSTORE_TOKEN": "petstore-secret"},
    )
    assert get_result.exit_code == 0
    get_payload = json.loads(get_result.output)
    get_request = get_payload["data"]["plan"]["rendered_request"]
    assert get_request["method"] == "GET"
    assert get_request["url"] == "https://api.example.com/v1/pets/pet-123"
    assert get_request["params"] == {"includeVaccines": True}
    assert get_request["headers"]["X-Trace-Id"] == "trace-1"
    assert get_request["headers"]["Authorization"] == "***"

    create_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "pet",
            "create",
            "pet",
            "--name",
            "Milo",
            "--age",
            "4",
            "--dry-run",
            "--output",
            "json",
        ],
        env={"PETSTORE_TOKEN": "petstore-secret"},
    )
    assert create_result.exit_code == 0
    create_payload = json.loads(create_result.output)
    create_request = create_payload["data"]["plan"]["rendered_request"]
    assert create_request["method"] == "POST"
    assert create_request["url"] == "https://api.example.com/v1/pets"
    assert create_request["json"] == {"name": "Milo", "age": 4}
    assert create_request["headers"]["Authorization"] == "***"


def test_source_add_openapi_supports_spec_file(tmp_path: Path):
    spec_path = tmp_path / "petstore.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")
    config_path = tmp_path / "cts.yaml"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "source",
            "add",
            "openapi",
            "petstore",
            "--spec-file",
            str(spec_path),
            "--discover-mode",
            "import",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["provider_type"] == "openapi"

    raw = config_path.read_text(encoding="utf-8")
    assert "spec:" in raw
    assert str(spec_path) in raw
