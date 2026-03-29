from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from cts.config.models import SourceConfig
from cts.models import (
    ExecutionPlan,
    HelpDescriptor,
    InvokeRequest,
    InvokeResult,
    OperationDescriptor,
    SchemaProvenance,
)


class Provider(Protocol):
    provider_type: str

    def discover(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> List[OperationDescriptor]:
        ...

    def get_operation(
        self,
        source_name: str,
        source_config: SourceConfig,
        operation_id: str,
        app: "CTSApp",
    ) -> Optional[OperationDescriptor]:
        ...

    def get_schema(
        self,
        source_name: str,
        source_config: SourceConfig,
        operation_id: str,
        app: "CTSApp",
    ) -> Optional[tuple]:
        ...

    def get_help(
        self,
        source_name: str,
        source_config: SourceConfig,
        operation_id: str,
        app: "CTSApp",
    ) -> Optional[HelpDescriptor]:
        ...

    def refresh_auth(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Optional[Dict]:
        ...

    def plan(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> ExecutionPlan:
        ...

    def invoke(self, source_name: str, source_config: SourceConfig, request: InvokeRequest, app: "CTSApp") -> InvokeResult:
        ...

    def healthcheck(self, source_name: str, source_config: SourceConfig, app: "CTSApp") -> Dict:
        ...


class ProviderError(RuntimeError):
    pass


def build_help_descriptor(operation: OperationDescriptor, provenance: Optional[SchemaProvenance] = None) -> HelpDescriptor:
    notes = []
    if provenance:
        notes.append(
            "Schema provenance: "
            f"{provenance.strategy}"
            + (f" ({provenance.origin})" if provenance.origin else "")
        )
    return HelpDescriptor(
        summary=operation.title,
        description=operation.description,
        examples=[example.get("cli", "") for example in operation.examples if isinstance(example, dict) and example.get("cli")],
        notes=notes,
    )
