"""Reliability configuration models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class BackoffStrategy(str, Enum):
    """Backoff strategy for retries."""
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


class RetryOnCondition(str, Enum):
    """Conditions under which to retry."""
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    UPSTREAM_5XX = "upstream_5xx"
    UPSTREAM_ERROR = "upstream_error"
    CONNECTION_ERROR = "connection_error"
    TRANSIENT_ERROR = "transient_error"


class RiskLevel(str, Enum):
    """Risk level for operations - determines retry behavior."""
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class IdempotencyStrategy(str, Enum):
    """Strategy for generating idempotency keys."""
    PROVIDER_NATIVE = "provider_native"
    HASH_ARGS = "hash_args"
    HASH_SELECTED_FIELDS = "hash_selected_fields"
    CALLER_SUPPLIED = "caller_supplied"
    UUID = "uuid"


class BackoffConfig(BaseModel):
    """Backoff configuration for retries."""
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER
    base_delay_ms: int = 300
    max_delay_ms: int = 30000
    multiplier: float = 2.0
    jitter_factor: float = 0.5


class RetryPolicy(BaseModel):
    """Retry policy configuration."""
    max_attempts: int = 2
    retry_on: List[RetryOnCondition] = Field(
        default_factory=lambda: [
            RetryOnCondition.TIMEOUT,
            RetryOnCondition.RATE_LIMIT,
            RetryOnCondition.UPSTREAM_5XX,
            RetryOnCondition.CONNECTION_ERROR,
            RetryOnCondition.TRANSIENT_ERROR,
        ]
    )
    backoff: BackoffConfig = Field(default_factory=BackoffConfig)
    
    # Risk-based defaults
    write_retry_requires_idempotent: bool = True
    destructive_retry_disabled: bool = True


class IdempotencyConfig(BaseModel):
    """Idempotency configuration for mounts/operations."""
    required: bool = False
    strategy: IdempotencyStrategy = IdempotencyStrategy.HASH_ARGS
    ttl_seconds: int = 86400  # 24 hours
    header_name: str = "Idempotency-Key"
    key_fields: List[str] = Field(default_factory=list)
    key_template: Optional[str] = None


class RateLimitBudget(BaseModel):
    """Rate limit budget configuration."""
    requests_per_second: Optional[int] = None
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    max_inflight: Optional[int] = None
    
    def get_rate_limit_type(self) -> Optional[str]:
        """Return the most granular rate limit type configured."""
        if self.requests_per_second:
            return "second"
        if self.requests_per_minute:
            return "minute"
        if self.requests_per_hour:
            return "hour"
        return None
    
    def get_rate_limit_value(self) -> Optional[int]:
        """Return the rate limit value."""
        if self.requests_per_second:
            return self.requests_per_second
        if self.requests_per_minute:
            return self.requests_per_minute
        if self.requests_per_hour:
            return self.requests_per_hour
        return None


class ConcurrencyConfig(BaseModel):
    """Concurrency control configuration."""
    max_inflight_per_source: int = 4
    max_inflight_global: int = 16
    queue_timeout_seconds: int = 30


class TimeoutConfig(BaseModel):
    """Timeout configuration."""
    connect_seconds: float = 5.0
    read_seconds: float = 30.0
    total_seconds: float = 60.0
    process_seconds: Optional[float] = None  # For CLI/shell processes


class ReliabilityConfig(BaseModel):
    """Top-level reliability configuration."""
    model_config = ConfigDict(extra="allow")
    
    # Timeout settings
    timeout_seconds: Optional[int] = None
    timeout: Optional[TimeoutConfig] = None
    
    # Retry settings
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    
    # Rate limiting
    budget_key: Optional[str] = None
    rate_limit: RateLimitBudget = Field(default_factory=RateLimitBudget)
    
    # Concurrency
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    
    # Idempotency
    idempotency: IdempotencyConfig = Field(default_factory=IdempotencyConfig)
    
    # Risk-based behavior
    risk: RiskLevel = RiskLevel.READ
    
    # Fallback/degraded mode
    fallback_mode: str = "fail"  # fail, degraded_ok
    circuit_breaker: Optional[Dict[str, Any]] = None


class GlobalReliabilityDefaults(BaseModel):
    """Global default reliability settings."""
    timeout_seconds: int = 30
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    budgets: Dict[str, RateLimitBudget] = Field(default_factory=dict)


def merge_reliability_config(
    global_defaults: Optional[GlobalReliabilityDefaults],
    source_config: Optional[Dict[str, Any]],
    mount_config: Optional[Dict[str, Any]],
    operation_risk: str = "read",
) -> ReliabilityConfig:
    """Merge reliability config from global, source, and mount levels.
    
    Priority: mount > source > global defaults
    """
    config_dict: Dict[str, Any] = {}
    
    # Start with global defaults
    if global_defaults:
        config_dict["timeout_seconds"] = global_defaults.timeout_seconds
        config_dict["retry"] = global_defaults.retry.model_dump()
        config_dict["concurrency"] = global_defaults.concurrency.model_dump()
    
    # Apply source-level overrides
    if source_config:
        config_dict = _deep_merge(config_dict, source_config)
    
    # Apply mount-level overrides
    if mount_config:
        config_dict = _deep_merge(config_dict, mount_config)
    
    # Set risk from operation
    config_dict["risk"] = operation_risk
    
    return ReliabilityConfig.model_validate(config_dict)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
