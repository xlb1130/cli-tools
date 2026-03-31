import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

__all__ = ["__version__"]


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
        return version("cts")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _resolve_version()
