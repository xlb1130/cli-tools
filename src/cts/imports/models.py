from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ImportArgumentDescriptor(BaseModel):
    name: str
    kind: str
    value_type: str = "string"
    flags: List[str] = Field(default_factory=list)
    required: bool = False
    repeated: bool = False
    default: Any = None
    choices: List[str] = Field(default_factory=list)
    help: Optional[str] = None
    metavar: Optional[str] = None
    env_var: Optional[str] = None
    secret: bool = False


class ImportWizardField(BaseModel):
    name: str
    label: str
    value_type: str = "string"
    required: bool = False
    default: Any = None
    placeholder: Optional[str] = None
    help: Optional[str] = None
    choices: List[str] = Field(default_factory=list)
    secret: bool = False
    multiple: bool = False
    visible_when: Dict[str, Any] = Field(default_factory=dict)


class ImportWizardStep(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    fields: List[ImportWizardField] = Field(default_factory=list)


class ImportWizardDescriptor(BaseModel):
    steps: List[ImportWizardStep] = Field(default_factory=list)
    final_confirmation: bool = True


class ImportDescriptor(BaseModel):
    provider_type: str
    title: str
    summary: Optional[str] = None
    description: Optional[str] = None
    supports_preview: bool = True
    supports_apply: bool = True
    supports_wizard: bool = True
    import_modes: List[str] = Field(default_factory=lambda: ["direct"])
    arguments: List[ImportArgumentDescriptor] = Field(default_factory=list)
    wizard: Optional[ImportWizardDescriptor] = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)


class ImportRequest(BaseModel):
    provider_type: str
    mode: str = "direct"
    source_name: Optional[str] = None
    values: Dict[str, Any] = Field(default_factory=dict)
    apply: bool = False
    target_file: Optional[str] = None
    profile: Optional[str] = None
    requested_by: str = "cli"


class ImportFileWrite(BaseModel):
    path: str
    format: str
    content: Any
    merge_strategy: str = "replace"


class ImportPostAction(BaseModel):
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ImportPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider_type: str
    source_name: str
    summary: Optional[str] = None
    source_patch: Dict[str, Any] = Field(default_factory=dict)
    mount_patches: List[Dict[str, Any]] = Field(default_factory=list)
    files_to_write: List[ImportFileWrite] = Field(default_factory=list)
    post_compile_actions: List[ImportPostAction] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    preview: Dict[str, Any] = Field(default_factory=dict)
    runtime_data: Dict[str, Any] = Field(default_factory=dict)


class ImportResult(BaseModel):
    ok: bool
    action: str
    provider_type: str
    source_name: str
    file: Optional[str] = None
    created_file: bool = False
    warnings: List[str] = Field(default_factory=list)
    preview: Dict[str, Any] = Field(default_factory=list)
    source_config: Optional[Dict[str, Any]] = None
    mounts: List[Dict[str, Any]] = Field(default_factory=list)
    post_actions: List[Dict[str, Any]] = Field(default_factory=list)
