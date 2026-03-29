from __future__ import annotations

from typing import Any, Dict, List, Optional


_HOOK_EVENT_CONTRACTS: List[Dict[str, Any]] = [
    {
        "event": "discovery.before",
        "stage": "before",
        "description": "Provider discovery 开始前，可改写 source_config/provider 并追加 runtime 信息。",
        "payload_fields": [
            {"name": "source_name", "type": "string", "required": True},
            {"name": "source_config", "type": "SourceConfig", "required": True},
            {"name": "provider", "type": "provider", "required": True},
            {"name": "mode", "type": "string", "required": True},
            {"name": "runtime", "type": "object", "required": False},
        ],
        "may_mutate": ["source_config", "provider", "runtime"],
    },
    {
        "event": "discovery.after",
        "stage": "after",
        "description": "Provider discovery 完成后，可改写 operations 列表。",
        "payload_fields": [
            {"name": "source_name", "type": "string", "required": True},
            {"name": "source_config", "type": "SourceConfig", "required": True},
            {"name": "provider", "type": "provider", "required": True},
            {"name": "operations", "type": "OperationDescriptor[]", "required": True},
            {"name": "mode", "type": "string", "required": True},
        ],
        "may_mutate": ["operations"],
    },
    {
        "event": "discovery.error",
        "stage": "error",
        "description": "Provider discovery 失败时触发，主要用于分类、告警和留痕。",
        "payload_fields": [
            {"name": "source_name", "type": "string", "required": True},
            {"name": "source_config", "type": "SourceConfig", "required": True},
            {"name": "provider", "type": "provider", "required": True},
            {"name": "error", "type": "Exception", "required": True},
            {"name": "mode", "type": "string", "required": True},
        ],
        "may_mutate": [],
    },
    {
        "event": "help.before",
        "stage": "before",
        "description": "命令帮助编译前触发，可改写 provider_help 或 schema_info。",
        "payload_fields": [
            {"name": "mount", "type": "MountRecord", "required": True},
            {"name": "provider_help", "type": "HelpDescriptor|null", "required": False},
            {"name": "schema_info", "type": "tuple|null", "required": False},
        ],
        "may_mutate": ["provider_help", "schema_info"],
    },
    {
        "event": "help.after",
        "stage": "after",
        "description": "帮助编译完成后触发，可改写最终 help payload。",
        "payload_fields": [
            {"name": "mount", "type": "MountRecord", "required": True},
            {"name": "help", "type": "object", "required": True},
        ],
        "may_mutate": ["help"],
    },
    {
        "event": "explain.before",
        "stage": "before",
        "description": "explain 计划生成前触发，可改写 args/runtime。",
        "payload_fields": [
            {"name": "mount", "type": "MountRecord", "required": True},
            {"name": "args", "type": "object", "required": True},
            {"name": "runtime", "type": "object", "required": True},
        ],
        "may_mutate": ["args", "runtime"],
    },
    {
        "event": "explain.after",
        "stage": "after",
        "description": "explain 成功后触发，可改写结果 payload。",
        "payload_fields": [
            {"name": "mount", "type": "MountRecord", "required": True},
            {"name": "args", "type": "object", "required": True},
            {"name": "runtime", "type": "object", "required": True},
            {"name": "result", "type": "object", "required": True},
        ],
        "may_mutate": ["result"],
    },
    {
        "event": "explain.error",
        "stage": "error",
        "description": "explain 失败后触发，用于扩展错误分类和告警。",
        "payload_fields": [
            {"name": "mount", "type": "MountRecord", "required": True},
            {"name": "args", "type": "object", "required": True},
            {"name": "runtime", "type": "object", "required": True},
            {"name": "error", "type": "Exception", "required": True},
        ],
        "may_mutate": [],
    },
    {
        "event": "invoke.before",
        "stage": "before",
        "description": "实际执行前触发，可改写 args/runtime。",
        "payload_fields": [
            {"name": "mount", "type": "MountRecord", "required": True},
            {"name": "args", "type": "object", "required": True},
            {"name": "runtime", "type": "object", "required": True},
        ],
        "may_mutate": ["args", "runtime"],
    },
    {
        "event": "invoke.after",
        "stage": "after",
        "description": "执行成功后触发，可改写标准化结果对象。",
        "payload_fields": [
            {"name": "mount", "type": "MountRecord", "required": True},
            {"name": "args", "type": "object", "required": True},
            {"name": "runtime", "type": "object", "required": True},
            {"name": "result", "type": "object", "required": True},
        ],
        "may_mutate": ["result"],
    },
    {
        "event": "invoke.error",
        "stage": "error",
        "description": "执行失败后触发，用于错误留痕、辅助恢复和告警。",
        "payload_fields": [
            {"name": "mount", "type": "MountRecord", "required": True},
            {"name": "args", "type": "object", "required": True},
            {"name": "runtime", "type": "object", "required": True},
            {"name": "error", "type": "Exception", "required": True},
        ],
        "may_mutate": [],
    },
    {
        "event": "surface.http.request.before",
        "stage": "before",
        "description": "HTTP northbound 请求路由前触发。",
        "payload_fields": [
            {"name": "method", "type": "string", "required": True},
            {"name": "path", "type": "string", "required": True},
            {"name": "query", "type": "object", "required": False},
            {"name": "body", "type": "object", "required": False},
        ],
        "may_mutate": [],
    },
    {
        "event": "surface.http.request.after",
        "stage": "after",
        "description": "HTTP northbound 请求完成后触发。",
        "payload_fields": [
            {"name": "method", "type": "string", "required": True},
            {"name": "path", "type": "string", "required": True},
            {"name": "query", "type": "object", "required": False},
            {"name": "body", "type": "object", "required": False},
            {"name": "response", "type": "object", "required": True},
        ],
        "may_mutate": [],
    },
    {
        "event": "surface.http.request.error",
        "stage": "error",
        "description": "HTTP northbound 请求失败时触发。",
        "payload_fields": [
            {"name": "method", "type": "string", "required": True},
            {"name": "path", "type": "string", "required": True},
            {"name": "query", "type": "object", "required": False},
            {"name": "body", "type": "object", "required": False},
            {"name": "error", "type": "Exception", "required": True},
        ],
        "may_mutate": [],
    },
]


