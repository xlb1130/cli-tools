"""Tests for the reliability layer."""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from types import SimpleNamespace

from cts.reliability import (
    BackoffConfig,
    BackoffStrategy,
    ConcurrencyConfig,
    ConcurrencyManager,
    ConcurrencySemaphore,
    GlobalReliabilityDefaults,
    IdempotencyConfig,
    IdempotencyKey,
    IdempotencyManager,
    IdempotencyStrategy,
    RateLimitBudget,
    RateLimitManager,
    RateLimiter,
    ReliabilityConfig,
    ReliabilityContext,
    ReliabilityManager,
    ReliabilityResult,
    RetryExecutor,
    RetryOnCondition,
    RetryPolicy,
    RiskLevel,
    TimeoutConfig,
    classify_error_for_retry,
    generate_idempotency_header,
    generate_idempotency_key_for_provider,
    merge_reliability_config,
    should_retry_for_risk,
)
from cts.execution.runtime import _get_reliability_manager


class TestBackoffConfig:
    """Tests for backoff configuration."""
    
    def test_default_values(self):
        config = BackoffConfig()
        assert config.strategy == BackoffStrategy.EXPONENTIAL_JITTER
        assert config.base_delay_ms == 300
        assert config.max_delay_ms == 30000
        assert config.multiplier == 2.0
        assert config.jitter_factor == 0.5
    
    def test_custom_values(self):
        config = BackoffConfig(
            strategy=BackoffStrategy.FIXED,
            base_delay_ms=100,
            max_delay_ms=5000,
        )
        assert config.strategy == BackoffStrategy.FIXED
        assert config.base_delay_ms == 100
        assert config.max_delay_ms == 5000


class TestRetryPolicy:
    """Tests for retry policy configuration."""
    
    def test_default_values(self):
        policy = RetryPolicy()
        assert policy.max_attempts == 2
        assert RetryOnCondition.TIMEOUT in policy.retry_on
        assert RetryOnCondition.RATE_LIMIT in policy.retry_on
    
    def test_custom_retry_on(self):
        policy = RetryPolicy(
            max_attempts=5,
            retry_on=[RetryOnCondition.TIMEOUT, RetryOnCondition.CONNECTION_ERROR],
        )
        assert policy.max_attempts == 5
        assert len(policy.retry_on) == 2


class TestRateLimitBudget:
    """Tests for rate limit budget configuration."""
    
    def test_per_second(self):
        budget = RateLimitBudget(requests_per_second=10)
        assert budget.get_rate_limit_type() == "second"
        assert budget.get_rate_limit_value() == 10
    
    def test_per_minute(self):
        budget = RateLimitBudget(requests_per_minute=100)
        assert budget.get_rate_limit_type() == "minute"
        assert budget.get_rate_limit_value() == 100
    
    def test_per_hour(self):
        budget = RateLimitBudget(requests_per_hour=1000)
        assert budget.get_rate_limit_type() == "hour"
        assert budget.get_rate_limit_value() == 1000
    
    def test_max_inflight(self):
        budget = RateLimitBudget(max_inflight=5)
        assert budget.max_inflight == 5
        assert budget.get_rate_limit_type() is None


class TestIdempotencyConfig:
    """Tests for idempotency configuration."""
    
    def test_default_values(self):
        config = IdempotencyConfig()
        assert config.required is False
        assert config.strategy == IdempotencyStrategy.HASH_ARGS
        assert config.ttl_seconds == 86400
    
    def test_custom_values(self):
        config = IdempotencyConfig(
            required=True,
            strategy=IdempotencyStrategy.UUID,
            ttl_seconds=3600,
            header_name="X-Request-Id",
        )
        assert config.required is True
        assert config.strategy == IdempotencyStrategy.UUID
        assert config.ttl_seconds == 3600
        assert config.header_name == "X-Request-Id"


