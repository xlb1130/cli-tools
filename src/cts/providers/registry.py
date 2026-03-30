from __future__ import annotations

from typing import Callable, Dict


class ProviderRegistry:
    def __init__(self) -> None:
        self._provider_factories: Dict[str, Callable[[], object]] = {
            "cli": _build_cli_provider,
            "shell": _build_shell_provider,
            "http": _build_http_provider,
            "openapi": _build_openapi_provider,
            "graphql": _build_graphql_provider,
            "mcp": _build_mcp_provider,
        }
        self._providers: Dict[str, object] = {}

    def register(self, provider_type: str, provider: object) -> None:
        normalized = provider_type.strip().lower()
        if not normalized:
            raise KeyError("provider_type must not be empty")
        if normalized in self._providers or normalized in self._provider_factories:
            raise KeyError(f"provider already registered: {normalized}")
        self._providers[normalized] = provider

    def get(self, provider_type: str):
        normalized = provider_type.strip().lower()
        if normalized in self._providers:
            return self._providers[normalized]
        factory = self._provider_factories.get(normalized)
        if factory is None:
            raise KeyError(f"unsupported provider type: {provider_type}")
        provider = factory()
        self._providers[normalized] = provider
        return provider

    def supported_types(self) -> set[str]:
        return set(self._provider_factories.keys()) | set(self._providers.keys())


def _build_cli_provider():
    from cts.providers.cli import CLIProvider

    return CLIProvider()


def _build_shell_provider():
    from cts.providers.cli import ShellProvider

    return ShellProvider()


def _build_http_provider():
    from cts.providers.http import HTTPProvider

    return HTTPProvider()


def _build_openapi_provider():
    from cts.providers.openapi import OpenAPIProvider

    return OpenAPIProvider()


def _build_graphql_provider():
    from cts.providers.graphql import GraphQLProvider

    return GraphQLProvider()


def _build_mcp_provider():
    from cts.providers.mcp_cli import MCPCLIProvider

    return MCPCLIProvider()
