from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml

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
from cts.imports.selectors import import_operation_select_arguments, import_operation_select_wizard_fields
from cts.models import ExecutionPlan, InvokeRequest, InvokeResult, OperationDescriptor
from cts.providers.base import ProviderError, build_help_descriptor
from cts.providers.cli import operation_from_config
from cts.providers.http import HTTPProvider, _build_url


HTTP_METHODS = ["get", "post", "put", "patch", "delete", "head", "options"]


class OpenAPIProvider(HTTPProvider):
    provider_type = "openapi"

    def describe_import(self, app: "CTSApp") -> ImportDescriptor:
        return ImportDescriptor(
            provider_type=self.provider_type,
            title="OpenAPI Spec",
            summary="Import an OpenAPI source from a spec file or URL.",
            arguments=[
                ImportArgumentDescriptor(name="source_name", kind="argument", value_type="string", required=True),
                ImportArgumentDescriptor(name="spec_file", kind="option", value_type="path", flags=["--spec-file", "spec_file"]),
                ImportArgumentDescriptor(name="spec_url", kind="option", value_type="string", flags=["--spec-url", "spec_url"]),
                ImportArgumentDescriptor(name="base_url", kind="option", value_type="string", flags=["--base-url", "base_url"]),
                ImportArgumentDescriptor(name="mount_under", kind="option", value_type="string", flags=["--mount-under", "mount_under"]),
                *import_operation_select_arguments(),
            ],
            wizard=ImportWizardDescriptor(
                steps=[
                    ImportWizardStep(
                        id="openapi",
                        title="OpenAPI Import",
                        fields=[
                            ImportWizardField(name="source_name", label="Source name", required=True),
                            ImportWizardField(name="spec_file", label="Spec file", value_type="path"),
                            ImportWizardField(name="spec_url", label="Spec URL"),
                            ImportWizardField(name="base_url", label="Base URL override"),
                            ImportWizardField(name="mount_under", label="Mount prefix"),
                            *import_operation_select_wizard_fields(),
                        ],
                    )
                ]
            ),
        )

    def plan_import(self, request: ImportRequest, app: "CTSApp") -> ImportPlan:
        values = dict(request.values)
        source_name = request.source_name or str(values.get("source_name") or "")
        spec: Dict[str, Any] = {}
        if values.get("spec_file"):
            spec["file"] = str(values["spec_file"])
        if values.get("spec_url"):
            spec["url"] = str(values["spec_url"])
        if not spec:
            raise ProviderError("spec_file or spec_url is required")
        source_patch: Dict[str, Any] = {
            "type": "openapi",
            "spec": spec,
            "discovery": {"mode": "live"},
        }
        if values.get("base_url"):
            source_patch["base_url"] = str(values["base_url"])
        mount_under = [segment for segment in str(values.get("mount_under") or source_name).split() if segment]
        operation_select = dict(request.operation_select)
        return ImportPlan(
            provider_type=self.provider_type,
            source_name=source_name,
            summary=f"Import OpenAPI source '{source_name}'",
            source_patch=source_patch,
            operation_select=operation_select,
            post_compile_actions=[
                ImportPostAction(action="sync_source", payload={"source_name": source_name}),
                ImportPostAction(
                    action="create_mounts_from_source_operations",
                    payload={"source_name": source_name, "under": mount_under, "select": operation_select},
                ),
            ],
            preview={
                "ok": True,
                "action": "import_openapi_preview",
                "apply_action": "import_openapi_apply",
                "source_name": source_name,
                "source_config": source_patch,
                "operation_select": operation_select,
            },
            runtime_data={
                "progress_labels": {
                    "compile": "Compiling config",
                    "sync_source": "Discovering operations",
                    "create_mounts_from_source_operations": "Creating mounts",
                }
            },
        )

    def discover(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> List[OperationDescriptor]:
        operations: List[OperationDescriptor] = []
        if source_config.spec:
            document, origin = _load_openapi_document(source_name, source_config, app)
            operations.extend(_operations_from_openapi(source_name, document, origin))

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
        if operation.provider_config.get("openapi_imported"):
            return operation.input_schema, {
                "strategy": "authoritative",
                "origin": operation.provider_config.get("spec_origin"),
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
        if operation.provider_config.get("openapi_imported"):
            method = str(operation.provider_config.get("method", "GET")).upper()
            path = operation.provider_config.get("path", "")
            help_descriptor.notes.append(f"HTTP: {method} {path}")
            if operation.provider_config.get("spec_origin"):
                help_descriptor.notes.append(f"OpenAPI spec: {operation.provider_config['spec_origin']}")
            if operation.provider_config.get("request_content_type"):
                help_descriptor.notes.append(
                    "Request body content-type: " + str(operation.provider_config["request_content_type"])
                )
        return help_descriptor

    def plan(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> ExecutionPlan:
        operation = self.get_operation(source_name, source_config, request.operation_id, app)
        if not operation:
            raise ProviderError(f"operation not found: {source_name}.{request.operation_id}")
        if not operation.provider_config.get("openapi_imported"):
            return super().plan(source_name, source_config, request, app)

        provider_config = operation.provider_config
        base_url = provider_config.get("server_url") or source_config.base_url or source_config.endpoint or ""
        if not base_url:
            raise ProviderError(f"openapi source {source_name} is missing base_url and spec servers")

        arg_bindings = dict(provider_config.get("arg_bindings") or {})
        path_args: Dict[str, Any] = {}
        params: Dict[str, Any] = {}
        headers = self._resolve_secret_refs(app, source_config.headers)
        cookies: Dict[str, Any] = {}
        body_fields = list(provider_config.get("body_fields") or [])
        body_field_bindings = dict(provider_config.get("body_field_bindings") or {})
        body_param_name = provider_config.get("body_param_name")
        body: Any = None

        for arg_name, value in request.args.items():
            binding = arg_bindings.get(arg_name)
            if binding:
                location = binding.get("in")
                wire_name = binding.get("wire_name", arg_name)
                if location == "path":
                    path_args[wire_name] = value
                elif location == "query":
                    params[wire_name] = value
                elif location == "header":
                    headers[wire_name] = value
                elif location == "cookie":
                    cookies[wire_name] = value
                continue

            if body_param_name and arg_name == body_param_name:
                body = value
                continue

            if body_fields and arg_name in body_fields:
                wire_name = body_field_bindings.get(arg_name, arg_name)
                if body is None or not isinstance(body, dict):
                    body = {}
                body[wire_name] = value
                continue

            if provider_config.get("fallback_location") == "query":
                params[arg_name] = value
            elif provider_config.get("fallback_location") == "body":
                if body is None or not isinstance(body, dict):
                    body = {}
                body[arg_name] = value

        url = _render_path_url(base_url, provider_config.get("path", ""), path_args)
        headers = self._resolve_secret_refs(app, headers)
        params = self._resolve_secret_refs(app, params)
        body = self._resolve_secret_refs(app, body)
        cookies = self._resolve_secret_refs(app, cookies)
        headers, params = self._apply_source_auth(source_name, source_config, app, headers=headers, params=params)
        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk=operation.risk,
            rendered_request={
                "method": str(provider_config.get("method", "GET")).upper(),
                "url": url,
                "params": params or None,
                "json": body,
                "headers": headers,
                "cookies": cookies or None,
            },
        )

    def invoke(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> InvokeResult:
        return super().invoke(source_name, source_config, request, app)

    def healthcheck(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Dict[str, Any]:
        spec_config = source_config.spec or {}
        spec_origin = spec_config.get("path") or spec_config.get("file") or spec_config.get("url")
        return {
            "ok": bool(spec_origin or source_config.base_url or source_config.endpoint),
            "provider_type": self.provider_type,
            "base_url": source_config.base_url or source_config.endpoint,
            "spec_origin": spec_origin,
        }


def _load_openapi_document(source_name: str, source_config: SourceConfig, app: "CTSApp") -> Tuple[Dict[str, Any], str]:
    spec_config = source_config.spec or {}
    path_value = spec_config.get("path") or spec_config.get("file")
    url_value = spec_config.get("url")

    if path_value:
        resolved = app.resolve_path(str(path_value), owner=source_config)
        if not resolved.exists():
            raise ProviderError(f"openapi spec file not found: {resolved}")
        text = resolved.read_text(encoding="utf-8")
        payload = _parse_openapi_document(text, origin=str(resolved))
        return payload, str(resolved)

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
        payload = _parse_openapi_document(response.text, origin=str(url_value))
        return payload, str(url_value)

    raise ProviderError("openapi source requires spec.path, spec.file, or spec.url")


def _parse_openapi_document(text: str, *, origin: str) -> Dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = yaml.safe_load(text)

    if not isinstance(payload, dict):
        raise ProviderError(f"openapi spec root must be a mapping: {origin}")
    if not payload.get("openapi") and not payload.get("paths"):
        raise ProviderError(f"unsupported openapi document: {origin}")
    return payload


def _operations_from_openapi(source_name: str, document: Dict[str, Any], origin: str) -> List[OperationDescriptor]:
    operations: List[OperationDescriptor] = []
    paths = document.get("paths") or {}
    if not isinstance(paths, dict):
        raise ProviderError("openapi spec 'paths' must be a mapping")

    for path_name, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            operations.append(_build_openapi_operation(source_name, document, origin, path_name, path_item, method, operation))
    return operations


def _build_openapi_operation(
    source_name: str,
    document: Dict[str, Any],
    origin: str,
    path_name: str,
    path_item: Dict[str, Any],
    method: str,
    operation: Dict[str, Any],
) -> OperationDescriptor:
    operation_id = _normalize_operation_id(operation.get("operationId") or f"{method}_{path_name}")
    title = operation.get("summary") or operation.get("operationId") or f"{method.upper()} {path_name}"
    description = operation.get("description") or operation.get("summary")
    tags = list(operation.get("tags") or [])

    combined_parameters = _combine_parameters(document, path_item.get("parameters"), operation.get("parameters"))
    properties: Dict[str, Any] = {}
    required: List[str] = []
    arg_bindings: Dict[str, Dict[str, Any]] = {}
    body_fields: List[str] = []
    body_field_bindings: Dict[str, str] = {}

    for parameter in combined_parameters:
        if not isinstance(parameter, dict):
            continue
        location = parameter.get("in")
        wire_name = str(parameter.get("name") or "").strip()
        if location not in {"path", "query", "header", "cookie"} or not wire_name:
            continue

        schema = _schema_from_parameter(parameter, document)
        arg_name = _register_arg_name(wire_name, location, properties)
        property_schema = _decorate_property_schema(schema, description=parameter.get("description"), example=_parameter_example(parameter))
        properties[arg_name] = property_schema
        arg_bindings[arg_name] = {"in": location, "wire_name": wire_name}
        if parameter.get("required") or location == "path":
            required.append(arg_name)

    request_body = _resolve_schema_object(operation.get("requestBody"), document)
    request_content_type = None
    body_param_name = None
    if isinstance(request_body, dict):
        request_content_type, request_body_schema = _select_request_body_schema(request_body, document)
        if request_body_schema:
            if request_body_schema.get("type") == "object" and request_body_schema.get("properties"):
                for body_name, body_schema in (request_body_schema.get("properties") or {}).items():
                    arg_name = _register_arg_name(str(body_name), "body", properties)
                    properties[arg_name] = _decorate_property_schema(
                        body_schema,
                        description=(body_schema or {}).get("description"),
                        example=(body_schema or {}).get("example"),
                    )
                    body_fields.append(arg_name)
                    body_field_bindings[arg_name] = str(body_name)
                for item in request_body_schema.get("required") or []:
                    body_required_name = _find_binding_key(body_field_bindings, str(item))
                    if body_required_name:
                        required.append(body_required_name)
            else:
                body_param_name = _register_arg_name("body", "body", properties)
                properties[body_param_name] = _decorate_property_schema(
                    request_body_schema,
                    description=request_body.get("description"),
                    example=request_body_schema.get("example"),
                )
                if request_body.get("required"):
                    required.append(body_param_name)

    input_schema = {
        "type": "object",
        "properties": properties,
        "required": sorted(set(required)),
    }
    output_schema = _extract_response_schema(operation, document)
    server_url = _resolve_server_url(document, path_item, operation)
    provider_config = {
        "openapi_imported": True,
        "spec_origin": origin,
        "method": method.upper(),
        "path": path_name,
        "server_url": server_url,
        "arg_bindings": arg_bindings,
        "body_fields": body_fields,
        "body_field_bindings": body_field_bindings,
        "body_param_name": body_param_name,
        "request_content_type": request_content_type,
        "operation_id": operation.get("operationId"),
        "tags": tags,
        "fallback_location": "query" if method.lower() in {"get", "head", "options"} else "body",
    }

    return OperationDescriptor(
        id=operation_id,
        source=source_name,
        provider_type="openapi",
        title=title,
        stable_name=f"{source_name}.{operation_id}".replace("_", "."),
        description=description,
        kind="action",
        tags=tags,
        group=tags[0] if tags else None,
        risk=_risk_for_method(method),
        input_schema=input_schema,
        output_schema=output_schema,
        examples=[],
        supported_surfaces=["cli", "invoke", "http"],
        provider_config=provider_config,
    )


def _combine_parameters(document: Dict[str, Any], path_parameters: Any, operation_parameters: Any) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for item in list(path_parameters or []) + list(operation_parameters or []):
        if not isinstance(item, dict):
            continue
        if "$ref" in item:
            resolved = _resolve_ref(document, str(item["$ref"]))
            if not isinstance(resolved, dict):
                continue
            item = resolved
        key = (str(item.get("name")), str(item.get("in")))
        merged[key] = item
    return list(merged.values())


def _schema_from_parameter(parameter: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(parameter.get("schema"), dict):
        return _normalize_schema(parameter["schema"], document)

    content = parameter.get("content") or {}
    if isinstance(content, dict):
        _, schema = _select_content_schema(content, document)
        if schema:
            return schema
    return {"type": "string"}


def _select_request_body_schema(request_body: Dict[str, Any], document: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    content = request_body.get("content") or {}
    if not isinstance(content, dict):
        return None, None
    return _select_content_schema(content, document)


def _select_content_schema(content: Dict[str, Any], document: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    content_type = None
    media = None
    for candidate in ["application/json", "application/*+json", "application/x-www-form-urlencoded", "multipart/form-data"]:
        if candidate in content:
            content_type = candidate
            media = content[candidate]
            break
    if media is None and content:
        content_type, media = next(iter(content.items()))
    if not isinstance(media, dict):
        return content_type, None
    schema = media.get("schema")
    if not isinstance(schema, dict):
        return content_type, None
    return content_type, _normalize_schema(schema, document)


def _extract_response_schema(operation: Dict[str, Any], document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    responses = operation.get("responses") or {}
    if not isinstance(responses, dict):
        return None
    for status_code in sorted(responses.keys()):
        if not str(status_code).startswith("2"):
            continue
        response = _resolve_schema_object(responses[status_code], document)
        if not isinstance(response, dict):
            continue
        content = response.get("content") or {}
        if not isinstance(content, dict):
            continue
        _, schema = _select_content_schema(content, document)
        if schema:
            return schema
    return None


def _resolve_server_url(document: Dict[str, Any], path_item: Dict[str, Any], operation: Dict[str, Any]) -> Optional[str]:
    for value in [operation.get("servers"), path_item.get("servers"), document.get("servers")]:
        if not isinstance(value, list) or not value:
            continue
        server = value[0]
        if not isinstance(server, dict) or not server.get("url"):
            continue
        return _resolve_server_variables(str(server["url"]), server.get("variables") or {})
    return None


def _resolve_server_variables(url: str, variables: Dict[str, Any]) -> str:
    resolved = url
    for name, config in variables.items():
        if isinstance(config, dict):
            replacement = config.get("default")
        else:
            replacement = None
        if replacement is None:
            continue
        resolved = resolved.replace("{" + str(name) + "}", str(replacement))
    return resolved


def _resolve_schema_object(value: Any, document: Dict[str, Any]) -> Any:
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        return _normalize_schema(value, document)
    return value


def _normalize_schema(schema: Dict[str, Any], document: Dict[str, Any], seen: Optional[set[str]] = None) -> Dict[str, Any]:
    seen = set(seen or set())
    if "$ref" in schema:
        ref = str(schema["$ref"])
        if ref in seen:
            return {}
        seen.add(ref)
        resolved = _resolve_ref(document, ref)
        merged = _normalize_schema(resolved, document, seen)
        extra = {key: value for key, value in schema.items() if key != "$ref"}
        return _merge_schema_dicts(merged, _normalize_schema(extra, document, seen))

    normalized = deepcopy(schema)
    if "allOf" in normalized:
        merged: Dict[str, Any] = {}
        for item in normalized.pop("allOf") or []:
            if isinstance(item, dict):
                merged = _merge_schema_dicts(merged, _normalize_schema(item, document, seen))
        normalized = _merge_schema_dicts(merged, normalized)

    schema_type = normalized.get("type")
    if isinstance(schema_type, list):
        non_null = [item for item in schema_type if item != "null"]
        normalized["type"] = non_null[0] if non_null else "string"

    properties = normalized.get("properties")
    if isinstance(properties, dict):
        normalized["properties"] = {
            key: _normalize_schema(value, document, seen) if isinstance(value, dict) else value
            for key, value in properties.items()
        }

    items = normalized.get("items")
    if isinstance(items, dict):
        normalized["items"] = _normalize_schema(items, document, seen)

    additional_properties = normalized.get("additionalProperties")
    if isinstance(additional_properties, dict):
        normalized["additionalProperties"] = _normalize_schema(additional_properties, document, seen)

    return normalized


def _resolve_ref(document: Dict[str, Any], ref: str) -> Dict[str, Any]:
    if not ref.startswith("#/"):
        raise ProviderError(f"unsupported openapi ref: {ref}")
    current: Any = document
    for token in ref[2:].split("/"):
        resolved_token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or resolved_token not in current:
            raise ProviderError(f"openapi ref not found: {ref}")
        current = current[resolved_token]
    if not isinstance(current, dict):
        raise ProviderError(f"openapi ref must resolve to an object: {ref}")
    return current


def _merge_schema_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    if not left:
        return deepcopy(right)
    if not right:
        return deepcopy(left)
    merged = deepcopy(left)
    for key, value in right.items():
        if key == "properties" and isinstance(value, dict):
            merged.setdefault("properties", {})
            for property_name, property_value in value.items():
                existing = merged["properties"].get(property_name, {})
                if isinstance(property_value, dict) and isinstance(existing, dict):
                    merged["properties"][property_name] = _merge_schema_dicts(existing, property_value)
                else:
                    merged["properties"][property_name] = deepcopy(property_value)
            continue
        if key == "required" and isinstance(value, list):
            existing_required = list(merged.get("required") or [])
            merged["required"] = sorted(set(existing_required + value))
            continue
        if key in {"description", "title"} and merged.get(key):
            continue
        merged[key] = deepcopy(value)
    return merged


def _decorate_property_schema(schema: Dict[str, Any], *, description: Optional[str], example: Any) -> Dict[str, Any]:
    property_schema = deepcopy(schema or {"type": "string"})
    if description and not property_schema.get("description"):
        property_schema["description"] = description
    if example is not None and "example" not in property_schema:
        property_schema["example"] = example
    return property_schema


def _parameter_example(parameter: Dict[str, Any]) -> Any:
    if "example" in parameter:
        return parameter["example"]
    examples = parameter.get("examples")
    if isinstance(examples, dict):
        first = next(iter(examples.values()), None)
        if isinstance(first, dict) and "value" in first:
            return first["value"]
    return None


def _register_arg_name(raw_name: str, location: str, properties: Dict[str, Any]) -> str:
    base = _sanitize_arg_name(raw_name) or _sanitize_arg_name(location + "_" + raw_name) or "arg"
    candidate = base
    index = 2
    while candidate in properties:
        if location == "body":
            candidate = f"body_{base}" if index == 2 else f"body_{base}_{index}"
        else:
            candidate = f"{base}_{index}"
        index += 1
    return candidate


def _sanitize_arg_name(value: str) -> str:
    camel_normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", camel_normalized).strip("_")
    if sanitized and sanitized[0].isdigit():
        sanitized = "arg_" + sanitized
    return sanitized.lower()


def _normalize_operation_id(value: str) -> str:
    return _sanitize_arg_name(value) or "operation"


def _risk_for_method(method: str) -> str:
    normalized = method.lower()
    if normalized in {"get", "head", "options"}:
        return "read"
    if normalized == "delete":
        return "destructive"
    return "write"


def _find_binding_key(bindings: Dict[str, str], wire_name: str) -> Optional[str]:
    for arg_name, current_wire_name in bindings.items():
        if current_wire_name == wire_name:
            return arg_name
    return None


def _render_path_url(base_url: str, path: str, path_args: Dict[str, Any]) -> str:
    if not path_args:
        return _build_url(base_url, path, {})
    rendered_path = path
    for wire_name, value in path_args.items():
        rendered_path = rendered_path.replace("{" + wire_name + "}", str(value))
    return _build_url(base_url, rendered_path, {})


def _dedupe_operations(operations: List[OperationDescriptor]) -> List[OperationDescriptor]:
    deduped: Dict[str, OperationDescriptor] = {}
    for operation in operations:
        deduped[operation.id] = operation
    return list(deduped.values())