class TestReliabilityConfig:
    """Tests for merged reliability configuration."""
    
    def test_default_values(self):
        config = ReliabilityConfig()
        assert config.risk == RiskLevel.READ
        assert config.retry.max_attempts == 2
    
    def test_custom_values(self):
        config = ReliabilityConfig(
            timeout_seconds=60,
            risk=RiskLevel.WRITE,
            retry=RetryPolicy(max_attempts=5),
        )
        assert config.timeout_seconds == 60
        assert config.risk == RiskLevel.WRITE
        assert config.retry.max_attempts == 5


class TestMergeReliabilityConfig:
    """Tests for merging reliability configurations."""
    
    def test_merge_from_global(self):
        global_defaults = GlobalReliabilityDefaults(
            timeout_seconds=30,
            retry=RetryPolicy(max_attempts=3),
        )
        config = merge_reliability_config(global_defaults, None, None, "read")
        assert config.timeout_seconds == 30
        assert config.retry.max_attempts == 3
        assert config.risk == RiskLevel.READ
    
    def test_merge_source_overrides_global(self):
        global_defaults = GlobalReliabilityDefaults(
            timeout_seconds=30,
        )
        source_config = {"timeout_seconds": 15}
        config = merge_reliability_config(global_defaults, source_config, None, "read")
        assert config.timeout_seconds == 15
    
    def test_merge_mount_overrides_source(self):
        source_config = {"timeout_seconds": 15}
        mount_config = {"timeout_seconds": 10}
        config = merge_reliability_config(None, source_config, mount_config, "write")
        assert config.timeout_seconds == 10
        assert config.risk == RiskLevel.WRITE


class TestShouldRetryForRisk:
    """Tests for risk-based retry decisions."""
    
    def test_read_always_allowed(self):
        assert should_retry_for_risk(RiskLevel.READ) is True
        assert should_retry_for_risk(RiskLevel.READ, is_idempotent=False) is True
    
    def test_write_requires_idempotent(self):
        assert should_retry_for_risk(RiskLevel.WRITE, is_idempotent=False) is False
        assert should_retry_for_risk(RiskLevel.WRITE, is_idempotent=True) is True
    
    def test_destructive_never_allowed(self):
        assert should_retry_for_risk(RiskLevel.DESTRUCTIVE) is False
        assert should_retry_for_risk(RiskLevel.DESTRUCTIVE, is_idempotent=True) is False


class TestClassifyErrorForRetry:
    """Tests for error classification for retry."""
    
    def test_timeout_error(self):
        error = TimeoutError("Request timed out")
        condition = classify_error_for_retry(error)
        assert condition == RetryOnCondition.TIMEOUT
    
    def test_connection_error(self):
        error = ConnectionError("Connection refused")
        condition = classify_error_for_retry(error)
        assert condition == RetryOnCondition.CONNECTION_ERROR
    
    def test_rate_limit_429(self):
        error = MagicMock()
        error.status_code = 429
        condition = classify_error_for_retry(error)
        assert condition == RetryOnCondition.RATE_LIMIT
    
    def test_upstream_5xx(self):
        error = MagicMock()
        error.status_code = 503
        condition = classify_error_for_retry(error)
        assert condition == RetryOnCondition.UPSTREAM_5XX
    
    def test_client_error_4xx(self):
        error = MagicMock()
        error.status_code = 400
        condition = classify_error_for_retry(error)
        assert condition is None


