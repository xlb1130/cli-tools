from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AppSettings(BaseModel):
    name: str = "cts"
    default_profile: Optional[str] = None
    cache_dir: Optional[str] = None
    state_dir: Optional[str] = None
    log_dir: Optional[str] = None


class DiscoveryConfig(BaseModel):
    mode: str = "manual"
    manifest: Optional[str] = None
    cache_ttl: Optional[int] = None
    schema_strategy: Optional[str] = None
    probe: Dict[str, Any] = Field(default_factory=dict)


class CommandConfig(BaseModel):
    path: List[str] = Field(default_factory=list)
    aliases: List[List[str]] = Field(default_factory=list)
    under: List[str] = Field(default_factory=list)
    naming: Dict[str, Any] = Field(default_factory=dict)


class MachineConfig(BaseModel):
    stable_name: Optional[str] = None
    expose_via: List[str] = Field(default_factory=lambda: ["cli", "invoke"])
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    annotations: Dict[str, Any] = Field(default_factory=dict)
    default_output: Optional[str] = None
    supports_dry_run: Optional[bool] = None


class MountHelpConfig(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    examples: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    param_overrides: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    hide_sections: List[str] = Field(default_factory=list)


class ParamConfig(BaseModel):
    flag: Optional[str] = None
    type: str = "string"
    required: bool = False
    repeated: bool = False
    help: Optional[str] = None
    default: Any = None
    enum: List[Any] = Field(default_factory=list)
    example: Any = None


class SourceOperationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    kind: str = "action"
    risk: str = "read"
    tags: List[str] = Field(default_factory=list)
    group: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    supported_surfaces: List[str] = Field(default_factory=lambda: ["cli", "invoke"])
    provider_config: Dict[str, Any] = Field(default_factory=dict)
    help: Dict[str, Any] = Field(default_factory=dict)


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str
    enabled: bool = True
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    owner: Optional[str] = None
    profile_scope: List[str] = Field(default_factory=list)
    adapter: Optional[str] = None
    executable: Optional[str] = None
    working_dir: Optional[str] = None
    root: Optional[str] = None
    base_url: Optional[str] = None
    endpoint: Optional[str] = None
    url: Optional[str] = None
    transport_type: Optional[str] = None
    headers: Dict[str, Any] = Field(default_factory=dict)
    env: Dict[str, str] = Field(default_factory=dict)
    auth_ref: Optional[str] = None
    auth_session: Optional[str] = None
    config_file: Optional[str] = None
    server: Optional[str] = None
    pass_env: bool = False
    expose_to_surfaces: List[str] = Field(default_factory=lambda: ["cli", "invoke"])
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    compatibility: Dict[str, Any] = Field(default_factory=dict)
    reliability: Dict[str, Any] = Field(default_factory=dict)
    drift_policy: Dict[str, Any] = Field(default_factory=dict)
    operations: Dict[str, SourceOperationConfig] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    spec: Dict[str, Any] = Field(default_factory=dict)
    schema_config: Dict[str, Any] = Field(default_factory=dict, alias="schema")


class MountConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str = "direct"
    source: str
    operation: Optional[str] = None
    select: Dict[str, Any] = Field(default_factory=dict)
    command: CommandConfig = Field(default_factory=CommandConfig)
    machine: MachineConfig = Field(default_factory=MachineConfig)
    help: MountHelpConfig = Field(default_factory=MountHelpConfig)
    params: Dict[str, ParamConfig] = Field(default_factory=dict)
    policy: Dict[str, Any] = Field(default_factory=dict)
    reliability: Dict[str, Any] = Field(default_factory=dict)
    drift_policy: Dict[str, Any] = Field(default_factory=dict)
    exposure: Dict[str, Any] = Field(default_factory=dict)
    transform: Dict[str, Any] = Field(default_factory=dict)
    compatibility: Dict[str, Any] = Field(default_factory=dict)


class SurfaceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    level: str = "INFO"
    format: str = "jsonl"
    sinks: Dict[str, Any] = Field(default_factory=dict)
    redact: Dict[str, Any] = Field(default_factory=dict)
    retention: Dict[str, Any] = Field(default_factory=dict)


class PluginConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    module: Optional[str] = None
    path: Optional[str] = None
    factory: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class HookConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str
    plugin: str
    handler: str
    enabled: bool = True
    priority: int = 100
    fail_mode: str = "warn"
    when: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)


class CTSConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    app: AppSettings = Field(default_factory=AppSettings)
    imports: List[str] = Field(default_factory=list)
    plugins: Dict[str, PluginConfig] = Field(default_factory=dict)
    hooks: List[HookConfig] = Field(default_factory=list)
    secrets: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    auth_profiles: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    compatibility: Dict[str, Any] = Field(default_factory=dict)
    reliability: Dict[str, Any] = Field(default_factory=dict)
    drift: Dict[str, Any] = Field(default_factory=dict)
    profiles: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    sources: Dict[str, SourceConfig] = Field(default_factory=dict)
    mounts: List[MountConfig] = Field(default_factory=list)
    aliases: List[Dict[str, Any]] = Field(default_factory=list)
    surfaces: Dict[str, SurfaceConfig] = Field(default_factory=dict)
    policies: Dict[str, Any] = Field(default_factory=dict)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    def get_reliability_defaults(self) -> "GlobalReliabilityDefaults":
        """Get typed reliability defaults from config."""
        from cts.reliability.models import GlobalReliabilityDefaults
        
        defaults_dict = self.reliability.get("defaults", {})
        if not defaults_dict:
            return GlobalReliabilityDefaults()
        return GlobalReliabilityDefaults.model_validate(defaults_dict)
    
    def get_rate_limit_budgets(self) -> Dict[str, "RateLimitBudget"]:
        """Get typed rate limit budgets from config."""
        from cts.reliability.models import RateLimitBudget
        
        budgets = self.reliability.get("budgets", {})
        return {
            key: RateLimitBudget.model_validate(value)
            for key, value in budgets.items()
        }
