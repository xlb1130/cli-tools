"""Post-task hook placeholder."""

from __future__ import annotations


def run(context: dict) -> dict:
    return {"event": "post_task", "context": context}