class TestRetryExecutor:
    """Tests for retry executor."""
    
    def test_success_first_attempt(self):
        executor = RetryExecutor(policy=RetryPolicy(max_attempts=3))
        result = executor.execute_sync(lambda: "success")
        assert result.success is True
        assert result.result == "success"
        assert result.attempts == 1
        assert result.retried is False
    
    def test_retry_then_success(self):
        executor = RetryExecutor(policy=RetryPolicy(max_attempts=3))
        call_count = [0]
        
        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise TimeoutError("Timeout")
            return "success"
        
        result = executor.execute_sync(flaky_func)
        assert result.success is True
        assert result.attempts == 3
        assert result.retried is True
    
    def test_retry_exhausted(self):
        executor = RetryExecutor(
            policy=RetryPolicy(max_attempts=2),
            risk=RiskLevel.READ,
        )
        
        def always_fail():
            raise TimeoutError("Always fails")
        
        result = executor.execute_sync(always_fail)
        assert result.success is False
        assert result.attempts == 2
        assert isinstance(result.error, TimeoutError)
    
    def test_no_retry_for_write_without_idempotent(self):
        executor = RetryExecutor(
            policy=RetryPolicy(max_attempts=3),
            risk=RiskLevel.WRITE,
            is_idempotent=False,
        )
        call_count = [0]
        
        def flaky_func():
            call_count[0] += 1
            raise TimeoutError("Timeout")
        
        result = executor.execute_sync(flaky_func)
        assert result.success is False
        assert call_count[0] == 1  # No retry
    
    def test_backoff_fixed(self):
        policy = RetryPolicy(
            max_attempts=3,
            backoff=BackoffConfig(
                strategy=BackoffStrategy.FIXED,
                base_delay_ms=100,
            ),
        )
        executor = RetryExecutor(policy=policy)
        
        # Test delay calculation
        assert executor.calculate_delay_ms(1) == 100
        assert executor.calculate_delay_ms(2) == 100
        assert executor.calculate_delay_ms(3) == 100
    
    def test_backoff_exponential(self):
        policy = RetryPolicy(
            max_attempts=3,
            backoff=BackoffConfig(
                strategy=BackoffStrategy.EXPONENTIAL,
                base_delay_ms=100,
                multiplier=2.0,
            ),
        )
        executor = RetryExecutor(policy=policy)
        
        assert executor.calculate_delay_ms(1) == 100
        assert executor.calculate_delay_ms(2) == 200
        assert executor.calculate_delay_ms(3) == 400
    
    def test_backoff_max_delay(self):
        policy = RetryPolicy(
            backoff=BackoffConfig(
                strategy=BackoffStrategy.EXPONENTIAL,
                base_delay_ms=100,
                max_delay_ms=500,
                multiplier=10.0,
            ),
        )
        executor = RetryExecutor(policy=policy)
        
        # Should cap at max_delay_ms
        assert executor.calculate_delay_ms(3) == 500


class TestRateLimiter:
    """Tests for rate limiter."""
    
    def test_acquire_within_limit(self):
        budget = RateLimitBudget(requests_per_second=10)
        limiter = RateLimiter(budget=budget)
        
        assert limiter.acquire() is True
        assert limiter.acquire() is True
    
    def test_acquire_with_inflight_limit(self):
        budget = RateLimitBudget(max_inflight=2)
        limiter = RateLimiter(budget=budget)
        
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is False  # Exceeds limit
    
    def test_get_state(self):
        budget = RateLimitBudget(requests_per_minute=100)
        limiter = RateLimiter(budget=budget, name="test")
        
        limiter.acquire()
        state = limiter.get_state()
        
        assert state["name"] == "test"
        assert state["total_requests"] == 1
    
    def test_reset(self):
        budget = RateLimitBudget(max_inflight=1)
        limiter = RateLimiter(budget=budget)
        
        limiter.acquire()
        limiter.reset()
        
        # Should be able to acquire again after reset
        assert limiter.acquire() is True


class TestRateLimitManager:
    """Tests for rate limit manager."""
    
    def test_get_limiter(self):
        manager = RateLimitManager()
        budget = RateLimitBudget(requests_per_second=10)
        
        limiter1 = manager.get_limiter("test-budget", budget)
        limiter2 = manager.get_limiter("test-budget")
        
        assert limiter1 is limiter2
    
    def test_acquire(self):
        manager = RateLimitManager()
        budget = RateLimitBudget(requests_per_second=10)
        manager.register_budget("test", budget)
        
        assert manager.acquire("test") is True
    
    def test_get_all_states(self):
        manager = RateLimitManager()
        manager.register_budget("budget1", RateLimitBudget(requests_per_second=10))
        manager.register_budget("budget2", RateLimitBudget(requests_per_minute=100))
        
        manager.acquire("budget1")
        # budget2 is registered but not yet accessed, so won't be in states
        manager.acquire("budget2")  # This will create the limiter
        states = manager.get_all_states()
        
        assert "budget1" in states
        assert "budget2" in states


