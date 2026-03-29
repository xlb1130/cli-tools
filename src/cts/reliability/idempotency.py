"""Idempotency key generation and duplicate execution prevention."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cts.reliability.models import IdempotencyConfig, IdempotencyStrategy


@dataclass
class IdempotencyKey:
    """Represents an idempotency key with metadata."""
    key: str
    strategy: IdempotencyStrategy
    mount_id: str
    operation_id: str
    created_at: float
    expires_at: float
    args_hash: Optional[str] = None
    source: Optional[str] = None
    
    def is_expired(self) -> bool:
        """Check if key has expired."""
        return time.time() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "strategy": self.strategy.value,
            "mount_id": self.mount_id,
            "operation_id": self.operation_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "args_hash": self.args_hash,
            "source": self.source,
        }


@dataclass
class ExecutionRecord:
    """Record of an execution for duplicate detection."""
    key: str
    mount_id: str
    operation_id: str
    args_hash: str
    run_id: str
    started_at: float
    completed_at: Optional[float] = None
    status: str = "pending"  # pending, completed, failed
    result_summary: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "mount_id": self.mount_id,
            "operation_id": self.operation_id,
            "args_hash": self.args_hash,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "result_summary": self.result_summary,
        }


class IdempotencyManager:
    """Manager for idempotency key generation and duplicate detection."""
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        default_ttl_seconds: int = 86400,
    ):
        self.cache_dir = cache_dir or Path.home() / ".cts" / "idempotency"
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: Dict[str, ExecutionRecord] = {}
        self._lock = threading.Lock()
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing records
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load cached execution records."""
        cache_file = self.cache_dir / "executions.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    for key, record in data.items():
                        self._cache[key] = ExecutionRecord(**record)
            except (json.JSONDecodeError, KeyError):
                pass
    
    def _save_cache(self) -> None:
        """Save cache to disk."""
        cache_file = self.cache_dir / "executions.json"
        with open(cache_file, "w") as f:
            json.dump(
                {k: v.to_dict() for k, v in self._cache.items()},
                f,
                indent=2,
            )
    
    def generate_key(
        self,
        mount_id: str,
        operation_id: str,
        args: Dict[str, Any],
        config: IdempotencyConfig,
        caller_key: Optional[str] = None,
    ) -> IdempotencyKey:
        """Generate an idempotency key based on strategy."""
        now = time.time()
        expires_at = now + config.ttl_seconds
        
        if config.strategy == IdempotencyStrategy.UUID:
            key = str(uuid.uuid4())
            args_hash = None
        
        elif config.strategy == IdempotencyStrategy.CALLER_SUPPLIED:
            if not caller_key:
                raise ValueError("caller_key required for caller_supplied strategy")
            key = caller_key
            args_hash = self._hash_args(args)
        
        elif config.strategy == IdempotencyStrategy.HASH_ARGS:
            args_hash = self._hash_args(args)
            key = self._derive_key(mount_id, operation_id, args_hash)
        
        elif config.strategy == IdempotencyStrategy.HASH_SELECTED_FIELDS:
            selected_args = {k: v for k, v in args.items() if k in config.key_fields}
            args_hash = self._hash_args(selected_args)
            key = self._derive_key(mount_id, operation_id, args_hash)
        
        elif config.strategy == IdempotencyStrategy.PROVIDER_NATIVE:
            # Provider will handle key generation
            key = str(uuid.uuid4())
            args_hash = self._hash_args(args)
        
        else:
            args_hash = self._hash_args(args)
            key = self._derive_key(mount_id, operation_id, args_hash)
        
        return IdempotencyKey(
            key=key,
            strategy=config.strategy,
            mount_id=mount_id,
            operation_id=operation_id,
            created_at=now,
            expires_at=expires_at,
            args_hash=args_hash,
        )
    
    def _hash_args(self, args: Dict[str, Any]) -> str:
        """Generate hash of arguments."""
        # Sort keys for consistent hashing
        serialized = json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]
    
    def _derive_key(self, mount_id: str, operation_id: str, args_hash: str) -> str:
        """Derive key from mount, operation, and args hash."""
        combined = f"{mount_id}:{operation_id}:{args_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]
    
    def check_duplicate(
        self,
        key: str,
        within_seconds: Optional[int] = None,
    ) -> Optional[ExecutionRecord]:
        """Check if execution with same key exists within TTL."""
        with self._lock:
            if key not in self._cache:
                return None
            
            record = self._cache[key]
            
            # Check expiration
            ttl = within_seconds or self.default_ttl_seconds
            if time.time() - record.started_at > ttl:
                # Expired, remove from cache
                del self._cache[key]
                self._save_cache()
                return None
            
            return record
    
    def record_execution_start(
        self,
        key: str,
        mount_id: str,
        operation_id: str,
        args: Dict[str, Any],
        run_id: str,
    ) -> ExecutionRecord:
        """Record the start of an execution."""
        args_hash = self._hash_args(args)
        record = ExecutionRecord(
            key=key,
            mount_id=mount_id,
            operation_id=operation_id,
            args_hash=args_hash,
            run_id=run_id,
            started_at=time.time(),
            status="pending",
        )
        
        with self._lock:
            self._cache[key] = record
            self._save_cache()
        
        return record
    
    def record_execution_complete(
        self,
        key: str,
        status: str = "completed",
        result_summary: Optional[str] = None,
    ) -> None:
        """Record the completion of an execution."""
        with self._lock:
            if key in self._cache:
                self._cache[key].completed_at = time.time()
                self._cache[key].status = status
                self._cache[key].result_summary = result_summary
                self._save_cache()
    
    def is_duplicate_execution(
        self,
        mount_id: str,
        operation_id: str,
        args: Dict[str, Any],
        config: IdempotencyConfig,
    ) -> Tuple[bool, Optional[ExecutionRecord]]:
        """Check if this would be a duplicate execution."""
        idem_key = self.generate_key(mount_id, operation_id, args, config)
        existing = self.check_duplicate(idem_key.key, config.ttl_seconds)
        
        if existing and existing.status == "completed":
            return True, existing
        
        return False, existing
    
    def cleanup_expired(self) -> int:
        """Remove expired records from cache."""
        now = time.time()
        expired_keys = []
        
        with self._lock:
            for key, record in self._cache.items():
                if now - record.started_at > self.default_ttl_seconds:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                self._save_cache()
        
        return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get idempotency manager statistics."""
        with self._lock:
            total = len(self._cache)
            pending = sum(1 for r in self._cache.values() if r.status == "pending")
            completed = sum(1 for r in self._cache.values() if r.status == "completed")
            failed = sum(1 for r in self._cache.values() if r.status == "failed")
            
            return {
                "total_records": total,
                "pending": pending,
                "completed": completed,
                "failed": failed,
                "cache_dir": str(self.cache_dir),
            }
    
    def clear_cache(self) -> None:
        """Clear all cached records."""
        with self._lock:
            self._cache.clear()
            self._save_cache()


def generate_idempotency_header(
    key: IdempotencyKey,
    header_name: str = "Idempotency-Key",
) -> Dict[str, str]:
    """Generate HTTP headers for idempotency key."""
    headers = {
        header_name: key.key,
        "X-Idempotency-Strategy": key.strategy.value,
        "X-Idempotency-Expires": str(int(key.expires_at)),
    }
    return headers


def generate_idempotency_key_for_provider(
    provider_type: str,
    mount_id: str,
    operation_id: str,
    args: Dict[str, Any],
    config: IdempotencyConfig,
) -> Tuple[str, Dict[str, str]]:
    """Generate idempotency key and provider-specific data.
    
    Returns:
        Tuple of (key, provider_specific_metadata)
    """
    manager = IdempotencyManager()
    key = manager.generate_key(mount_id, operation_id, args, config)
    
    metadata = {
        "key": key.key,
        "strategy": key.strategy.value,
        "header_name": config.header_name,
    }
    
    # Provider-specific handling
    if provider_type in ("http", "openapi"):
        metadata["headers"] = generate_idempotency_header(key, config.header_name)
    
    elif provider_type == "graphql":
        # For GraphQL, include in extensions
        metadata["extensions"] = {
            "idempotency": {
                "key": key.key,
            }
        }
    
    elif provider_type in ("cli", "shell", "mcp_cli"):
        # For CLI, pass as environment variable
        metadata["env"] = {
            "CTS_IDEMPOTENCY_KEY": key.key,
        }
    
    return key.key, metadata
