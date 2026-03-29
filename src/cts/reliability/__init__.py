"""Reliability layer for CTS - retry, rate limiting, idempotency, and concurrency control."""

from cts.reliability.models import (
    BackoffConfig,
    BackoffStrategy,
    ConcurrencyConfig,
    GlobalReliabilityDefaults,
    IdempotencyConfig,
    IdempotencyStrategy,
    RateLimitBudget,
    ReliabilityConfig,
    RetryOnCondition,
    RetryPolicy,
    RiskLevel,
    TimeoutConfig,
    merge_reliability_config,
)
from cts.reliability.retry import (
    RetryExecutor,
    RetryContext,
    RetryResult,
    classify_error_for_retry,
    create_retry_executor_from_config,
    get_retry_after_ms,
    should_retry_for_risk,
)
from cts.reliability.rate_limiter import RateLimiter, RateLimitManager
from cts.reliability.concurrency import ConcurrencyManager, ConcurrencySemaphore
from cts.reliability.idempotency import (
    IdempotencyManager,
    IdempotencyKey,
    ExecutionRecord,
    generate_idempotency_header,
    generate_idempotency_key_for_provider,
)
from cts.reliability.facade import (
    ReliabilityManager,
    ReliabilityContext,
    ReliabilityResult,
)

__all__ = [
    # Models
    "ReliabilityConfig",
    "RetryPolicy",
    "RetryOnCondition",
    "BackoffConfig",
    "BackoffStrategy",
    "IdempotencyConfig",
    "IdempotencyStrategy",
    "RateLimitBudget",
    "RiskLevel",
    "ConcurrencyConfig",
    "TimeoutConfig",
    "GlobalReliabilityDefaults",
    "merge_reliability_config",
    # Retry
    "RetryExecutor",
    "RetryContext",
    "RetryResult",
    "classify_error_for_retry",
    "create_retry_executor_from_config",
    "get_retry_after_ms",
    "should_retry_for_risk",
    # Rate limiting
    "RateLimiter",
    "RateLimitManager",
    # Concurrency
    "ConcurrencyManager",
    "ConcurrencySemaphore",
    # Idempotency
    "IdempotencyManager",
    "IdempotencyKey",
    "ExecutionRecord",
    "generate_idempotency_header",
    "generate_idempotency_key_for_provider",
    # Facade
    "ReliabilityManager",
    "ReliabilityContext",
    "ReliabilityResult",
]
