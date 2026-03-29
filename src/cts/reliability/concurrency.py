"""Concurrency control with semaphores and queue management."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from cts.reliability.models import ConcurrencyConfig


@dataclass
class ConcurrencyState:
    """State for concurrency tracking."""
    active: int = 0
    waiting: int = 0
    total_acquired: int = 0
    total_released: int = 0
    total_timed_out: int = 0
    peak_active: int = 0


class ConcurrencySemaphore:
    """Semaphore with state tracking and timeout support."""
    
    def __init__(
        self,
        max_concurrent: int,
        name: str = "default",
        queue_timeout_seconds: float = 30.0,
    ):
        self.max_concurrent = max_concurrent
        self.name = name
        self.queue_timeout_seconds = queue_timeout_seconds
        self._semaphore = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()
        self._state = ConcurrencyState()
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """Acquire semaphore, optionally with timeout."""
        timeout = timeout or self.queue_timeout_seconds
        
        with self._lock:
            self._state.waiting += 1
        
        acquired = self._semaphore.acquire(timeout=timeout)
        
        with self._lock:
            self._state.waiting -= 1
            
            if acquired:
                self._state.active += 1
                self._state.total_acquired += 1
                self._state.peak_active = max(self._state.peak_active, self._state.active)
            else:
                self._state.total_timed_out += 1
        
        return acquired
    
    def release(self) -> None:
        """Release semaphore."""
        with self._lock:
            if self._state.active > 0:
                self._state.active -= 1
                self._state.total_released += 1
        
        self._semaphore.release()
    
    @contextmanager
    def acquire_context(self, timeout: Optional[float] = None):
        """Context manager for acquire/release."""
        acquired = self.acquire(timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()
    
    def get_state(self) -> Dict[str, Any]:
        """Get current semaphore state."""
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "active": self._state.active,
            "waiting": self._state.waiting,
            "available": self.max_concurrent - self._state.active,
            "total_acquired": self._state.total_acquired,
            "total_released": self._state.total_released,
            "total_timed_out": self._state.total_timed_out,
            "peak_active": self._state.peak_active,
        }
    
    async def async_acquire(self, timeout: Optional[float] = None) -> bool:
        """Async acquire semaphore."""
        timeout = timeout or self.queue_timeout_seconds
        
        try:
            async with asyncio.timeout(timeout):
                async with self._get_async_semaphore():
                    with self._lock:
                        self._state.active += 1
                        self._state.total_acquired += 1
                        self._state.peak_active = max(
                            self._state.peak_active, self._state.active
                        )
                    return True
        except asyncio.TimeoutError:
            with self._lock:
                self._state.total_timed_out += 1
            return False
    
    async def async_release(self) -> None:
        """Async release semaphore."""
        with self._lock:
            if self._state.active > 0:
                self._state.active -= 1
                self._state.total_released += 1
    
    def _get_async_semaphore(self) -> asyncio.Semaphore:
        """Get or create async semaphore."""
        if not hasattr(self, "_async_semaphore"):
            self._async_semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._async_semaphore


class ConcurrencyManager:
    """Manager for concurrency control across sources and global limits."""
    
    def __init__(self, config: Optional[ConcurrencyConfig] = None):
        self.config = config or ConcurrencyConfig()
        self._semaphores: Dict[str, ConcurrencySemaphore] = {}
        self._global_semaphore: Optional[ConcurrencySemaphore] = None
        self._lock = threading.Lock()
    
    def _get_global_semaphore(self) -> ConcurrencySemaphore:
        """Get or create global semaphore."""
        if self._global_semaphore is None:
            self._global_semaphore = ConcurrencySemaphore(
                max_concurrent=self.config.max_inflight_global,
                name="global",
                queue_timeout_seconds=self.config.queue_timeout_seconds,
            )
        return self._global_semaphore
    
    def get_source_semaphore(self, source_name: str) -> ConcurrencySemaphore:
        """Get or create semaphore for a source."""
        with self._lock:
            if source_name not in self._semaphores:
                self._semaphores[source_name] = ConcurrencySemaphore(
                    max_concurrent=self.config.max_inflight_per_source,
                    name=source_name,
                    queue_timeout_seconds=self.config.queue_timeout_seconds,
                )
            return self._semaphores[source_name]
    
    @contextmanager
    def acquire_for_source(
        self,
        source_name: str,
        timeout: Optional[float] = None,
        use_global: bool = True,
    ):
        """Context manager to acquire both source and global semaphores."""
        source_sem = self.get_source_semaphore(source_name)
        global_sem = self._get_global_semaphore() if use_global else None
        
        # Acquire source semaphore first
        source_acquired = source_sem.acquire(timeout)
        if not source_acquired:
            yield False
            return
        
        # Then acquire global semaphore
        global_acquired = True
        if global_sem:
            global_acquired = global_sem.acquire(timeout)
            if not global_acquired:
                source_sem.release()
                yield False
                return
        
        try:
            yield True
        finally:
            if global_acquired and global_sem:
                global_sem.release()
            source_sem.release()
    
    async def async_acquire_for_source(
        self,
        source_name: str,
        timeout: Optional[float] = None,
        use_global: bool = True,
    ) -> bool:
        """Async acquire both source and global semaphores."""
        source_sem = self.get_source_semaphore(source_name)
        global_sem = self._get_global_semaphore() if use_global else None
        
        # Acquire source semaphore first
        source_acquired = await source_sem.async_acquire(timeout)
        if not source_acquired:
            return False
        
        # Then acquire global semaphore
        global_acquired = True
        if global_sem:
            global_acquired = await global_sem.async_acquire(timeout)
            if not global_acquired:
                await source_sem.async_release()
                return False
        
        # Note: Caller is responsible for calling async_release_for_source
        return True
    
    async def async_release_for_source(
        self,
        source_name: str,
        use_global: bool = True,
    ) -> None:
        """Async release both source and global semaphores."""
        source_sem = self.get_source_semaphore(source_name)
        global_sem = self._get_global_semaphore() if use_global else None
        
        await source_sem.async_release()
        if global_sem:
            await global_sem.async_release()
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get state of all semaphores."""
        states = {}
        
        for name, sem in self._semaphores.items():
            states[f"source:{name}"] = sem.get_state()
        
        if self._global_semaphore:
            states["global"] = self._global_semaphore.get_state()
        
        return states
    
    def get_source_status(self, source_name: str) -> Dict[str, Any]:
        """Get status of a specific source."""
        if source_name not in self._semaphores:
            return {
                "exists": False,
                "source": source_name,
                "max_concurrent": self.config.max_inflight_per_source,
            }
        
        return {
            "exists": True,
            "source": source_name,
            **self._semaphores[source_name].get_state(),
        }
    
    def get_global_status(self) -> Dict[str, Any]:
        """Get global concurrency status."""
        if self._global_semaphore is None:
            return {
                "exists": False,
                "max_concurrent": self.config.max_inflight_global,
            }
        
        return {
            "exists": True,
            **self._global_semaphore.get_state(),
        }
    
    def reset_all(self) -> None:
        """Reset all semaphores."""
        self._semaphores.clear()
        self._global_semaphore = None
