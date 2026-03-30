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
        return {}
