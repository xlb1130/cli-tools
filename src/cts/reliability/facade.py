"""Reliability manager facade that integrates all reliability components."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

from cts.reliability.concurrency import ConcurrencyManager, ConcurrencySemaphore
from cts.reliability.idempotency import (
    ExecutionRecord,
    IdempotencyKey,
    IdempotencyManager,
)
from cts.reliability.models import (
    GlobalReliabilityDefaults,
    RateLimitBudget,
    ReliabilityConfig,
    RetryOnCondition,
    RetryPolicy,
    RiskLevel,
    merge_reliability_config,
)
from cts.reliability.rate_limiter import RateLimitManager, RateLimiter
from cts.reliability.retry import (
    RetryContext,
    RetryExecutor,
    RetryResult,
    classify_error_for_retry,
    create_retry_executor_from_config,
    should_retry_for_risk,
)

T = TypeVar("T")


@dataclass
class ReliabilityContext:
    """Context for a reliability-wrapped execution."""
    mount_id: str
    operation_id: str
    source_name: str
    provider_type: str
    args: Dict[str, Any]
    run_id: str
    
    # Resolved config
    config: ReliabilityConfig = field(default_factory=ReliabilityConfig)
    
    # Generated idempotency key (if applicable)
    idempotency_key: Optional[IdempotencyKey] = None
    
    # Execution tracking
    attempt: int = 0
    start_time: float = 0.0
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the context."""
        self.events.append({
            "type": event_type,
            "timestamp": time.time(),
            "attempt": self.attempt,
            **(data or {}),
        })


@dataclass
class ReliabilityResult:
    """Result of a reliability-wrapped execution."""
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    
    # Execution metadata
    attempts: int = 0
    total_delay_ms: int = 0
    duration_ms: int = 0
    
    # Reliability metadata
    was_retried: bool = False
    was_rate_limited: bool = False
    was_duplicate: bool = False
    idempotency_key: Optional[str] = None
    
    # Events for logging
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "attempts": self.attempts,
            "total_delay_ms": self.total_delay_ms,
            "duration_ms": self.duration_ms,
            "was_retried": self.was_retried,
            "was_rate_limited": self.was_rate_limited,
            "was_duplicate": self.was_duplicate,
            "idempotency_key": self.idempotency_key,
        }


