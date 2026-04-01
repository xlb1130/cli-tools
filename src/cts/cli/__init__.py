from __future__ import annotations

__all__ = ["main"]


def __getattr__(name: str):
    if name != "main":
        raise AttributeError(name)

    from cts.cli.root import main

    return main
