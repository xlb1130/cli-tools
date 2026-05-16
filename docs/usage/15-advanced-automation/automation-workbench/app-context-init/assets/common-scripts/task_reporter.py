"""Report task execution results."""

from __future__ import annotations


def report_task(task_id: str, result: dict) -> dict:
    return {"task_id": task_id, "result": result}
