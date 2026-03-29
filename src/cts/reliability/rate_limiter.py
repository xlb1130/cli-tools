"""Rate limiting with budget management and token bucket algorithm."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from cts.reliability.models import RateLimitBudget


@dataclass
class RateLimitState:
    """State for a rate limit bucket."""
    tokens: float
    last_refill: float
    requests_in_window: int = 0
    window_start: float = 0.0
    total_requests: int = 0
    total_limited: int = 0
    last_limited_at: Optional[float] = None


class RateLimiter:
    """Rate limiter using token bucket / sliding window algorithm."""
    
    def __init__(
        self,
        budget: RateLimitBudget,
        name: str = "default",
        on_limited: Optional[Callable[[float], None]] = None,
    ):
        self.budget = budget
        self.name = name
        self.on_limited = on_limited
        self._lock = threading.Lock()
        self._state = self._init_state()
    
    def _init_state(self) -> RateLimitState:
        """Initialize rate limit state."""
        now = time.time()
        return RateLimitState(
            tokens=float(self.budget.get_rate_limit_value() or 1000),
            last_refill=now,
            window_start=now,
        )
    
    def _refill_tokens(self) -> None:
        """Refill tokens based on time elapsed."""
        if not self.budget.requests_per_second:
            return
        
        now = time.time()
        elapsed = now - self._state.last_refill
        refill_rate = self.budget.requests_per_second
        tokens_to_add = elapsed * refill_rate
        
        max_tokens = self.budget.requests_per_second * 2  # Allow some burst
        self._state.tokens = min(max_tokens, self._state.tokens + tokens_to_add)
        self._state.last_refill = now
    
    def _check_window(self) -> bool:
        """Check and update sliding window for minute/hour limits."""
        now = time.time()
        
        if self.budget.requests_per_minute:
            window_seconds = 60.0
            if now - self._state.window_start >= window_seconds:
                self._state.window_start = now
                self._state.requests_in_window = 0
            return self._state.requests_in_window < self.budget.requests_per_minute
        
        if self.budget.requests_per_hour:
            window_seconds = 3600.0
            if now - self._state.window_start >= window_seconds:
                self._state.window_start = now
                self._state.requests_in_window = 0
            return self._state.requests_in_window < self.budget.requests_per_hour
        
        return True
    
    def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens. Returns True if allowed, False if rate limited."""
        with self._lock:
            now = time.time()
            
            # Check inflight limit first
            if self.budget.max_inflight is not None:
                if self._state.requests_in_window >= self.budget.max_inflight:
                    self._record_limited(now)
                    return False
            
            # Refill tokens for per-second rate
            if self.budget.requests_per_second:
                self._refill_tokens()
                if self._state.tokens < tokens:
                    self._record_limited(now)
                    return False
                self._state.tokens -= tokens
            
            # Check sliding window for minute/hour
            if not self._check_window():
                self._record_limited(now)
                return False
            
            self._state.requests_in_window += 1
            self._state.total_requests += 1
            return True
    
    def _record_limited(self, now: float) -> None:
        """Record a rate limit event."""
        self._state.total_limited += 1
        self._state.last_limited_at = now
        
        if self.on_limited:
            wait_time = self._calculate_wait_time()
            self.on_limited(wait_time)
    
    def _calculate_wait_time(self) -> float:
        """Calculate how long to wait before next request is allowed."""
        if self.budget.requests_per_second:
            return 1.0 / self.budget.requests_per_second
        if self.budget.requests_per_minute:
            remaining = 60.0 - (time.time() - self._state.window_start)
            return max(0, remaining)
        if self.budget.requests_per_hour:
            remaining = 3600.0 - (time.time() - self._state.window_start)
            return max(0, remaining)
        return 1.0
    
    def wait_and_acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Wait if necessary and acquire tokens. Returns True if acquired."""
        start_time = time.time()
        
        while True:
            if self.acquire(tokens):
                return True
            
            wait_time = self._calculate_wait_time()
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed + wait_time > timeout:
                    return False
            
            time.sleep(wait_time)
    
    async def async_acquire(self, tokens: int = 1) -> bool:
        """Async version of acquire."""
        # Use async lock equivalent
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.acquire, tokens)
    
    async def async_wait_and_acquire(
        self,
        tokens: int = 1,
        timeout: Optional[float] = None,
    ) -> bool:
        """Async version of wait_and_acquire."""
        start_time = time.time()
        
        while True:
            if self.acquire(tokens):
                return True
            
            wait_time = self._calculate_wait_time()
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed + wait_time > timeout:
                    return False
            
            await asyncio.sleep(wait_time)
    
    def get_state(self) -> Dict[str, Any]:
        """Get current rate limiter state."""
        return {
            "name": self.name,
            "tokens": self._state.tokens,
            "requests_in_window": self._state.requests_in_window,
            "total_requests": self._state.total_requests,
            "total_limited": self._state.total_limited,
            "last_limited_at": self._state.last_limited_at,
            "budget": self.budget.model_dump(),
        }
    
    def reset(self) -> None:
        """Reset rate limiter state."""
        with self._lock:
            self._state = self._init_state()


class RateLimitManager:
    """Manager for multiple rate limiters with budget registry."""
    
    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
        self._budgets: Dict[str, RateLimitBudget] = {}
        self._lock = threading.Lock()
    
    def register_budget(self, key: str, budget: RateLimitBudget) -> None:
        """Register a rate limit budget."""
        with self._lock:
            self._budgets[key] = budget
    
    def get_limiter(
        self,
        budget_key: str,
        budget: Optional[RateLimitBudget] = None,
        on_limited: Optional[Callable[[float], None]] = None,
    ) -> RateLimiter:
        """Get or create a rate limiter for a budget key."""
        with self._lock:
            if budget_key not in self._limiters:
                if budget is None:
                    budget = self._budgets.get(budget_key, RateLimitBudget())
                self._limiters[budget_key] = RateLimiter(
                    budget=budget,
                    name=budget_key,
                    on_limited=on_limited,
                )
            return self._limiters[budget_key]
    
    def acquire(self, budget_key: str, tokens: int = 1) -> bool:
        """Acquire tokens from a specific budget."""
        limiter = self.get_limiter(budget_key)
        return limiter.acquire(tokens)
    
    def wait_and_acquire(
        self,
        budget_key: str,
        tokens: int = 1,
        timeout: Optional[float] = None,
    ) -> bool:
        """Wait and acquire tokens from a specific budget."""
        limiter = self.get_limiter(budget_key)
        return limiter.wait_and_acquire(tokens, timeout)
    
    async def async_acquire(self, budget_key: str, tokens: int = 1) -> bool:
        """Async acquire tokens from a specific budget."""
        limiter = self.get_limiter(budget_key)
        return await limiter.async_acquire(tokens)
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get state of all rate limiters."""
        return {key: limiter.get_state() for key, limiter in self._limiters.items()}
    
    def reset_all(self) -> None:
        """Reset all rate limiters."""
        for limiter in self._limiters.values():
            limiter.reset()
    
    def get_budget_status(self, budget_key: str) -> Dict[str, Any]:
        """Get status of a specific budget."""
        if budget_key not in self._limiters:
            return {"exists": False, "budget_key": budget_key}
        
        limiter = self._limiters[budget_key]
        return {
            "exists": True,
            "budget_key": budget_key,
            **limiter.get_state(),
        }
