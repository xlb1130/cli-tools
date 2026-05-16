"""Generate stable task identifiers."""

from __future__ import annotations

from uuid import uuid4


def generate_task_id(prefix: str = "task") -> str:
    return f"{prefix}_{uuid4()}"
