from __future__ import annotations

import re
from pathlib import Path
from typing import Final

__all__ = ["__version__"]

_UNSET: Final = object()
_version_cache: object = _UNSET


def _read_pyproject_version() -> str:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.exists():
        return "0.0.0"

    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', pyproject.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        return "0.0.0"
    return match.group(1)


def _resolve_version() -> str:
    local_version = _read_pyproject_version()
    if local_version != "0.0.0":
        return local_version

    try:
        from importlib.metadata import PackageNotFoundError, version
    except ModuleNotFoundError:
        return "0.0.0"

    try:
        return version("cts")
    except PackageNotFoundError:
        return "0.0.0"

def __getattr__(name: str):
    global _version_cache

    if name != "__version__":
        raise AttributeError(name)
    if _version_cache is _UNSET:
        _version_cache = _resolve_version()
    return _version_cache
