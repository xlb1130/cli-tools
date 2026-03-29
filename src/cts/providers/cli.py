from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from cts.config.models import SourceConfig, SourceOperationConfig
from cts.models import ExecutionPlan, InvokeRequest, InvokeResult, OperationDescriptor
from cts.providers.base import ProviderError, build_help_descriptor


def render_argv_template(template: Iterable[Any], variables: Dict[str, Any]) -> List[str]:
    rendered: List[str] = []
    for item in template:
        if isinstance(item, str):
            rendered.append(_render_token(item, variables))
        else:
            rendered.append(str(item))
    return rendered


def _render_token(token: str, variables: Dict[str, Any]) -> str:
    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise ProviderError(f"missing template variable: {key}")
        value = variables[key]
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", replacer, token)


def parse_output(raw_stdout: str, output_mode: str) -> tuple:
    if output_mode == "json":
        try:
            return json.loads(raw_stdout), None
        except json.JSONDecodeError as exc:
            raise ProviderError(f"expected JSON output but parsing failed: {exc}") from exc
    if output_mode == "text":
        return None, raw_stdout.rstrip("\n")
    return None, raw_stdout


def manifest_operations_from_data(
    source_name: str,
    provider_type: str,
    data: Dict[str, Any],
) -> List[OperationDescriptor]:
    operations = []
    for raw in data.get("operations", []):
        operation_id = raw["id"]
        provider_config = dict(raw)
        operations.append(
            OperationDescriptor(
                id=operation_id,
                source=source_name,
                provider_type=provider_type,
                title=raw.get("title") or operation_id,
                stable_name=raw.get("stable_name"),
                description=raw.get("description"),
                kind=raw.get("kind", "action"),
                tags=list(raw.get("tags", [])),
                group=raw.get("group"),
                risk=raw.get("risk", "read"),
                input_schema=dict(raw.get("input_schema") or {}),
                output_schema=raw.get("output_schema"),
                examples=list(raw.get("examples", [])),
                supported_surfaces=list(raw.get("supported_surfaces", ["cli", "invoke"])),
                provider_config=provider_config,
            )
        )
    return operations


def load_manifest(path: Path) -> Dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ProviderError(f"manifest root must be a mapping: {path}")
    return raw


def operation_from_config(
    source_name: str,
    provider_type: str,
    operation_id: str,
    operation: SourceOperationConfig,
) -> OperationDescriptor:
    return OperationDescriptor(
        id=operation_id,
        source=source_name,
        provider_type=provider_type,
        title=operation.title or operation_id,
        stable_name=operation.provider_config.get("stable_name"),
        description=operation.description,
        kind=operation.kind,
        tags=list(operation.tags),
        group=operation.group,
        risk=operation.risk,
        input_schema=dict(operation.input_schema),
        output_schema=operation.output_schema,
        examples=list(operation.examples),
        supported_surfaces=list(operation.supported_surfaces),
        provider_config=dict(operation.provider_config),
    )


class CLIProvider:
    provider_type = "cli"

    def discover(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> List[OperationDescriptor]:
        operations: List[OperationDescriptor] = []

        manifest_path = source_config.discovery.manifest
        if manifest_path:
            resolved = app.resolve_path(manifest_path, owner=source_config)
            if resolved.exists():
                operations.extend(
                    manifest_operations_from_data(source_name, self.provider_type, load_manifest(resolved))
                )

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
        for operation in app.source_operations.get(source_name, {}).values():
            if operation.id == operation_id:
                return operation

        for operation in self.discover(source_name, source_config, app):
            if operation.id == operation_id:
                return operation
        return None

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
        return operation.input_schema, {"strategy": "declared", "origin": "cli-manifest", "confidence": 1.0}

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

        argv = self._build_argv(operation, source_name, request)

        return ExecutionPlan(
            source=source_name,
            operation_id=request.operation_id,
            provider_type=self.provider_type,
            normalized_args=dict(request.args),
            risk=operation.risk,
            rendered_request={
                "argv": argv,
                "cwd": request.cwd or source_config.working_dir or None,
                "env": sorted(list((source_config.env or {}).keys())),
            },
        )

    def invoke(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> InvokeResult:
        plan = self.plan(source_name, source_config, request, app)
        if request.dry_run:
            return InvokeResult(
                ok=True,
                data={"dry_run": True, "plan": plan.model_dump(mode="json")},
                metadata={"provider_type": self.provider_type},
            )

        operation = self.get_operation(source_name, source_config, request.operation_id, app)
        assert operation is not None

        env = {}
        if source_config.pass_env:
            env.update(os.environ)
        env.update(source_config.env)
        env.update(request.env)

        completed = subprocess.run(
            plan.rendered_request["argv"],
            cwd=request.cwd or source_config.working_dir or None,
            env=env or None,
            capture_output=True,
            text=True,
            timeout=request.timeout_seconds or source_config.reliability.get("timeout_seconds"),
            check=False,
        )

        output_mode = (
            operation.provider_config.get("output", {}).get("mode")
            or operation.provider_config.get("output_mode")
            or "text"
        )
        data, text = parse_output(completed.stdout, output_mode)

        return InvokeResult(
            ok=completed.returncode == 0,
            status_code=completed.returncode,
            data=data,
            text=text,
            stderr=completed.stderr or None,
            metadata={
                "provider_type": self.provider_type,
                "argv": plan.rendered_request["argv"],
                "output_mode": output_mode,
            },
        )

    def healthcheck(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Dict[str, Any]:
        executable = source_config.executable
        if executable:
            return {
                "ok": shutil.which(executable) is not None,
                "provider_type": self.provider_type,
                "executable": executable,
            }
        return {"ok": True, "provider_type": self.provider_type}

    def _build_argv(self, operation: OperationDescriptor, source_name: str, request: InvokeRequest) -> List[str]:
        argv_template = operation.provider_config.get("argv_template")
        if argv_template:
            variables = dict(request.args)
            variables["__args_json__"] = json.dumps(request.args, ensure_ascii=False)
            variables["source_name"] = source_name
            variables["operation_id"] = request.operation_id
            return render_argv_template(argv_template, variables)

        command_argv = operation.provider_config.get("command_argv")
        option_bindings = operation.provider_config.get("option_bindings")
        if command_argv and option_bindings:
            argv = list(command_argv)
            option_order = list(operation.provider_config.get("option_order") or option_bindings.keys())
            for name in option_order:
                if name not in request.args:
                    continue
                value = request.args.get(name)
                if value is None:
                    continue
                binding = dict(option_bindings.get(name) or {})
                emit_flag = binding.get("emit_flag")
                if not emit_flag:
                    continue
                kind = binding.get("kind", "value")
                repeatable = bool(binding.get("repeatable"))
                if kind == "flag":
                    if bool(value):
                        argv.append(str(emit_flag))
                    continue
                if repeatable and isinstance(value, list):
                    for item in value:
                        argv.extend([str(emit_flag), self._stringify_cli_value(item)])
                    continue
                argv.extend([str(emit_flag), self._stringify_cli_value(value)])
            return argv

        raise ProviderError(
            "CLI operation requires provider_config.argv_template or command_argv + option_bindings in manifest or source.operations"
        )

    def _stringify_cli_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


class ShellProvider(CLIProvider):
    provider_type = "shell"


def _dedupe_operations(operations: List[OperationDescriptor]) -> List[OperationDescriptor]:
    seen: Dict[str, OperationDescriptor] = {}
    for operation in operations:
        seen[operation.id] = operation
    return list(seen.values())
