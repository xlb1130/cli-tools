"""Persist self-evolution findings."""

from __future__ import annotations


def report_learning(topic: str, summary: str) -> dict:
    return {"topic": topic, "summary": summary}
