from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from cts.config.models import SourceConfig, SourceOperationConfig
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

    def describe_import(self, app: "CTSApp") -> ImportDescriptor:
        return ImportDescriptor(
            provider_type=self.provider_type,
            title="Local CLI",
            summary="Import a local CLI command or command tree.",
            arguments=[
                ImportArgumentDescriptor(name="source_name", kind="argument", value_type="string", required=True, help="CTS source name."),
                ImportArgumentDescriptor(name="command_argv", kind="argument", value_type="string_list", required=True, repeated=True, help="Original command argv."),
                ImportArgumentDescriptor(name="import_strategy", kind="option", value_type="choice", flags=["--from", "import_strategy"], default="help", choices=["help", "completion", "manpage", "schema"], help="Schema/help import strategy."),
                ImportArgumentDescriptor(name="executable", kind="option", value_type="string", help="Executable override."),
                ImportArgumentDescriptor(name="operation_id", kind="option", value_type="string", help="Operation id override."),
                ImportArgumentDescriptor(name="title", kind="option", value_type="string"),
                ImportArgumentDescriptor(name="risk", kind="option", value_type="choice", default="read", choices=["read", "write", "destructive"]),
                ImportArgumentDescriptor(name="output_mode", kind="option", value_type="choice", default="text", choices=["text", "json"]),
                ImportArgumentDescriptor(name="help_flag", kind="option", value_type="string", default="--help"),
                ImportArgumentDescriptor(name="completion_command", kind="option", value_type="string"),
                ImportArgumentDescriptor(name="completion_file", kind="option", value_type="path"),
                ImportArgumentDescriptor(name="completion_format", kind="option", value_type="choice", default="lines", choices=["lines", "fish", "json"]),
                ImportArgumentDescriptor(name="man_command", kind="option", value_type="string"),
                ImportArgumentDescriptor(name="man_file", kind="option", value_type="path"),
                ImportArgumentDescriptor(name="schema_command", kind="option", value_type="string"),
                ImportArgumentDescriptor(name="schema_file", kind="option", value_type="path"),
                ImportArgumentDescriptor(name="schema_format", kind="option", value_type="choice", default="auto", choices=["auto", "operation", "bindings", "options"]),
                ImportArgumentDescriptor(name="import_all", kind="flag", value_type="bool", flags=["--all", "import_all"], default=False, help="Import the full CLI tree."),
                ImportArgumentDescriptor(name="save_manifest_path", kind="option", value_type="path", flags=["--save-manifest", "save_manifest_path"]),
                ImportArgumentDescriptor(name="create_mount", kind="flag", value_type="bool", default=True, help="Create mount for imported operation."),
                ImportArgumentDescriptor(name="mount_id", kind="option", value_type="string"),
                ImportArgumentDescriptor(name="command_path_value", kind="option", value_type="string", flags=["--path", "command_path_value"]),
                ImportArgumentDescriptor(name="under_values", kind="option", value_type="string_list", repeated=True, flags=["--under", "under_values"]),
                ImportArgumentDescriptor(name="prefix", kind="option", value_type="string"),
            ],
            wizard=ImportWizardDescriptor(
                steps=[
                    ImportWizardStep(
                        id="basics",
                        title="CLI Import",
                        fields=[
                            ImportWizardField(name="source_name", label="Source name", required=True),
                            ImportWizardField(name="command_text", label="Command argv", required=True, help="Shell-like command line."),
                            ImportWizardField(name="import_strategy", label="Import strategy", value_type="choice", default="help", choices=["help", "completion", "manpage", "schema"]),
                            ImportWizardField(name="operation_id", label="Operation id", help="Leave blank to auto-derive."),
                            ImportWizardField(name="title", label="Title"),
                            ImportWizardField(name="risk", label="Risk level", value_type="choice", default="read", choices=["read", "write", "destructive"]),
                            ImportWizardField(name="output_mode", label="Output mode", value_type="choice", default="text", choices=["text", "json"]),
                            ImportWizardField(name="save_manifest_path", label="Save manifest path"),
                            ImportWizardField(name="under_text", label="Mount prefix", help="Space-separated command path prefix."),
                            ImportWizardField(name="import_all", label="Import full CLI tree", value_type="bool", default=False),
                        ],
                    ),
                ]
            ),
        )

    def plan_import(self, request: ImportRequest, app: "CTSApp") -> ImportPlan:
        from cts.cli.import_planning import (
            derive_operation_id_from_command,
            prepare_cli_import_plan,
            prepare_cli_import_tree_plan,
        )

        values = dict(request.values)
        source_name = request.source_name or str(values.get("source_name") or "")
        command_argv = list(values.get("command_argv") or [])
        if not command_argv and values.get("command_text"):
            command_argv = shlex.split(str(values["command_text"]))
        import_strategy = str(values.get("import_strategy") or "help")
        executable = values.get("executable")
        risk = str(values.get("risk") or "read")
        output_mode = str(values.get("output_mode") or "text")
        under_values = tuple(values.get("under_values") or shlex.split(str(values.get("under_text") or "")))
        save_manifest_path = Path(values["save_manifest_path"]) if values.get("save_manifest_path") else None
        operation_id = values.get("operation_id") or (None if values.get("import_all") else derive_operation_id_from_command(command_argv))

        if values.get("import_all"):
            legacy_plan = prepare_cli_import_tree_plan(
                app,
                source_name=source_name,
                command_argv=command_argv,
                executable=executable,
                risk=risk,
                output_mode=output_mode,
                help_flag=str(values.get("help_flag") or "--help"),
                create_mount=bool(values.get("create_mount", True)),
                under_values=under_values,
                prefix=values.get("prefix"),
                save_manifest_path=save_manifest_path,
            )
            return ImportPlan(
                provider_type=self.provider_type,
                source_name=source_name,
                summary=f"Import CLI tree '{source_name}'",
                preview={"ok": True, "action": "import_cli_tree_preview", **legacy_plan, "apply_action": "import_cli_tree_apply"},
                warnings=list(legacy_plan.get("warnings") or []),
                runtime_data={"apply_strategy": "cli_tree", "legacy_plan": legacy_plan},
            )

        legacy_plan = prepare_cli_import_plan(
            app,
            source_name=source_name,
            command_argv=command_argv,
            operation_id=operation_id,
            import_strategy=import_strategy,
            executable=executable,
            title=values.get("title"),
            risk=risk,
            output_mode=output_mode,
            help_flag=str(values.get("help_flag") or "--help"),
            completion_command=values.get("completion_command"),
            completion_file=Path(values["completion_file"]) if values.get("completion_file") else None,
            completion_format=str(values.get("completion_format") or "lines"),
            man_command=values.get("man_command"),
            man_file=Path(values["man_file"]) if values.get("man_file") else None,
            schema_command=values.get("schema_command"),
            schema_file=Path(values["schema_file"]) if values.get("schema_file") else None,
            schema_format=str(values.get("schema_format") or "auto"),
            create_mount=bool(values.get("create_mount", True)),
            mount_id=values.get("mount_id"),
            command_path_value=values.get("command_path_value"),
            under_values=under_values,
            prefix=values.get("prefix"),
            save_manifest_path=save_manifest_path,
        )
        return ImportPlan(
            provider_type=self.provider_type,
            source_name=source_name,
            summary=f"Import CLI command '{source_name}'",
            preview={"ok": True, "action": "import_cli_preview", **legacy_plan, "apply_action": "import_cli_apply"},
            warnings=list(legacy_plan.get("warnings") or []),
            runtime_data={"apply_strategy": "cli_single", "legacy_plan": legacy_plan},
        )

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

    def describe_import(self, app: "CTSApp") -> ImportDescriptor:
        return ImportDescriptor(
            provider_type=self.provider_type,
            title="Shell Command",
            summary="Import a shell command or script.",
            arguments=[
                ImportArgumentDescriptor(name="source_name", kind="argument", value_type="string", required=True),
                ImportArgumentDescriptor(name="exec_command", kind="option", value_type="string", flags=["--exec", "exec_command"], help="Shell command string."),
                ImportArgumentDescriptor(name="script_file", kind="option", value_type="path", help="Script file path."),
                ImportArgumentDescriptor(name="shell_bin", kind="option", value_type="string", default="/bin/sh"),
                ImportArgumentDescriptor(name="under_values", kind="option", value_type="string_list", repeated=True, flags=["--under", "under_values"]),
                ImportArgumentDescriptor(name="title", kind="option", value_type="string"),
                ImportArgumentDescriptor(name="description", kind="option", value_type="string"),
                ImportArgumentDescriptor(name="risk", kind="option", value_type="choice", default="read", choices=["read", "write", "destructive"]),
                ImportArgumentDescriptor(name="output_mode", kind="option", value_type="choice", default="text", choices=["text", "json"]),
            ],
            wizard=ImportWizardDescriptor(
                steps=[
                    ImportWizardStep(
                        id="shell",
                        title="Shell Import",
                        fields=[
                            ImportWizardField(name="source_name", label="Source name", required=True),
                            ImportWizardField(name="exec_command", label="Inline command"),
                            ImportWizardField(name="script_file", label="Script file", value_type="path"),
                            ImportWizardField(name="shell_bin", label="Shell binary", default="/bin/sh"),
                            ImportWizardField(name="title", label="Title"),
                            ImportWizardField(name="description", label="Description"),
                            ImportWizardField(name="risk", label="Risk level", value_type="choice", default="read", choices=["read", "write", "destructive"]),
                            ImportWizardField(name="output_mode", label="Output mode", value_type="choice", default="text", choices=["text", "json"]),
                            ImportWizardField(name="under_text", label="Mount prefix"),
                        ],
                    )
                ]
            ),
        )

    def plan_import(self, request: ImportRequest, app: "CTSApp") -> ImportPlan:
        values = dict(request.values)
        source_name = request.source_name or str(values.get("source_name") or "")
        exec_command = values.get("exec_command")
        script_file = values.get("script_file")
        if not exec_command and not script_file:
            raise ProviderError("exactly one of exec_command or script_file is required")
        if exec_command and script_file:
            raise ProviderError("exec_command and script_file are mutually exclusive")
        shell_bin = str(values.get("shell_bin") or "/bin/sh")
        under_values = list(values.get("under_values") or shlex.split(str(values.get("under_text") or "")))
        operation_id = "run"
        source_label = exec_command if exec_command else str(Path(str(script_file)).resolve())
        argv_template = [shell_bin, "-c", exec_command] if exec_command else [shell_bin, str(Path(str(script_file)).resolve())]
        source_patch = {
            "type": "shell",
            "enabled": True,
            "executable": shell_bin,
            "operations": {
                operation_id: {
                    "title": values.get("title") or source_name,
                    "description": values.get("description") or f"Execute shell command: {source_label}",
                    "risk": str(values.get("risk") or "read"),
                    "input_schema": {"type": "object", "properties": {}},
                    "provider_config": {"argv_template": argv_template, "output_mode": str(values.get("output_mode") or "text")},
                }
            },
        }
        mount_path = under_values + [source_name] if under_values else [source_name]
        mount_patch = {
            "id": source_name.replace(".", "-").replace("_", "-"),
            "source": source_name,
            "operation": operation_id,
            "command": {"path": mount_path},
            "machine": {"stable_name": f"{source_name}.run"},
            "help": {
                "summary": values.get("title") or source_name,
                "description": values.get("description") or f"Execute shell command: {source_label}",
                "notes": [f"Shell executable: {shell_bin}"],
            },
        }
        preview = {
            "ok": True,
            "action": "import_shell_preview",
            "apply_action": "import_shell_apply",
            "source_name": source_name,
            "mount_id": mount_patch["id"],
            "command_path": mount_path,
            "exec": exec_command,
            "exec_command": exec_command,
            "script_file": str(Path(str(script_file)).resolve()) if script_file else None,
            "source_config": source_patch,
            "mount": mount_patch,
        }
        return ImportPlan(
            provider_type=self.provider_type,
            source_name=source_name,
            summary=f"Import shell source '{source_name}'",
            source_patch=source_patch,
            mount_patches=[mount_patch],
            preview=preview,
        )


def _dedupe_operations(operations: List[OperationDescriptor]) -> List[OperationDescriptor]:
    seen: Dict[str, OperationDescriptor] = {}
    for operation in operations:
        seen[operation.id] = operation
    return list(seen.values())
