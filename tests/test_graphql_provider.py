import json
from pathlib import Path

from click.testing import CliRunner

from cts.app import build_app
from cts.cli.root import main
from cts.providers import graphql as graphql_provider


INTROSPECTION_PAYLOAD = {
    "data": {
        "__schema": {
            "queryType": {"name": "Query"},
            "mutationType": {"name": "Mutation"},
            "types": [
                {
                    "kind": "OBJECT",
                    "name": "Query",
                    "fields": [
                        {
                            "name": "viewer",
                            "description": "Fetch current viewer.",
                            "args": [
                                {
                                    "name": "id",
                                    "description": "Viewer id",
                                    "defaultValue": None,
                                    "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None}},
                                },
                                {
                                    "name": "verbose",
                                    "description": "Verbose flag",
                                    "defaultValue": "false",
                                    "type": {"kind": "SCALAR", "name": "Boolean", "ofType": None},
                                },
                            ],
                            "type": {"kind": "OBJECT", "name": "User", "ofType": None},
                        }
                    ],
                },
                {
                    "kind": "OBJECT",
                    "name": "Mutation",
                    "fields": [
                        {
                            "name": "createPost",
                            "description": "Create a post.",
                            "args": [
                                {
                                    "name": "input",
                                    "description": "Post input",
                                    "defaultValue": None,
                                    "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "INPUT_OBJECT", "name": "CreatePostInput", "ofType": None}},
                                }
                            ],
                            "type": {"kind": "OBJECT", "name": "Post", "ofType": None},
                        }
                    ],
                },
                {
                    "kind": "OBJECT",
                    "name": "User",
                    "fields": [
                        {"name": "id", "description": None, "args": [], "type": {"kind": "SCALAR", "name": "ID", "ofType": None}},
                        {"name": "name", "description": None, "args": [], "type": {"kind": "SCALAR", "name": "String", "ofType": None}},
                    ],
                },
                {
                    "kind": "OBJECT",
                    "name": "Post",
                    "fields": [
                        {"name": "id", "description": None, "args": [], "type": {"kind": "SCALAR", "name": "ID", "ofType": None}},
                        {"name": "title", "description": None, "args": [], "type": {"kind": "SCALAR", "name": "String", "ofType": None}},
                        {"name": "author", "description": None, "args": [], "type": {"kind": "OBJECT", "name": "User", "ofType": None}},
                    ],
                },
                {
                    "kind": "INPUT_OBJECT",
                    "name": "CreatePostInput",
                    "description": "Input for post creation.",
                    "inputFields": [
                        {
                            "name": "title",
                            "description": "Post title",
                            "defaultValue": None,
                            "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "String", "ofType": None}},
                        },
                        {
                            "name": "tags",
                            "description": "Post tags",
                            "defaultValue": None,
                            "type": {"kind": "LIST", "name": None, "ofType": {"kind": "SCALAR", "name": "String", "ofType": None}},
                        },
                    ],
                },
                {"kind": "SCALAR", "name": "ID", "fields": None, "inputFields": None, "enumValues": None, "possibleTypes": None},
                {"kind": "SCALAR", "name": "String", "fields": None, "inputFields": None, "enumValues": None, "possibleTypes": None},
                {"kind": "SCALAR", "name": "Boolean", "fields": None, "inputFields": None, "enumValues": None, "possibleTypes": None},
            ],
        }
    }
}


def test_graphql_import_generates_operations_and_help(tmp_path: Path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(INTROSPECTION_PAYLOAD), encoding="utf-8")

    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
auth_profiles:
  github_auth:
    type: bearer
    source: env
    token_env: GITHUB_TOKEN
sources:
  github_graphql:
    type: graphql
    endpoint: https://api.example.com/graphql
    auth_ref: github_auth
    schema:
      path: {schema_path}