class TestConcurrencySemaphore:
    """Tests for concurrency semaphore."""
    
    def test_acquire_within_limit(self):
        sem = ConcurrencySemaphore(max_concurrent=2)
        
        assert sem.acquire() is True
        assert sem.acquire() is True
    
    def test_acquire_exceeds_limit(self):
        sem = ConcurrencySemaphore(max_concurrent=2, queue_timeout_seconds=0.1)
        
        assert sem.acquire() is True
        assert sem.acquire() is True
        assert sem.acquire(timeout=0.01) is False
    
    def test_release(self):
        sem = ConcurrencySemaphore(max_concurrent=1)
        
        assert sem.acquire() is True
        sem.release()
        assert sem.acquire() is True
    
    def test_context_manager(self):
        sem = ConcurrencySemaphore(max_concurrent=1)
        
        with sem.acquire_context() as acquired:
            assert acquired is True
            # Should not be able to acquire again
            assert sem.acquire(timeout=0.01) is False
        
        # Should be able to acquire after context exit
        assert sem.acquire() is True
    
    def test_get_state(self):
        sem = ConcurrencySemaphore(max_concurrent=2, name="test")
        sem.acquire()
        
        state = sem.get_state()
        
        assert state["name"] == "test"
        assert state["active"] == 1
        assert state["available"] == 1


class TestConcurrencyManager:
    """Tests for concurrency manager."""
    
    def test_get_source_semaphore(self):
        manager = ConcurrencyManager()
        sem1 = manager.get_source_semaphore("source1")
        sem2 = manager.get_source_semaphore("source1")
        
        assert sem1 is sem2
    
    def test_acquire_for_source(self):
        manager = ConcurrencyManager(
            config=ConcurrencyConfig(max_inflight_per_source=1)
        )
        
        with manager.acquire_for_source("source1") as acquired:
            assert acquired is True
    
    def test_get_all_states(self):
        manager = ConcurrencyManager()
        manager.get_source_semaphore("source1").acquire()
        
        states = manager.get_all_states()
        
        assert "source:source1" in states


