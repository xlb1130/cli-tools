"""Upload generic execution reports."""

from __future__ import annotations


def upload_report(payload: dict) -> dict:
    return {"ok": True, "kind": "generic-report", "payload": payload}