def list_hook_contracts() -> List[Dict[str, Any]]:
    return [_enrich_contract(item) for item in _HOOK_EVENT_CONTRACTS]


def get_hook_contract(event: str) -> Optional[Dict[str, Any]]:
    normalized = str(event or "").strip()
    for item in _HOOK_EVENT_CONTRACTS:
        if item["event"] == normalized:
            return _enrich_contract(item)
    return None


def _enrich_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    event = str(contract["event"])
    return {
        **contract,
        "sample_payload": _sample_payload_for_event(event),
        "sample_context": _sample_context_for_event(event),
        "simulation": _simulation_profile_for_event(event),
    }


def _sample_payload_for_event(event: str) -> Dict[str, Any]:
    samples = {
        "discovery.before": {"mode": "compile", "runtime": {}},
        "discovery.after": {"mode": "compile", "operations": []},
        "discovery.error": {"mode": "compile", "error": {"type": "RuntimeError", "message": "boom"}},
        "help.before": {},
        "help.after": {"help": {"description": "sample help"}},
        "explain.before": {"args": {"text": "hello"}, "runtime": {}},
        "explain.after": {"args": {"text": "hello"}, "runtime": {}, "result": {"ok": True}},
        "explain.error": {"args": {"text": "hello"}, "runtime": {}, "error": {"type": "ValueError", "message": "bad input"}},
        "invoke.before": {"args": {"text": "hello"}, "runtime": {}},
        "invoke.after": {"args": {"text": "hello"}, "runtime": {}, "result": {"ok": True, "data": {"text": "hello"}}},
        "invoke.error": {"args": {"text": "hello"}, "runtime": {}, "error": {"type": "RuntimeError", "message": "boom"}},
        "surface.http.request.before": {"method": "GET", "path": "/api/extensions/summary", "query": {}},
        "surface.http.request.after": {
            "method": "GET",
            "path": "/api/extensions/summary",
            "query": {},
            "response": {"ok": True},
        },
        "surface.http.request.error": {
            "method": "GET",
            "path": "/api/extensions/summary",
            "query": {},
            "error": {"type": "KeyError", "message": "route not found"},
        },
    }
    return dict(samples.get(event, {}))


def _sample_context_for_event(event: str) -> Dict[str, Any]:
    if event.startswith("surface.http."):
        return {"mount_required": False, "source_required": False}
    if event.startswith("discovery."):
        return {"mount_required": False, "source_required": True}
    return {"mount_required": True, "source_required": False}


def _simulation_profile_for_event(event: str) -> Dict[str, Any]:
    if event.startswith("invoke."):
        return {
            "risk_level": "high",
            "provider_calls_blocked": True,
            "plugin_side_effects_possible": True,
            "notes": [
                "simulate 不会调用 southbound provider，也不会真正执行 mount。",
                "但如果 execute_handlers=true，plugin handler 仍在当前进程内运行，可能产生文件、网络或状态副作用。",
            ],
        }
    if event.startswith("discovery.") or event.startswith("surface.http."):
        return {
            "risk_level": "medium",
            "provider_calls_blocked": True,
            "plugin_side_effects_possible": True,
            "notes": [
                "simulate 不会进入 provider 调用主链路。",
                "但 execute_handlers=true 时，hook handler 依然可能访问外部资源或修改进程内状态。",
            ],
        }
    return {
        "risk_level": "low",
        "provider_calls_blocked": True,
        "plugin_side_effects_possible": True,
        "notes": [
            "simulate 不会调用 southbound provider。",
            "execute_handlers=false 时只做匹配解释，不执行任何 plugin handler。",
        ],
    }
