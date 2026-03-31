"""
带 Hooks 的 Plugin 示例

这个插件演示了：
1. 注册一个新的 provider type (hook_echo)
2. 提供多个 hook handler
3. 通过配置控制行为
"""

from cts.models import (
    ExecutionPlan,
    HelpDescriptor,
    InvokeResult,
    OperationDescriptor,
)


class EchoProvider:
    """自定义 Provider"""
    provider_type = "hook_echo"

    def discover(self, source_name, source_config, app):
        operations = []
        for op_id, op in source_config.operations.items():
            operations.append(
                OperationDescriptor(
                    id=op_id,
                    source=source_name,
                    provider_type=self.provider_type,
                    title=op.title or op_id,
                    stable_name=f"{source_name}.{op_id}".replace("_", "."),
                    description=op.description,
                    kind=op.kind,
                    risk=op.risk,
                    input_schema=dict(op.input_schema),
                    output_schema=op.output_schema,
                    examples=list(op.examples),
                    supported_surfaces=list(op.supported_surfaces),
                    provider_config=dict(op.provider_config),
                )
            )
        return operations

    def get_operation(self, source_name, source_config, operation_id, app):
        return app.source_operations.get(source_name, {}).get(operation_id)

    def get_schema(self, source_name, source_config, operation_id, app):
        op = self.get_operation(source_name, source_config, operation_id, app)
        if op is None:
            return None
        return op.input_schema, {
            "strategy": "declared",
            "origin": "plugin",
            "confidence": 1.0,
        }

    def get_help(self, source_name, source_config, operation_id, app):
        op = self.get_operation(source_name, source_config, operation_id, app)
        if op is None:
            return None
        return HelpDescriptor(summary=op.title, description=op.description)

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
    """插件主类"""

    def __init__(self, plugin_name=None, config=None):
        self.plugin_name = plugin_name or "demo"
        self.config = config or {}

    def register_providers(self):
        """注册 Provider"""
        return {"hook_echo": EchoProvider()}

    def get_hook_handlers(self):
        """注册所有 Hook 处理函数"""
        return {
            "suffix_text": self.suffix_text,
            "mark_result": self.mark_result,
            "append_help_note": self.append_help_note,
        }

    # ============ Hook 处理函数 ============

    def suffix_text(self, ctx):
        """
        Hook: 在 args.text 后追加后缀

        触发时机: explain.before, invoke.before
        可修改字段: args
        """
        payload = dict(ctx.payload)
        args = dict(payload.get("args", {}))

        if "text" in args:
            suffix = self.config.get("suffix", "!")
            args["text"] = args["text"] + suffix

        payload["args"] = args
        return payload

    def mark_result(self, ctx):
        """
        Hook: 在结果中添加标记

        触发时机: invoke.after
        可修改字段: result
        """
        payload = dict(ctx.payload)
        result = dict(payload.get("result", {}))
        data = dict(result.get("data") or {})

        data["hooked"] = True
        data["hook_plugin"] = self.plugin_name

        result["data"] = data
        payload["result"] = result
        return payload

    def append_help_note(self, ctx):
        """
        Hook: 在帮助信息后追加说明

        触发时机: help.after
        可修改字段: help
        """
        payload = dict(ctx.payload)
        help_obj = dict(payload.get("help", {}))

        note = self.config.get("help_note", "")
        if note:
            existing = help_obj.get("description", "")
            help_obj["description"] = f"{existing}\n\n{note}".strip()

        payload["help"] = help_obj
        return payload