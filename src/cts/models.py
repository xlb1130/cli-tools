from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SchemaProvenance(BaseModel):
    strategy: str = "manual"
    origin: Optional[str] = None
    confidence: float = 1.0


class HelpDescriptor(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    arguments: List[Dict[str, Any]] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    source_origin: Optional[str] = None


class OperationDescriptor(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    source: str
    provider_type: str
    title: str
    stable_name: Optional[str] = None
    description: Optional[str] = None
    kind: str = "action"
    tags: List[str] = Field(default_factory=list)
    group: Optional[str] = None
    risk: str = "read"
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    supported_surfaces: List[str] = Field(default_factory=lambda: ["cli", "invoke"])
    transport_hints: Dict[str, Any] = Field(default_factory=dict)
    provider_config: Dict[str, Any] = Field(default_factory=dict)


class InvokeRequest(BaseModel):
    source: str
    operation_id: str
    args: Dict[str, Any] = Field(default_factory=dict)
    profile: Optional[str] = None
    cwd: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    stream: bool = False
    timeout_seconds: Optional[int] = None
    dry_run: bool = False
    non_interactive: bool = False


class InvokeResult(BaseModel):
    ok: bool
    status_code: Optional[int] = None
    data: Any = None
    text: Optional[str] = None
    stderr: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    source: str
    operation_id: str
    provider_type: str
    normalized_args: Dict[str, Any] = Field(default_factory=dict)
    risk: str = "read"
    requires_confirmation: bool = False
    rendered_request: Optional[Dict[str, Any]] = None


class ErrorInfo(BaseModel):
    type: str
    code: str
    message: str
    retryable: bool = False
    user_fixable: bool = False
    stage: Optional[str] = None
    source: Optional[str] = None
    mount_id: Optional[str] = None
    operation_id: Optional[str] = None
    provider_type: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    suggestions: List[str] = Field(default_factory=list)
    raw_cause: Optional[Dict[str, Any]] = None


class ErrorEnvelope(BaseModel):
    ok: bool = False
    error: ErrorInfo
    run_id: Optional[str] = None
    trace_id: Optional[str] = None


class MountRecord(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    mount_id: str
    source_name: str
    provider_type: str
    operation: OperationDescriptor
    command_path: List[str] = Field(default_factory=list)
    aliases: List[List[str]] = Field(default_factory=list)
    stable_name: str
    summary: Optional[str] = None
    description: Optional[str] = None
    source_config: Any = None
    mount_config: Any = None
    generated: bool = False
    generated_from: Optional[str] = None

    def to_summary(self) -> Dict[str, Any]:
        return {
            "mount_id": self.mount_id,
            "source": self.source_name,
            "provider_type": self.provider_type,
            "command_path": self.command_path,
            "aliases": self.aliases,
            "stable_name": self.stable_name,
            "summary": self.summary or self.operation.title,
            "risk": self.operation.risk,
        }