class ReliabilityManager:
    """Facade for all reliability components.
    
    This class integrates:
    - Retry with backoff
    - Rate limiting with budgets
    - Concurrency control
    - Idempotency key management
    - Risk-based execution policies
    """
    
    def __init__(
        self,
        global_defaults: Optional[GlobalReliabilityDefaults] = None,
        cache_dir: Optional[Path] = None,
        on_retry: Optional[Callable[[ReliabilityContext], None]] = None,
        on_rate_limited: Optional[Callable[[str, float], None]] = None,
    ):
        self.global_defaults = global_defaults or GlobalReliabilityDefaults()
        self.cache_dir = cache_dir or Path.home() / ".cts" / "reliability"
        
        # Component managers
        self.rate_limit_manager = RateLimitManager()
        self.concurrency_manager = ConcurrencyManager(self.global_defaults.concurrency)
        self.idempotency_manager = IdempotencyManager(cache_dir=self.cache_dir)
        
        # Callbacks
        self.on_retry = on_retry
        self.on_rate_limited = on_rate_limited
    
    def resolve_config(
        self,
        source_reliability: Optional[Dict[str, Any]] = None,
        mount_reliability: Optional[Dict[str, Any]] = None,
        operation_risk: str = "read",
    ) -> ReliabilityConfig:
        """Resolve reliability config from global, source, and mount levels."""
        return merge_reliability_config(
            self.global_defaults,
            source_reliability,
            mount_reliability,
            operation_risk,
        )
    
    def prepare_execution(
        self,
        mount_id: str,
        operation_id: str,
        source_name: str,
        provider_type: str,
        args: Dict[str, Any],
        run_id: str,
        config: ReliabilityConfig,
    ) -> ReliabilityContext:
        """Prepare context for an execution."""
        ctx = ReliabilityContext(
            mount_id=mount_id,
            operation_id=operation_id,
            source_name=source_name,
            provider_type=provider_type,
            args=args,
            run_id=run_id,
            config=config,
            start_time=time.time(),
        )
        
        # Generate idempotency key if required
        if config.idempotency.required:
            ctx.idempotency_key = self.idempotency_manager.generate_key(
                mount_id=mount_id,
                operation_id=operation_id,
                args=args,
                config=config.idempotency,
            )
            ctx.add_event("idempotency_key_generated", {
                "key": ctx.idempotency_key.key,
                "strategy": ctx.idempotency_key.strategy.value,
            })
        
        return ctx
    
    def check_duplicate(
        self,
        ctx: ReliabilityContext,
    ) -> Optional[ExecutionRecord]:
        """Check if this execution is a duplicate."""
        if not ctx.idempotency_key:
            return None
        
        existing = self.idempotency_manager.check_duplicate(
            ctx.idempotency_key.key,
            ctx.config.idempotency.ttl_seconds,
        )
        
        if existing:
            ctx.add_event("duplicate_execution_blocked", {
                "existing_run_id": existing.run_id,
                "existing_status": existing.status,
            })
        
        return existing
    
    def acquire_rate_limit(
        self,
        ctx: ReliabilityContext,
        budget_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """Acquire rate limit tokens."""
        key = budget_key or ctx.config.budget_key or f"source:{ctx.source_name}"
        
        if not ctx.config.rate_limit.get_rate_limit_value():
            return True  # No rate limit configured
        
        limiter = self.rate_limit_manager.get_limiter(
            budget_key=key,
            budget=ctx.config.rate_limit,
            on_limited=self.on_rate_limited,
        )
        
        acquired = limiter.acquire()
        
        if not acquired:
            ctx.add_event("rate_limit_hit", {
                "budget_key": key,
                "wait_time_ms": limiter._calculate_wait_time() * 1000,
            })
        
        return acquired
    
    def acquire_concurrency(
        self,
        ctx: ReliabilityContext,
        timeout: Optional[float] = None,
    ) -> bool:
        """Acquire concurrency semaphore."""
        sem = self.concurrency_manager.get_source_semaphore(ctx.source_name)
        acquired = sem.acquire(timeout or ctx.config.concurrency.queue_timeout_seconds)
        
        if not acquired:
            ctx.add_event("concurrency_timeout", {
                "source": ctx.source_name,
                "max_concurrent": sem.max_concurrent,
            })
        
        return acquired
    
    def release_concurrency(self, ctx: ReliabilityContext) -> None:
        """Release concurrency semaphore."""
        sem = self.concurrency_manager.get_source_semaphore(ctx.source_name)
        sem.release()
    
    def execute_with_reliability(
        self,
        ctx: ReliabilityContext,
        func: Callable[[], T],
        is_idempotent: bool = False,
    ) -> ReliabilityResult:
        """Execute function with full reliability guarantees."""
        
        # Check for duplicate execution
        if ctx.idempotency_key:
            existing = self.check_duplicate(ctx)
            if existing and existing.status == "completed":
                return ReliabilityResult(
                    success=True,
                    result=None,  # Original result not stored
                    was_duplicate=True,
                    idempotency_key=ctx.idempotency_key.key,
                    events=ctx.events,
                )
        
        # Acquire rate limit
        if not self.acquire_rate_limit(ctx):
            return ReliabilityResult(
                success=False,
                error=Exception("Rate limit exceeded"),
                was_rate_limited=True,
                events=ctx.events,
            )
        
        # Acquire concurrency
        if not self.acquire_concurrency(ctx):
            return ReliabilityResult(
                success=False,
                error=Exception("Concurrency limit exceeded"),
                events=ctx.events,
            )
        
        try:
            # Record execution start for idempotency
            if ctx.idempotency_key:
                self.idempotency_manager.record_execution_start(
                    key=ctx.idempotency_key.key,
                    mount_id=ctx.mount_id,
                    operation_id=ctx.operation_id,
                    args=ctx.args,
                    run_id=ctx.run_id,
                )
            
            # Execute with retry
            executor = create_retry_executor_from_config(
                ctx.config,
                is_idempotent=is_idempotent or ctx.config.idempotency.required,
            )
            
            def on_retry_callback(retry_ctx: RetryContext) -> None:
                ctx.attempt = retry_ctx.attempt
                ctx.add_event("retry_scheduled", {
                    "delay_ms": retry_ctx.last_delay_ms,
                    "total_delay_ms": retry_ctx.total_delay_ms,
                })
                if self.on_retry:
                    self.on_retry(ctx)
            
            retry_result = executor.execute_sync(func, on_retry=on_retry_callback)
            
            # Record completion
            if ctx.idempotency_key:
                self.idempotency_manager.record_execution_complete(
                    ctx.idempotency_key.key,
                    status="completed" if retry_result.success else "failed",
                )
            
            duration_ms = int((time.time() - ctx.start_time) * 1000)
            
            return ReliabilityResult(
                success=retry_result.success,
                result=retry_result.result,
                error=retry_result.error,
                attempts=retry_result.attempts,
                total_delay_ms=retry_result.total_delay_ms,
                duration_ms=duration_ms,
                was_retried=retry_result.retried,
                idempotency_key=ctx.idempotency_key.key if ctx.idempotency_key else None,
                events=ctx.events + retry_result.events,
            )
        
        finally:
            self.release_concurrency(ctx)
    
    async def async_execute_with_reliability(
        self,
        ctx: ReliabilityContext,
        func: Callable[[], T],
        is_idempotent: bool = False,
    ) -> ReliabilityResult:
        """Async version of execute_with_reliability."""
        import asyncio
        
        # Check for duplicate execution
        if ctx.idempotency_key:
            existing = self.check_duplicate(ctx)
            if existing and existing.status == "completed":
                return ReliabilityResult(
                    success=True,
                    result=None,
                    was_duplicate=True,
                    idempotency_key=ctx.idempotency_key.key,
                    events=ctx.events,
                )
        
        # Acquire rate limit
        if not self.acquire_rate_limit(ctx):
            return ReliabilityResult(
                success=False,
                error=Exception("Rate limit exceeded"),
                was_rate_limited=True,
                events=ctx.events,
            )
        
        # Acquire concurrency (async)
        acquired = await self.concurrency_manager.async_acquire_for_source(ctx.source_name)
        if not acquired:
            return ReliabilityResult(
                success=False,
                error=Exception("Concurrency limit exceeded"),
                events=ctx.events,
            )
        
        try:
            # Record execution start
            if ctx.idempotency_key:
                self.idempotency_manager.record_execution_start(
                    key=ctx.idempotency_key.key,
                    mount_id=ctx.mount_id,
                    operation_id=ctx.operation_id,
                    args=ctx.args,
                    run_id=ctx.run_id,
                )
            
            # Execute with retry
            executor = create_retry_executor_from_config(
                ctx.config,
                is_idempotent=is_idempotent or ctx.config.idempotency.required,
            )
            
            def on_retry_callback(retry_ctx: RetryContext) -> None:
                ctx.attempt = retry_ctx.attempt
                ctx.add_event("retry_scheduled", {
                    "delay_ms": retry_ctx.last_delay_ms,
                })
                if self.on_retry:
                    self.on_retry(ctx)
            
            retry_result = await executor.execute_async(func, on_retry=on_retry_callback)
            
            # Record completion
            if ctx.idempotency_key:
                self.idempotency_manager.record_execution_complete(
                    ctx.idempotency_key.key,
                    status="completed" if retry_result.success else "failed",
                )
            
            duration_ms = int((time.time() - ctx.start_time) * 1000)
            
            return ReliabilityResult(
                success=retry_result.success,
                result=retry_result.result,
                error=retry_result.error,
                attempts=retry_result.attempts,
                total_delay_ms=retry_result.total_delay_ms,
                duration_ms=duration_ms,
                was_retried=retry_result.retried,
                idempotency_key=ctx.idempotency_key.key if ctx.idempotency_key else None,
                events=ctx.events + retry_result.events,
            )
        
        finally:
            await self.concurrency_manager.async_release_for_source(ctx.source_name)
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all reliability components."""
        return {
            "rate_limits": self.rate_limit_manager.get_all_states(),
            "concurrency": self.concurrency_manager.get_all_states(),
            "idempotency": self.idempotency_manager.get_stats(),
        }
    
    def register_budget(self, key: str, budget: RateLimitBudget) -> None:
        """Register a rate limit budget."""
        self.rate_limit_manager.register_budget(key, budget)
    
    def reset_all(self) -> None:
        """Reset all reliability state."""
        self.rate_limit_manager.reset_all()
        self.concurrency_manager.reset_all()
        self.idempotency_manager.clear_cache()