mounts:
  - id: gql
    source: github_graphql
    select:
      include: ["*"]
    command:
      under: [gql]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    app = build_app(str(config_path))
    mounts = {mount.mount_id: mount for mount in app.catalog.mounts}
    assert "gql.viewer" in mounts
    assert "gql.create_post" in mounts
    assert mounts["gql.viewer"].command_path == ["gql", "viewer"]
    assert mounts["gql.create_post"].command_path == ["gql", "create", "post"]

    viewer = app.source_operations["github_graphql"]["viewer"]
    create_post = app.source_operations["github_graphql"]["create_post"]
    assert viewer.input_schema["properties"]["id"]["type"] == "string"
    assert viewer.input_schema["properties"]["verbose"]["type"] == "boolean"
    assert "default" in viewer.input_schema["properties"]["verbose"]
    assert create_post.input_schema["properties"]["input"]["type"] == "object"
    assert create_post.input_schema["properties"]["input"]["properties"]["title"]["type"] == "string"
    assert create_post.output_schema["properties"]["author"]["properties"]["name"]["type"] == "string"

    runner = CliRunner()
    help_result = runner.invoke(main, ["--config", str(config_path), "gql", "viewer", "--help"])
    assert help_result.exit_code == 0
    normalized_help_output = " ".join(help_result.output.split())
    assert "GraphQL: query viewer" in normalized_help_output
    assert "GraphQL schema:" in normalized_help_output
    assert "authoritative" in normalized_help_output

    inspect_result = runner.invoke(
        main,
        ["--config", str(config_path), "manage", "inspect", "operation", "github_graphql", "viewer", "--format", "json"],
    )
    assert inspect_result.exit_code == 0
    inspect_payload = json.loads(inspect_result.output)
    assert inspect_payload["schema_provenance"]["strategy"] == "authoritative"
    assert inspect_payload["schema_provenance"]["origin"] == str(schema_path)


def test_graphql_dynamic_command_dry_run_builds_graphql_request(tmp_path: Path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(INTROSPECTION_PAYLOAD), encoding="utf-8")
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        f"""
version: 1
auth_profiles:
  github_auth:
    type: bearer
    source: env
    token_env: GITHUB_TOKEN
sources:
  github_graphql:
    type: graphql
    endpoint: https://api.example.com/graphql
    auth_ref: github_auth
    schema:
      path: {schema_path}
mounts:
  - id: gql
    source: github_graphql
    select:
      include: ["*"]
    command:
      under: [gql]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    viewer_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "gql",
            "viewer",
            "--id",
            "user-1",
            "--verbose",
            "--dry-run",
            "--output",
            "json",
        ],
        env={"GITHUB_TOKEN": "gh-secret"},
    )
    assert viewer_result.exit_code == 0
    viewer_payload = json.loads(viewer_result.output)
    request = viewer_payload["data"]["plan"]["rendered_request"]
    assert request["method"] == "POST"
    assert request["url"] == "https://api.example.com/graphql"
    assert request["json"]["variables"] == {"id": "user-1", "verbose": True}
    assert "query QueryViewer" in request["json"]["query"]
    assert "viewer(id: $id, verbose: $verbose)" in request["json"]["query"]
    assert request["headers"]["Authorization"] == "***"

    mutation_result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "gql",
            "create",
            "post",
            "--input-json",
            '{"input":{"title":"Hello","tags":["one","two"]}}',
            "--dry-run",
            "--output",
            "json",
        ],
        env={"GITHUB_TOKEN": "gh-secret"},
    )
    assert mutation_result.exit_code == 0
    mutation_payload = json.loads(mutation_result.output)
    mutation_request = mutation_payload["data"]["plan"]["rendered_request"]
    assert mutation_request["json"]["variables"] == {"input": {"title": "Hello", "tags": ["one", "two"]}}
    assert "mutation MutationCreatePost" in mutation_request["json"]["query"]
    assert "createPost(input: $input)" in mutation_request["json"]["query"]
    assert mutation_request["headers"]["Authorization"] == "***"


def test_graphql_live_introspection_is_supported(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "cts.yaml"
    config_path.write_text(
        """
version: 1
auth_profiles:
  github_auth:
    type: bearer
    source: env
    token_env: GITHUB_TOKEN
sources:
  github_graphql:
    type: graphql
    endpoint: https://api.example.com/graphql
    auth_ref: github_auth
    schema:
      introspection: live
mounts:
  - id: gql
    source: github_graphql
    select:
      include: ["*"]
    command:
      under: [gql]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return INTROSPECTION_PAYLOAD

    def fake_post(url, json=None, headers=None, params=None, timeout=None):
        assert url == "https://api.example.com/graphql"
        assert json["operationName"] == "IntrospectionQuery"
        assert headers["Authorization"] == "Bearer gh-live-secret"
        return FakeResponse()

    monkeypatch.setattr(graphql_provider.httpx, "post", fake_post)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-live-secret")
    app = build_app(str(config_path))
    assert "viewer" in app.source_operations["github_graphql"]


def test_source_add_graphql_supports_schema_file(tmp_path: Path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(INTROSPECTION_PAYLOAD), encoding="utf-8")
    config_path = tmp_path / "cts.yaml"

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--config",
            str(config_path),
            "manage", "source",
            "add",
            "graphql",
            "github_graphql",
            "--endpoint",
            "https://api.example.com/graphql",
            "--schema-file",
            str(schema_path),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["provider_type"] == "graphql"

    raw = config_path.read_text(encoding="utf-8")
    assert "schema:" in raw
    assert str(schema_path) in raw
