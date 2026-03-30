"""External plugin protocol for CTS.

This module enables external plugins to communicate with CTS via
a well-defined protocol, allowing third-party extensions.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ExternalPluginProtocol(Protocol):
    """Protocol that external plugins must implement."""
    
    def get_metadata(self) -> Dict[str, Any]:
        """Return plugin metadata."""
        ...
    
    def register_providers(self) -> List[Dict[str, Any]]:
        """Return list of provider registrations."""
        ...
    
    def get_hooks(self) -> List[Dict[str, Any]]:
        """Return list of hook registrations."""
        ...
    
    def invoke(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke a plugin action."""
        ...


@dataclass
class PluginMetadata:
    """Metadata for an external plugin."""
    name: str
    version: str
    description: Optional[str] = None
    author: Optional[str] = None
    homepage: Optional[str] = None
    min_cts_version: Optional[str] = None
    max_cts_version: Optional[str] = None
    provides: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PluginMetadata:
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "0.0.0"),
            description=data.get("description"),
            author=data.get("author"),
            homepage=data.get("homepage"),
            min_cts_version=data.get("min_cts_version"),
            max_cts_version=data.get("max_cts_version"),
            provides=data.get("provides", []),
            capabilities=data.get("capabilities", []),
        )


@dataclass
class ProviderRegistration:
    """Registration info for a plugin-provided provider."""
    type: str
    description: Optional[str] = None
    config_schema: Dict[str, Any] = field(default_factory=dict)
    supports_discovery: bool = False
    supports_explain: bool = True
    supports_invoke: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProviderRegistration:
        return cls(
            type=data.get("type", ""),
            description=data.get("description"),
            config_schema=data.get("config_schema", {}),
            supports_discovery=data.get("supports_discovery", False),
            supports_explain=data.get("supports_explain", True),
            supports_invoke=data.get("supports_invoke", True),
        )


@dataclass
class HookRegistration:
    """Registration info for a plugin-provided hook."""
    event: str
    handler: str  # Action name to invoke
    priority: int = 100
    when: Optional[Any] = None
    fail_mode: str = "warn"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HookRegistration:
        return cls(
            event=data.get("event", ""),
            handler=data.get("handler", ""),
            priority=data.get("priority", 100),
            when=data.get("when"),
            fail_mode=data.get("fail_mode", "warn"),
        )


class ExternalPlugin:
    """Base class for external plugins."""
    
    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata
        self._providers: Dict[str, ProviderRegistration] = {}
        self._hooks: List[HookRegistration] = []
        self._handlers: Dict[str, Callable] = {}
    
    def register_provider(self, registration: ProviderRegistration) -> None:
        """Register a provider type."""
        self._providers[registration.type] = registration
    
    def register_hook(self, registration: HookRegistration) -> None:
        """Register a hook."""
        self._hooks.append(registration)
    
    def register_handler(self, action: str, handler: Callable) -> None:
        """Register an action handler."""
        self._handlers[action] = handler
    
    def get_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.metadata.name,
            "version": self.metadata.version,
            "description": self.metadata.description,
            "author": self.metadata.author,
            "homepage": self.metadata.homepage,
            "min_cts_version": self.metadata.min_cts_version,
            "max_cts_version": self.metadata.max_cts_version,
            "provides": self.metadata.provides,
            "capabilities": self.metadata.capabilities,
        }
    
    def register_providers(self) -> List[Dict[str, Any]]:
        return [r.__dict__ for r in self._providers.values()]
    
    def get_hooks(self) -> List[Dict[str, Any]]:
        return [h.__dict__ for h in self._hooks]
    
    def invoke(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._handlers.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
        try:
            result = handler(payload)
            return {"ok": True, "result": result}
        except Exception as e:
            return {"error": str(e)}


class SubprocessPlugin(ExternalPlugin):
    """External plugin that runs as a subprocess."""
    
    def __init__(self, executable: Path, metadata: Optional[PluginMetadata] = None):
        self.executable = executable
        self._metadata = metadata
        self._loaded = False
        super().__init__(metadata or PluginMetadata(name="unknown", version="0.0.0"))
    
    def load(self) -> None:
        """Load plugin metadata from the executable."""
        if self._loaded:
            return
        
        result = self._call("get_metadata", {})
        if "error" in result:
            raise RuntimeError(f"Failed to load plugin: {result['error']}")
        
        self.metadata = PluginMetadata.from_dict(result.get("result", {}))
        self._loaded = True
        
        # Load providers
        providers_result = self._call("register_providers", {})
        if "result" in providers_result:
            for p in providers_result["result"]:
                self.register_provider(ProviderRegistration.from_dict(p))
        
        # Load hooks
        hooks_result = self._call("get_hooks", {})
        if "result" in hooks_result:
            for h in hooks_result["result"]:
                self.register_hook(HookRegistration.from_dict(h))
    
    def invoke(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._call(action, payload)
    
    def _call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call the plugin executable."""
        try:
            request = {
                "action": action,
                "payload": payload,
            }
            
            result = subprocess.run(
                [str(self.executable), "--plugin-mode"],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                return {"error": f"Plugin exited with code {result.returncode}: {result.stderr}"}
            
            return json.loads(result.stdout)
        
        except subprocess.TimeoutExpired:
            return {"error": "Plugin timeout"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response: {e}"}
        except Exception as e:
            return {"error": str(e)}


class PluginRegistry:
    """Registry for external plugins."""
    
    def __init__(self):
        self._plugins: Dict[str, ExternalPlugin] = {}
    
    def register(self, plugin: ExternalPlugin) -> None:
        """Register a plugin."""
        self._plugins[plugin.metadata.name] = plugin
    
    def get(self, name: str) -> Optional[ExternalPlugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)
    
    def list_all(self) -> List[ExternalPlugin]:
        """List all registered plugins."""
        return list(self._plugins.values())
    
    def get_all_providers(self) -> Dict[str, ProviderRegistration]:
        """Get all provider registrations from all plugins."""
        providers = {}
        for plugin in self._plugins.values():
            for reg in plugin._providers.values():
                providers[reg.type] = reg
        return providers
    
    def get_all_hooks(self) -> List[tuple[str, HookRegistration]]:
        """Get all hook registrations with plugin names."""
        hooks = []
        for name, plugin in self._plugins.items():
            for hook in plugin._hooks:
                hooks.append((name, hook))
        return hooks


# Protocol message format for external plugins
PROTOCOL_VERSION = "1.0"

def create_request(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a protocol request."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "action": action,
        "payload": payload,
    }


def parse_response(data: str) -> Dict[str, Any]:
    """Parse a protocol response."""
    return json.loads(data)


def create_response(result: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
    """Create a protocol response."""
    response = {"protocol_version": PROTOCOL_VERSION}
    if error:
        response["error"] = error
    else:
        response["result"] = result
    return response
