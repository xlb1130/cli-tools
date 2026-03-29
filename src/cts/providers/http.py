from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from cts.auth import apply_auth_to_request
from cts.config.models import SourceConfig, SourceOperationConfig
from cts.execution.logging import redact_value
from cts.models import ExecutionPlan, InvokeRequest, InvokeResult, OperationDescriptor
from cts.providers.base import ProviderError, build_help_descriptor
from cts.providers.cli import load_manifest, manifest_operations_from_data, operation_from_config


class HTTPProvider:
    provider_type = "http"

    def discover(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> List[OperationDescriptor]:
        operations: List[OperationDescriptor] = []
        if source_config.discovery.manifest:
            manifest = app.resolve_path(source_config.discovery.manifest, owner=source_config)
            if manifest.exists():
                operations.extend(manifest_operations_from_data(source_name, self.provider_type, load_manifest(manifest)))

        for operation_id, operation in source_config.operations.items():
            operations.append(operation_from_config(source_name, self.provider_type, operation_id, operation))
        return operations

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
        return operation.input_schema, {"strategy": "declared", "origin": "http-config", "confidence": 0.9}

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
        return build_help_descriptor(operation)

    def refresh_auth(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Optional[Dict]:
        return None

    def plan(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> ExecutionPlan:
        operation = self.get_operation(source_name, source_config, request.operation_id, app)
        if not operation:
            raise ProviderError(f"operation not found: {source_name}.{request.operation_id}")
        if not source_config.base_url and self.provider_type != "graphql":
            raise ProviderError(f"source {source_name} is missing base_url")

        provider_config = operation.provider_config
        method = provider_config.get("method", "GET").upper()
        path = provider_config.get("path", "")
        url = _build_url(source_config.base_url or source_config.endpoint or "", path, request.args)

        path_keys = set(provider_config.get("path_params", [])) or set(_extract_template_keys(path))
        remaining = {key: value for key, value in request.args.items() if key not in path_keys}

        body = None
        params = None
        if self.provider_type == "graphql":
            body = {
                "query": provider_config.get("document"),
                "variables": dict(request.args),
            }
            method = "POST"
            url = source_config.endpoint or source_config.base_url or ""
        elif method in {"POST", "PUT", "PATCH"}:
            body_fields = provider_config.get("body_fields")
            body = {key: remaining[key] for key in body_fields} if body_fields else remaining
        else:
            params = remaining

        headers = self._resolve_secret_refs(app, source_config.headers)
        headers.update(self._resolve_secret_refs(app, provider_config.get("headers", {})))
        params = self._resolve_secret_refs(app, params)
        body = self._resolve_secret_refs(app, body)
        headers, params = self._apply_source_auth(source_name, source_config, app, headers=headers, params=params)

        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk=operation.risk,
            rendered_request={
                "method": method,
                "url": url,
                "params": params,
                "json": body,
                "headers": headers,
            },
        )

    def invoke(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> InvokeResult:
        plan = self.plan(source_name, source_config, request, app)
        if request.dry_run:
            payload = app.secret_manager.redact_resolved_values(plan.model_dump(mode="json"))
            return InvokeResult(
                ok=True,
                data={"dry_run": True, "plan": redact_value(app, payload)},
                metadata={"provider_type": self.provider_type},
            )

        response = httpx.request(
            method=plan.rendered_request["method"],
            url=plan.rendered_request["url"],
            params=plan.rendered_request.get("params"),
            json=plan.rendered_request.get("json"),
            headers=plan.rendered_request.get("headers"),
            cookies=plan.rendered_request.get("cookies"),
            timeout=request.timeout_seconds or source_config.reliability.get("timeout_seconds", 30),
        )

        try:
            data = response.json()
            text = None
        except ValueError:
            data = None
            text = response.text

        return InvokeResult(
            ok=response.is_success,
            status_code=response.status_code,
            data=data,
            text=text,
            metadata={
                "provider_type": self.provider_type,
                "headers": dict(response.headers),
            },
        )

    def healthcheck(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Dict[str, Any]:
        return {
            "ok": bool(source_config.base_url or source_config.endpoint),
            "provider_type": self.provider_type,
            "base_url": source_config.base_url or source_config.endpoint,
        }

    def _apply_source_auth(
        self,
        source_name: str,
        source_config: SourceConfig,
        app: "CTSApp",
        *,
        headers: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        credentials = app.auth_manager.credentials_for_source(source_name, source_config)
        return apply_auth_to_request(credentials, headers=headers, params=params)

    def _resolve_secret_refs(self, app: "CTSApp", value: Any) -> Any:
        return app.secret_manager.resolve_refs_in_value(value)

class GraphQLProvider(HTTPProvider):
    provider_type = "graphql"


def _build_url(base_url: str, path: str, args: Dict[str, Any]) -> str:
    if not path:
        return base_url
    rendered_path = path.format_map({key: value for key, value in args.items()})
    return base_url.rstrip("/") + "/" + rendered_path.lstrip("/")


def _extract_template_keys(path: str) -> List[str]:
    keys: List[str] = []
    in_key = False
    current = []
    for char in path:
        if char == "{":
            in_key = True
            current = []
            continue
        if char == "}" and in_key:
            in_key = False
            keys.append("".join(current))
            current = []
            continue
        if in_key:
            current.append(char)
    return keys
