from __future__ import annotations

from typing import Dict

from cts.providers.cli import CLIProvider, ShellProvider
from cts.providers.graphql import GraphQLProvider
from cts.providers.http import HTTPProvider
from cts.providers.mcp_cli import MCPCLIProvider
from cts.providers.openapi import OpenAPIProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, object] = {
            "cli": CLIProvider(),
            "shell": ShellProvider(),
            "http": HTTPProvider(),
            "openapi": OpenAPIProvider(),
            "graphql": GraphQLProvider(),
            "mcp": MCPCLIProvider(),
        }

    def register(self, provider_type: str, provider: object) -> None:
        normalized = provider_type.strip().lower()
        if not normalized:
            raise KeyError("provider_type must not be empty")
        if normalized in self._providers:
            raise KeyError(f"provider already registered: {normalized}")
        self._providers[normalized] = provider

    def get(self, provider_type: str):
        normalized = provider_type.strip().lower()
        if normalized not in self._providers:
            raise KeyError(f"unsupported provider type: {provider_type}")
        return self._providers[normalized]

    def supported_types(self) -> set[str]:
        return set(self._providers.keys())
