"""Retry execution with backoff strategies and risk-based control."""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

from cts.reliability.models import (
    BackoffStrategy,
    ReliabilityConfig,
    RetryOnCondition,
    RetryPolicy,
    RiskLevel,
)

T = TypeVar("T")


@dataclass
class RetryContext:
    """Context for retry execution."""
    attempt: int = 0
    max_attempts: int = 2
    last_error: Optional[Exception] = None
    last_delay_ms: int = 0
    total_delay_ms: int = 0
    retry_conditions: List[RetryOnCondition] = field(default_factory=list)
    
    # Event tracking
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Add a retry event."""
        self.events.append({
            "type": event_type,
            "attempt": self.attempt,
            "timestamp": time.time(),
            **(data or {}),
        })


@dataclass
class RetryResult:
    """Result of retry execution."""
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    attempts: int = 0
    total_delay_ms: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def retried(self) -> bool:
        return self.attempts > 1


class RetryExecutor:
    """Executor with retry logic, backoff, and risk-based control."""
    
    def __init__(
        self,
        policy: Optional[RetryPolicy] = None,
        risk: RiskLevel = RiskLevel.READ,
        is_idempotent: bool = False,
    ):
        self.policy = policy or RetryPolicy()
        self.risk = risk
        self.is_idempotent = is_idempotent
    
    def can_retry(self, ctx: RetryContext, error: Exception) -> bool:
        """Determine if retry is allowed based on risk level and error type."""
        # Check max attempts
        if ctx.attempt >= ctx.max_attempts:
            return False
        
        # Risk-based retry rules
        if not should_retry_for_risk(self.risk, self.is_idempotent):
            return False
        
        # Check error condition
        condition = classify_error_for_retry(error)
        if condition is None:
            return False
        
        return condition in ctx.retry_conditions
    
    def calculate_delay_ms(self, attempt: int) -> int:
        """Calculate delay in milliseconds for given attempt number."""
        backoff = self.policy.backoff
        base = backoff.base_delay_ms
        
        if backoff.strategy == BackoffStrategy.FIXED:
            delay = base
        
        elif backoff.strategy == BackoffStrategy.LINEAR:
            delay = base * attempt
        
        elif backoff.strategy == BackoffStrategy.EXPONENTIAL:
            delay = base * (backoff.multiplier ** (attempt - 1))
        
        elif backoff.strategy == BackoffStrategy.EXPONENTIAL_JITTER:
            # Exponential with full jitter
            exponential_delay = base * (backoff.multiplier ** (attempt - 1))
            jitter_range = int(exponential_delay * backoff.jitter_factor)
            jitter = random.randint(0, jitter_range)
            delay = exponential_delay - jitter_range // 2 + jitter
        
        else:
            delay = base
        
        # Cap at max delay
        return min(int(delay), backoff.max_delay_ms)
    
    def execute_sync(
        self,
        func: Callable[[], T],
        on_retry: Optional[Callable[[RetryContext], None]] = None,
    ) -> RetryResult:
        """Execute function with retry logic (synchronous)."""
        ctx = RetryContext(
            max_attempts=self.policy.max_attempts,
            retry_conditions=list(self.policy.retry_on),
        )
        
        while True:
            ctx.attempt += 1
            ctx.add_event("attempt_started")
            
            try:
                result = func()
                ctx.add_event("attempt_succeeded")
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=ctx.attempt,
                    total_delay_ms=ctx.total_delay_ms,
                    events=ctx.events,
                )
            
            except Exception as e:
                ctx.last_error = e
                ctx.add_event("attempt_failed", {"error_type": type(e).__name__})
                
                # Check if we can retry
                if not self.can_retry(ctx, e):
                    ctx.add_event("retry_exhausted")
                    return RetryResult(
                        success=False,
                        error=e,
                        attempts=ctx.attempt,
                        total_delay_ms=ctx.total_delay_ms,
                        events=ctx.events,
                    )
                
                # Calculate and apply delay
                delay_ms = self.calculate_delay_ms(ctx.attempt)
                ctx.last_delay_ms = delay_ms
                ctx.total_delay_ms += delay_ms
                
                ctx.add_event("retry_scheduled", {
                    "delay_ms": delay_ms,
                    "next_attempt": ctx.attempt + 1,
                })
                
                if on_retry:
                    on_retry(ctx)
                
                # Wait before retry
                time.sleep(delay_ms / 1000.0)
    
    async def execute_async(
        self,
        func: Callable[[], T],
        on_retry: Optional[Callable[[RetryContext], None]] = None,
    ) -> RetryResult:
        """Execute function with retry logic (asynchronous)."""
        ctx = RetryContext(
            max_attempts=self.policy.max_attempts,
            retry_conditions=list(self.policy.retry_on),
        )
        
        while True:
            ctx.attempt += 1
            ctx.add_event("attempt_started")
            
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func()
                else:
                    result = func()
                ctx.add_event("attempt_succeeded")
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=ctx.attempt,
                    total_delay_ms=ctx.total_delay_ms,
                    events=ctx.events,
                )
            
            except Exception as e:
                ctx.last_error = e
                ctx.add_event("attempt_failed", {"error_type": type(e).__name__})
                
                # Check if we can retry
                if not self.can_retry(ctx, e):
                    ctx.add_event("retry_exhausted")
                    return RetryResult(
                        success=False,
                        error=e,
                        attempts=ctx.attempt,
                        total_delay_ms=ctx.total_delay_ms,
                        events=ctx.events,
                    )
                
                # Calculate and apply delay
                delay_ms = self.calculate_delay_ms(ctx.attempt)
                ctx.last_delay_ms = delay_ms
                ctx.total_delay_ms += delay_ms
                
                ctx.add_event("retry_scheduled", {
                    "delay_ms": delay_ms,
                    "next_attempt": ctx.attempt + 1,
                })
                
                if on_retry:
                    on_retry(ctx)
                
                # Wait before retry
                await asyncio.sleep(delay_ms / 1000.0)


def should_retry_for_risk(risk: RiskLevel, is_idempotent: bool = False) -> bool:
    """Determine if retry is allowed based on risk level.
    
    Rules:
    - READ: Always allow retry
    - WRITE: Allow retry only if operation is idempotent
    - DESTRUCTIVE: Never allow automatic retry
    """
    if risk == RiskLevel.READ:
        return True
    elif risk == RiskLevel.WRITE:
        return is_idempotent
    elif risk == RiskLevel.DESTRUCTIVE:
        return False
    return False


def classify_error_for_retry(error: Exception) -> Optional[RetryOnCondition]:
    """Classify an error to determine retry condition."""
    error_type = type(error).__name__
    error_message = str(error).lower()
    
    # Timeout errors
    if "timeout" in error_type.lower() or "timeout" in error_message:
        return RetryOnCondition.TIMEOUT
    
    # Rate limit errors
    if "ratelimit" in error_type.lower() or "rate" in error_message and "limit" in error_message:
        return RetryOnCondition.RATE_LIMIT
    if hasattr(error, "status_code"):
        status = getattr(error, "status_code", None)
        if status == 429:
            return RetryOnCondition.RATE_LIMIT
    
    # Upstream errors
    if hasattr(error, "status_code"):
        status = getattr(error, "status_code", None)
        if status and 500 <= status < 600:
            return RetryOnCondition.UPSTREAM_5XX
        if status and 400 <= status < 500:
            return None  # Client errors should not be retried
    
    # Connection errors
    if "connection" in error_type.lower() or "connection" in error_message:
        return RetryOnCondition.CONNECTION_ERROR
    
    # Network/transient errors
    if any(word in error_type.lower() for word in ["network", "socket", "dns", "refused"]):
        return RetryOnCondition.TRANSIENT_ERROR
    
    # Check for common transient error patterns
    transient_patterns = [
        "connection reset",
        "broken pipe",
        "temporary failure",
        "service unavailable",
        "gateway timeout",
        "bad gateway",
    ]
    if any(pattern in error_message for pattern in transient_patterns):
        return RetryOnCondition.TRANSIENT_ERROR
    
    return None


def get_retry_after_ms(error: Exception) -> Optional[int]:
    """Extract Retry-After value from error if available."""
    if hasattr(error, "headers"):
        headers = getattr(error, "headers", {}) or {}
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                # Try parsing as seconds
                return int(retry_after) * 1000
            except ValueError:
                pass
    return None


def create_retry_executor_from_config(
    config: ReliabilityConfig,
    is_idempotent: bool = False,
) -> RetryExecutor:
    """Create a RetryExecutor from ReliabilityConfig."""
    return RetryExecutor(
        policy=config.retry,
        risk=config.risk,
        is_idempotent=is_idempotent or config.idempotency.required,
    )