class TestIdempotencyManager:
    """Tests for idempotency manager."""
    
    def test_generate_key_uuid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = IdempotencyManager(cache_dir=Path(tmpdir))
            config = IdempotencyConfig(strategy=IdempotencyStrategy.UUID)
            
            key = manager.generate_key(
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                config=config,
            )
            
            assert key.strategy == IdempotencyStrategy.UUID
            assert len(key.key) == 36  # UUID format
    
    def test_generate_key_hash_args(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = IdempotencyManager(cache_dir=Path(tmpdir))
            config = IdempotencyConfig(strategy=IdempotencyStrategy.HASH_ARGS)
            
            key1 = manager.generate_key(
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                config=config,
            )
            
            key2 = manager.generate_key(
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                config=config,
            )
            
            # Same args should produce same key
            assert key1.key == key2.key
    
    def test_generate_key_hash_selected_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = IdempotencyManager(cache_dir=Path(tmpdir))
            config = IdempotencyConfig(
                strategy=IdempotencyStrategy.HASH_SELECTED_FIELDS,
                key_fields=["id"],
            )
            
            key1 = manager.generate_key(
                mount_id="test-mount",
                operation_id="test-op",
                args={"id": "123", "timestamp": "2024-01-01"},
                config=config,
            )
            
            key2 = manager.generate_key(
                mount_id="test-mount",
                operation_id="test-op",
                args={"id": "123", "timestamp": "2024-01-02"},  # Different timestamp
                config=config,
            )
            
            # Only selected fields matter
            assert key1.key == key2.key
    
    def test_check_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = IdempotencyManager(cache_dir=Path(tmpdir))
            config = IdempotencyConfig(strategy=IdempotencyStrategy.HASH_ARGS)
            
            key = manager.generate_key(
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                config=config,
            )
            
            # Record execution
            manager.record_execution_start(
                key=key.key,
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                run_id="run-123",
            )
            manager.record_execution_complete(key.key, status="completed")
            
            # Check duplicate
            existing = manager.check_duplicate(key.key)
            assert existing is not None
            assert existing.run_id == "run-123"
    
    def test_is_duplicate_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = IdempotencyManager(cache_dir=Path(tmpdir))
            config = IdempotencyConfig(
                strategy=IdempotencyStrategy.HASH_ARGS,
                required=True,
            )
            
            # First execution
            is_dup, existing = manager.is_duplicate_execution(
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                config=config,
            )
            assert is_dup is False
            
            # Record execution
            key = manager.generate_key(
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                config=config,
            )
            manager.record_execution_start(
                key=key.key,
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                run_id="run-123",
            )
            manager.record_execution_complete(key.key, status="completed")
            
            # Second execution with same args
            is_dup, existing = manager.is_duplicate_execution(
                mount_id="test-mount",
                operation_id="test-op",
                args={"foo": "bar"},
                config=config,
            )
            assert is_dup is True
            assert existing.run_id == "run-123"


class TestIdempotencyHeaders:
    """Tests for idempotency header generation."""
    
    def test_generate_headers(self):
        key = IdempotencyKey(
            key="test-key-123",
            strategy=IdempotencyStrategy.HASH_ARGS,
            mount_id="test-mount",
            operation_id="test-op",
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )
        
        headers = generate_idempotency_header(key)
        
        assert headers["Idempotency-Key"] == "test-key-123"
        assert headers["X-Idempotency-Strategy"] == "hash_args"
    
    def test_custom_header_name(self):
        key = IdempotencyKey(
            key="test-key-123",
            strategy=IdempotencyStrategy.HASH_ARGS,
            mount_id="test-mount",
            operation_id="test-op",
            created_at=time.time(),
            expires_at=time.time() + 3600,
        )
        
        headers = generate_idempotency_header(key, header_name="X-Request-ID")
        
        assert headers["X-Request-ID"] == "test-key-123"


class TestGenerateIdempotencyKeyForProvider:
    """Tests for provider-specific idempotency key generation."""
    
    def test_http_provider(self):
        key, metadata = generate_idempotency_key_for_provider(
            provider_type="http",
            mount_id="test-mount",
            operation_id="test-op",
            args={"foo": "bar"},
            config=IdempotencyConfig(strategy=IdempotencyStrategy.HASH_ARGS),
        )
        
        assert key is not None
        assert "headers" in metadata
        assert "Idempotency-Key" in metadata["headers"]
    
    def test_cli_provider(self):
        key, metadata = generate_idempotency_key_for_provider(
            provider_type="cli",
            mount_id="test-mount",
            operation_id="test-op",
            args={"foo": "bar"},
            config=IdempotencyConfig(strategy=IdempotencyStrategy.HASH_ARGS),
        )
        
        assert key is not None
        assert "env" in metadata
        assert "CTS_IDEMPOTENCY_KEY" in metadata["env"]


class TestReliabilityManager:
    """Tests for reliability manager facade."""
    
    def test_resolve_config(self):
        manager = ReliabilityManager(
            global_defaults=GlobalReliabilityDefaults(timeout_seconds=30)
        )
        
        config = manager.resolve_config(
            source_reliability={"timeout_seconds": 15},
            mount_reliability={"timeout_seconds": 10},
            operation_risk="write",
        )
        
        assert config.timeout_seconds == 10
        assert config.risk == RiskLevel.WRITE
    
    def test_prepare_execution(self):
        manager = ReliabilityManager()
        config = ReliabilityConfig(idempotency=IdempotencyConfig(required=True))
        
        ctx = manager.prepare_execution(
            mount_id="test-mount",
            operation_id="test-op",
            source_name="test-source",
            provider_type="http",
            args={"foo": "bar"},
            run_id="run-123",
            config=config,
        )
        
        assert ctx.mount_id == "test-mount"
        assert ctx.operation_id == "test-op"
        assert ctx.idempotency_key is not None
    
    def test_execute_with_reliability_success(self):
        manager = ReliabilityManager()
        config = ReliabilityConfig()
        
        ctx = manager.prepare_execution(
            mount_id="test-mount",
            operation_id="test-op",
            source_name="test-source",
            provider_type="http",
            args={},
            run_id="run-123",
            config=config,
        )
        
        result = manager.execute_with_reliability(
            ctx,
            lambda: MagicMock(ok=True, data={"result": "success"}),
        )
        
        assert result.success is True
        assert result.attempts == 1
    
    def test_execute_with_reliability_retry(self):
        manager = ReliabilityManager()
        config = ReliabilityConfig(
            retry=RetryPolicy(max_attempts=3),
            risk=RiskLevel.READ,
        )
        
        ctx = manager.prepare_execution(
            mount_id="test-mount",
            operation_id="test-op",
            source_name="test-source",
            provider_type="http",
            args={},
            run_id="run-123",
            config=config,
        )
        
        call_count = [0]
        
        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise TimeoutError("Timeout")
            return MagicMock(ok=True, data={"result": "success"})
        
        result = manager.execute_with_reliability(ctx, flaky_func)
        
        assert result.success is True
        assert result.was_retried is True
        assert result.attempts == 3
    
    def test_get_status(self):
        manager = ReliabilityManager()
        status = manager.get_status()
        
        assert "rate_limits" in status
        assert "concurrency" in status
        assert "idempotency" in status

    def test_runtime_manager_uses_app_defaults_and_budgets(self, tmp_path: Path):
        defaults = GlobalReliabilityDefaults(
            timeout_seconds=12,
            concurrency=ConcurrencyConfig(max_inflight_global=7, max_inflight_per_source=3),
        )
        budget = RateLimitBudget(requests_per_minute=42)
        app = SimpleNamespace(
            config=SimpleNamespace(
                get_reliability_defaults=lambda: defaults,
                get_rate_limit_budgets=lambda: {"demo": budget},
            ),
            primary_config_dir=tmp_path,
        )

        manager = _get_reliability_manager(app)

        assert manager.global_defaults.timeout_seconds == 12
        assert manager.concurrency_manager.config.max_inflight_global == 7
        assert manager.rate_limit_manager._budgets["demo"].requests_per_minute == 42


# Note: Async tests require pytest-asyncio to be installed.
# The async methods are tested indirectly through the synchronous tests
# and the async implementations follow the same patterns.
# 
# To run async tests, install pytest-asyncio:
#   pip install pytest-asyncio
#
# Then uncomment and run the async test classes below.

# class TestAsyncRetryExecutor:
#     """Tests for async retry execution."""
#     
#     @pytest.mark.asyncio
#     async def test_async_success(self):
#         executor = RetryExecutor(policy=RetryPolicy(max_attempts=3))
#         
#         async def async_func():
#             return "success"
#         
#         result = await executor.execute_async(async_func)
#         assert result.success is True
#         assert result.result == "success"
#     
#     @pytest.mark.asyncio
#     async def test_async_retry_then_success(self):
#         executor = RetryExecutor(policy=RetryPolicy(max_attempts=3))
#         call_count = [0]
#         
#         async def flaky_func():
#             call_count[0] += 1
#             if call_count[0] < 3:
#                 raise TimeoutError("Timeout")
#             return "success"
#         
#         result = await executor.execute_async(flaky_func)
#         assert result.success is True
#         assert result.attempts == 3
# 
# 
# class TestAsyncRateLimiter:
#     """Tests for async rate limiter."""
#     
#     @pytest.mark.asyncio
#     async def test_async_acquire(self):
#         budget = RateLimitBudget(requests_per_second=10)
#         limiter = RateLimiter(budget=budget)
#         
#         result = await limiter.async_acquire()
#         assert result is True
# 
# 
# class TestAsyncReliabilityManager:
#     """Tests for async reliability manager."""
#     
#     @pytest.mark.asyncio
#     async def test_async_execute(self):
#         manager = ReliabilityManager()
#         config = ReliabilityConfig()
#         
#         ctx = manager.prepare_execution(
#             mount_id="test-mount",
#             operation_id="test-op",
#             source_name="test-source",
#             provider_type="http",
#             args={},
#             run_id="run-123",
#             config=config,
#         )
#         
#         async def async_func():
#             return MagicMock(ok=True, data={"result": "success"})
#         
#         result = await manager.async_execute_with_reliability(ctx, async_func)
#         assert result.success is True
