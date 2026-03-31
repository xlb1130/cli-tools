from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

import httpx

from cts.auth import apply_auth_to_request
from cts.config.models import SourceConfig
from cts.imports.models import (
    ImportArgumentDescriptor,
    ImportDescriptor,
    ImportPlan,
    ImportPostAction,
    ImportRequest,
    ImportWizardDescriptor,
    ImportWizardField,
    ImportWizardStep,
)
from cts.models import ExecutionPlan, InvokeRequest, InvokeResult, OperationDescriptor
from cts.providers.base import ProviderError, build_help_descriptor
from cts.providers.cli import operation_from_config
from cts.providers.http import HTTPProvider


INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          defaultValue
          type { ...TypeRef }
        }
        type { ...TypeRef }
      }
      inputFields {
        name
        description
        defaultValue
        type { ...TypeRef }
      }
      enumValues(includeDeprecated: true) {
        name
        description
      }
      possibleTypes {
        name
        kind
      }
    }
  }
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
            }
          }
        }
      }
    }
  }
}
""".strip()


class GraphQLProvider(HTTPProvider):
    provider_type = "graphql"

    def describe_import(self, app: "CTSApp") -> ImportDescriptor:
        return ImportDescriptor(
            provider_type=self.provider_type,
            title="GraphQL Endpoint",
            summary="Import a GraphQL source from endpoint and schema info.",
            arguments=[
                ImportArgumentDescriptor(name="source_name", kind="argument", value_type="string", required=True),
                ImportArgumentDescriptor(name="endpoint", kind="option", value_type="string", required=True),
                ImportArgumentDescriptor(name="schema_file", kind="option", value_type="path", flags=["--schema-file", "schema_file"]),
                ImportArgumentDescriptor(name="schema_url", kind="option", value_type="string", flags=["--schema-url", "schema_url"]),
                ImportArgumentDescriptor(name="introspection", kind="option", value_type="choice", default="live", choices=["live", "disabled"]),
                ImportArgumentDescriptor(name="mount_under", kind="option", value_type="string", flags=["--mount-under", "mount_under"]),
            ],
            wizard=ImportWizardDescriptor(
                steps=[
                    ImportWizardStep(
                        id="graphql",
                        title="GraphQL Import",
                        fields=[
                            ImportWizardField(name="source_name", label="Source name", required=True),
                            ImportWizardField(name="endpoint", label="Endpoint", required=True),
                            ImportWizardField(name="schema_file", label="Schema file", value_type="path"),
                            ImportWizardField(name="schema_url", label="Schema URL"),
                            ImportWizardField(name="introspection", label="Introspection", value_type="choice", default="live", choices=["live", "disabled"]),
                            ImportWizardField(name="mount_under", label="Mount prefix"),
                        ],
                    )
                ]
            ),
        )

    def plan_import(self, request: ImportRequest, app: "CTSApp") -> ImportPlan:
        values = dict(request.values)
        source_name = request.source_name or str(values.get("source_name") or "")
        schema: Dict[str, Any] = {}
        if values.get("schema_file"):
            schema["file"] = str(values["schema_file"])
        if values.get("schema_url"):
            schema["url"] = str(values["schema_url"])
        introspection = str(values.get("introspection") or "live")
        if introspection != "disabled":
            schema["introspection"] = introspection
        source_patch = {
            "type": "graphql",
            "endpoint": str(values.get("endpoint") or ""),
            "schema": schema,
        }
        mount_under = [segment for segment in str(values.get("mount_under") or source_name).split() if segment]
        return ImportPlan(
            provider_type=self.provider_type,
            source_name=source_name,
            summary=f"Import GraphQL source '{source_name}'",
            source_patch=source_patch,
            post_compile_actions=[
                ImportPostAction(action="sync_source", payload={"source_name": source_name}),
                ImportPostAction(action="create_mounts_from_source_operations", payload={"source_name": source_name, "under": mount_under}),
            ],
            preview={
                "ok": True,
                "action": "import_graphql_preview",
                "apply_action": "import_graphql_apply",
                "source_name": source_name,
                "source_config": source_patch,
            },
        )

    def discover(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> List[OperationDescriptor]:
        operations: List[OperationDescriptor] = []
        if _should_import_schema(source_config):
            schema_document, origin = _load_graphql_schema(source_name, source_config, app)
            operations.extend(_operations_from_introspection(source_name, schema_document, origin))

        for operation_id, operation in source_config.operations.items():
            operations.append(operation_from_config(source_name, self.provider_type, operation_id, operation))
        return _dedupe_operations(operations)

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
        if operation.provider_config.get("graphql_imported"):
            return operation.input_schema, {
                "strategy": "authoritative",
                "origin": operation.provider_config.get("schema_origin"),
                "confidence": 1.0,
            }
        return operation.input_schema, {"strategy": "manual", "origin": "source.operations", "confidence": 1.0}

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
        if operation.provider_config.get("graphql_imported"):
            op_type = operation.provider_config.get("graphql_operation_type", "query")
            field_name = operation.provider_config.get("field_name", operation.id)
            help_descriptor.notes.append(f"GraphQL: {op_type} {field_name}")
            if operation.provider_config.get("schema_origin"):
                help_descriptor.notes.append(f"GraphQL schema: {operation.provider_config['schema_origin']}")
        return help_descriptor

    def plan(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> ExecutionPlan:
        operation = self.get_operation(source_name, source_config, request.operation_id, app)
        if not operation:
            raise ProviderError(f"operation not found: {source_name}.{request.operation_id}")
        if not operation.provider_config.get("graphql_imported"):
            return super().plan(source_name, source_config, request, app)

        endpoint = source_config.endpoint or source_config.base_url
        if not endpoint:
            raise ProviderError(f"graphql source {source_name} is missing endpoint")

        provider_config = operation.provider_config
        headers = self._resolve_secret_refs(app, source_config.headers)
        headers.update(self._resolve_secret_refs(app, provider_config.get("headers", {})))
        headers.setdefault("Content-Type", "application/json")
        headers, _ = self._apply_source_auth(source_name, source_config, app, headers=headers, params=None)

        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk=operation.risk,
            rendered_request={
                "method": "POST",
                "url": endpoint,
                "params": None,
                "json": {
                    "query": provider_config.get("document"),
                    "variables": dict(request.args),
                    "operationName": provider_config.get("operation_name"),
                },
                "headers": headers,
            },
        )

    def invoke(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> InvokeResult:
        return super().invoke(source_name, source_config, request, app)

    def healthcheck(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Dict[str, Any]:
        schema_config = source_config.schema_config or {}
        schema_origin = schema_config.get("path") or schema_config.get("file") or schema_config.get("url")
        return {
            "ok": bool(source_config.endpoint or source_config.base_url),
            "provider_type": self.provider_type,
            "endpoint": source_config.endpoint or source_config.base_url,
            "schema_origin": schema_origin,
            "introspection": schema_config.get("introspection"),
        }


def _should_import_schema(source_config: SourceConfig) -> bool:
    schema_config = source_config.schema_config or {}
    introspection_mode = str(schema_config.get("introspection") or "").lower()
    return bool(schema_config.get("path") or schema_config.get("file") or schema_config.get("url")) or introspection_mode in {
        "live",
        "import",
        "enabled",
        "true",
    }


def _load_graphql_schema(source_name: str, source_config: SourceConfig, app: "CTSApp") -> Tuple[Dict[str, Any], str]:
    schema_config = source_config.schema_config or {}
    path_value = schema_config.get("path") or schema_config.get("file")
    url_value = schema_config.get("url")
    introspection_mode = str(schema_config.get("introspection") or "").lower()

    if path_value:
        resolved = app.resolve_path(str(path_value), owner=source_config)
        if not resolved.exists():
            raise ProviderError(f"graphql schema file not found: {resolved}")
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        return _extract_schema_payload(payload, origin=str(resolved)), str(resolved)

    if url_value:
        headers, params = apply_auth_to_request(
            app.auth_manager.credentials_for_source(source_name, source_config),
            headers=app.secret_manager.resolve_refs_in_value(source_config.headers),
            params=None,
        )
        response = httpx.get(
            str(url_value),
            headers=headers,
            params=params,
            timeout=source_config.reliability.get("timeout_seconds", 30),
        )
        response.raise_for_status()
        return _extract_schema_payload(response.json(), origin=str(url_value)), str(url_value)

    if introspection_mode in {"live", "import", "enabled", "true"}:
        endpoint = source_config.endpoint or source_config.base_url
        if not endpoint:
            raise ProviderError("graphql live introspection requires endpoint or base_url")
        headers, params = apply_auth_to_request(
            app.auth_manager.credentials_for_source(source_name, source_config),
            headers=app.secret_manager.resolve_refs_in_value(source_config.headers),
            params=None,
        )
        headers.setdefault("Content-Type", "application/json")
        response = httpx.post(
            endpoint,
            json={"query": INTROSPECTION_QUERY, "operationName": "IntrospectionQuery"},
            headers=headers,
            params=params,
            timeout=source_config.reliability.get("timeout_seconds", 30),
        )
        response.raise_for_status()
        return _extract_schema_payload(response.json(), origin=str(endpoint)), str(endpoint)

    raise ProviderError("graphql source requires schema.path, schema.url, or schema.introspection=live")


def _extract_schema_payload(payload: Any, *, origin: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProviderError(f"graphql introspection payload must be a mapping: {origin}")
    if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("__schema"), dict):
        return payload["data"]["__schema"]
    if isinstance(payload.get("__schema"), dict):
        return payload["__schema"]
    raise ProviderError(f"invalid graphql introspection payload: {origin}")


def _operations_from_introspection(source_name: str, schema_document: Dict[str, Any], origin: str) -> List[OperationDescriptor]:
    types = {item.get("name"): item for item in schema_document.get("types") or [] if isinstance(item, dict) and item.get("name")}
    operations: List[OperationDescriptor] = []

    root_specs = [
        ("query", (schema_document.get("queryType") or {}).get("name"), "read"),
        ("mutation", (schema_document.get("mutationType") or {}).get("name"), "write"),
    ]
    seen_ids: set[str] = set()
    for op_type, root_name, default_risk in root_specs:
        if not root_name or root_name not in types:
            continue
        root_type = types[root_name]
        for field in root_type.get("fields") or []:
            if not isinstance(field, dict) or not field.get("name"):
                continue
            field_name = str(field["name"])
            operation_id = _sanitize_name(field_name)
            if operation_id in seen_ids:
                operation_id = f"{op_type}_{operation_id}"
            seen_ids.add(operation_id)
            document = _build_operation_document(op_type, field_name, field, types)
            input_schema = _build_input_schema(field, types)
            output_schema = _unwrap_output_schema(field.get("type"), types)
            operations.append(
                OperationDescriptor(
                    id=operation_id,
                    source=source_name,
                    provider_type="graphql",
                    title=field_name,
                    stable_name=f"{source_name}.{operation_id}".replace("_", "."),
                    description=field.get("description"),
                    kind=op_type,
                    tags=[op_type],
                    group=op_type,
                    risk="write" if op_type == "mutation" else default_risk,
                    input_schema=input_schema,
                    output_schema=output_schema,
                    examples=[],
                    supported_surfaces=["cli", "invoke", "http"],
                    provider_config={
                        "graphql_imported": True,
                        "graphql_operation_type": op_type,
                        "field_name": field_name,
                        "document": document,
                        "operation_name": _graphql_operation_name(op_type, field_name),
                        "schema_origin": origin,
                        "root_type": root_name,
                    },
                )
            )
    return operations


def _build_input_schema(field: Dict[str, Any], types: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for arg in field.get("args") or []:
        if not isinstance(arg, dict) or not arg.get("name"):
            continue
        arg_name = _sanitize_name(str(arg["name"]))
        schema, is_required = _type_ref_to_json_schema(arg.get("type"), types)
        property_schema = deepcopy(schema)
        if arg.get("description") and not property_schema.get("description"):
            property_schema["description"] = arg["description"]
        if arg.get("defaultValue") is not None:
            property_schema["default"] = arg["defaultValue"]
            is_required = False
        properties[arg_name] = property_schema
        if is_required:
            required.append(arg_name)
    return {"type": "object", "properties": properties, "required": sorted(set(required))}


def _type_ref_to_json_schema(type_ref: Any, types: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Any], bool]:
    if not isinstance(type_ref, dict):
        return {"type": "string"}, False

    kind = type_ref.get("kind")
    if kind == "NON_NULL":
        schema, _ = _type_ref_to_json_schema(type_ref.get("ofType"), types)
        return schema, True
    if kind == "LIST":
        items, _ = _type_ref_to_json_schema(type_ref.get("ofType"), types)
        return {"type": "array", "items": items}, False

    type_name = type_ref.get("name")
    if not type_name:
        return {"type": "string"}, False

    if kind == "SCALAR":
        return _scalar_schema(type_name), False
    if kind == "ENUM":
        enum_type = types.get(type_name) or {}
        values = [item["name"] for item in enum_type.get("enumValues") or [] if isinstance(item, dict) and item.get("name")]
        schema: Dict[str, Any] = {"type": "string"}
        if values:
            schema["enum"] = values
        if enum_type.get("description"):
            schema["description"] = enum_type["description"]
        return schema, False
    if kind == "INPUT_OBJECT":
        input_type = types.get(type_name) or {}
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for field in input_type.get("inputFields") or []:
            if not isinstance(field, dict) or not field.get("name"):
                continue
            field_schema, field_required = _type_ref_to_json_schema(field.get("type"), types)
            property_schema = deepcopy(field_schema)
            if field.get("description") and not property_schema.get("description"):
                property_schema["description"] = field["description"]
            if field.get("defaultValue") is not None:
                property_schema["default"] = field["defaultValue"]
                field_required = False
            properties[_sanitize_name(str(field["name"]))] = property_schema
            if field_required:
                required.append(_sanitize_name(str(field["name"])))
        schema = {"type": "object", "properties": properties, "required": sorted(set(required))}
        if input_type.get("description"):
            schema["description"] = input_type["description"]
        return schema, False
    return {"type": "object", "additionalProperties": True}, False


def _unwrap_output_schema(type_ref: Any, types: Dict[str, Dict[str, Any]], depth: int = 0, seen: Optional[set[str]] = None) -> Optional[Dict[str, Any]]:
    seen = set(seen or set())
    if not isinstance(type_ref, dict):
        return None
    kind = type_ref.get("kind")
    if kind == "NON_NULL":
        return _unwrap_output_schema(type_ref.get("ofType"), types, depth=depth, seen=seen)
    if kind == "LIST":
        items = _unwrap_output_schema(type_ref.get("ofType"), types, depth=depth, seen=seen) or {"type": "object"}
        return {"type": "array", "items": items}

    type_name = type_ref.get("name")
    if not type_name:
        return None

    if kind == "SCALAR":
        return _scalar_schema(type_name)
    if kind == "ENUM":
        enum_type = types.get(type_name) or {}
        values = [item["name"] for item in enum_type.get("enumValues") or [] if isinstance(item, dict) and item.get("name")]
        schema: Dict[str, Any] = {"type": "string"}
        if values:
            schema["enum"] = values
        return schema
    if kind in {"OBJECT", "INTERFACE"}:
        if depth >= 2 or type_name in seen:
            return {"type": "object", "additionalProperties": True}
        seen.add(type_name)
        object_type = types.get(type_name) or {}
        properties: Dict[str, Any] = {}
        for field in object_type.get("fields") or []:
            if not isinstance(field, dict) or not field.get("name"):
                continue
            properties[_sanitize_name(str(field["name"]))] = _unwrap_output_schema(
                field.get("type"),
                types,
                depth=depth + 1,
                seen=seen,
            ) or {"type": "object"}
        schema: Dict[str, Any] = {"type": "object", "properties": properties}
        return schema
    if kind == "UNION":
        return {"type": "object", "additionalProperties": True}
    return {"type": "object", "additionalProperties": True}


def _build_operation_document(op_type: str, field_name: str, field: Dict[str, Any], types: Dict[str, Dict[str, Any]]) -> str:
    operation_name = _graphql_operation_name(op_type, field_name)
    variable_defs: List[str] = []
    arg_bindings: List[str] = []
    for arg in field.get("args") or []:
        if not isinstance(arg, dict) or not arg.get("name"):
            continue
        raw_name = str(arg["name"])
        variable_defs.append(f"${raw_name}: {_graphql_type_ref(arg.get('type'))}")
        arg_bindings.append(f"{raw_name}: ${raw_name}")

    args_rendered = f"({', '.join(arg_bindings)})" if arg_bindings else ""
    selection = _build_selection_set(field.get("type"), types)
    variable_def_rendered = f"({', '.join(variable_defs)})" if variable_defs else ""
    field_rendered = f"{field_name}{args_rendered}"
    if selection:
        field_rendered += f" {selection}"
    return f"{op_type} {operation_name}{variable_def_rendered} {{\n  {field_rendered}\n}}"


def _build_selection_set(type_ref: Any, types: Dict[str, Dict[str, Any]], depth: int = 0, seen: Optional[set[str]] = None) -> str:
    seen = set(seen or set())
    named_type = _unwrap_named_type(type_ref)
    if not named_type:
        return ""
    kind = named_type.get("kind")
    type_name = named_type.get("name")
    if kind in {"SCALAR", "ENUM"} or not type_name:
        return ""
    if kind in {"UNION", "INTERFACE"}:
        return "{ __typename }"
    if depth >= 2 or type_name in seen:
        return "{ __typename }"

    object_type = types.get(type_name) or {}
    fields = object_type.get("fields") or []
    selections: List[str] = []
    seen.add(type_name)
    for field in fields:
        if not isinstance(field, dict) or not field.get("name"):
            continue
        child_name = str(field["name"])
        child_named_type = _unwrap_named_type(field.get("type"))
        if child_named_type and child_named_type.get("kind") in {"SCALAR", "ENUM"}:
            selections.append(child_name)
            continue
        child_selection = _build_selection_set(field.get("type"), types, depth=depth + 1, seen=seen)
        if child_selection:
            selections.append(f"{child_name} {child_selection}")
    if not selections:
        return "{ __typename }"
    return "{ " + " ".join(selections[:8]) + " }"


def _unwrap_named_type(type_ref: Any) -> Optional[Dict[str, Any]]:
    current = type_ref
    while isinstance(current, dict) and current.get("kind") in {"NON_NULL", "LIST"}:
        current = current.get("ofType")
    return current if isinstance(current, dict) else None


def _graphql_type_ref(type_ref: Any) -> str:
    if not isinstance(type_ref, dict):
        return "String"
    kind = type_ref.get("kind")
    if kind == "NON_NULL":
        return _graphql_type_ref(type_ref.get("ofType")) + "!"
    if kind == "LIST":
        return "[" + _graphql_type_ref(type_ref.get("ofType")) + "]"
    return str(type_ref.get("name") or "String")


def _graphql_operation_name(op_type: str, field_name: str) -> str:
    return op_type.capitalize() + _pascal_case(field_name)


def _pascal_case(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value))
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def _sanitize_name(value: str) -> str:
    camel_normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", camel_normalized).strip("_")
    if sanitized and sanitized[0].isdigit():
        sanitized = "arg_" + sanitized
    return sanitized.lower() or "field"


def _scalar_schema(type_name: str) -> Dict[str, Any]:
    mapping = {
        "id": {"type": "string"},
        "string": {"type": "string"},
        "int": {"type": "integer"},
        "float": {"type": "number"},
        "boolean": {"type": "boolean"},
    }
    return deepcopy(mapping.get(type_name.lower(), {"type": "string"}))


def _dedupe_operations(operations: List[OperationDescriptor]) -> List[OperationDescriptor]:
    deduped: Dict[str, OperationDescriptor] = {}
    for operation in operations:
        deduped[operation.id] = operation
    return list(deduped.values())
