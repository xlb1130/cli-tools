"""Documentation generator for CTS.

Generates documentation from CTS configuration and runtime state.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from cts.app import CTSApp


@dataclass
class DocsConfig:
    """Configuration for documentation generation."""
    output_dir: Path = Path("docs/generated")
    format: str = "markdown"  # markdown, html, json
    include_sources: bool = True
    include_mounts: bool = True
    include_workflows: bool = True
    include_catalog: bool = True
    include_cli_help: bool = True
    title: str = "CTS Documentation"
    description: Optional[str] = None


class DocsGenerator:
    """Generate documentation from CTS app."""
    
    def __init__(self, app: CTSApp, config: Optional[DocsConfig] = None):
        self.app = app
        self.config = config or DocsConfig()
    
    def generate(self) -> Dict[str, Path]:
        """Generate all documentation and return file paths."""
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        
        generated = {}
        
        if self.config.include_sources:
            generated["sources"] = self._generate_sources_doc()
        
        if self.config.include_mounts:
            generated["mounts"] = self._generate_mounts_doc()
        
        if self.config.include_catalog:
            generated["catalog"] = self._generate_catalog_doc()
        
        if self.config.include_cli_help:
            generated["cli"] = self._generate_cli_doc()
        
        generated["index"] = self._generate_index()
        
        return generated
    
    def _generate_index(self) -> Path:
        """Generate main index page."""
        return self._write_document("index", self._render_index(), self._render_index_payload())
    
    def _generate_sources_doc(self) -> Path:
        """Generate sources documentation."""
        return self._write_document("sources", self._render_sources(), self._render_sources_payload())
    
    def _generate_mounts_doc(self) -> Path:
        """Generate mounts documentation."""
        return self._write_document("mounts", self._render_mounts(), self._render_mounts_payload())
    
    def _generate_catalog_doc(self) -> Path:
        """Generate catalog documentation."""
        return self._write_document("catalog", self._render_catalog(), self._render_catalog_payload())
    
    def _generate_cli_doc(self) -> Path:
        """Generate CLI reference documentation."""
        return self._write_document("cli-reference", self._render_cli_reference(), self._render_cli_reference_payload())

    def _write_document(self, stem: str, markdown_content: str, payload: Dict[str, Any]) -> Path:
        extension = self._file_extension()
        path = self.config.output_dir / f"{stem}.{extension}"
        if self.config.format == "json":
            content = json.dumps(payload, ensure_ascii=False, indent=2)
        elif self.config.format == "html":
            content = self._render_html_document(payload.get("title") or stem, markdown_content)
        else:
            content = markdown_content
        path.write_text(content, encoding="utf-8")
        return path

    def _file_extension(self) -> str:
        if self.config.format == "html":
            return "html"
        if self.config.format == "json":
            return "json"
        return "md"

    def _render_html_document(self, title: str, markdown_content: str) -> str:
        body = html.escape(markdown_content)
        return (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "<head>\n"
            f"  <meta charset=\"utf-8\" />\n  <title>{html.escape(title)}</title>\n"
            "  <style>body{font-family:IBM Plex Sans,Segoe UI,sans-serif;margin:2rem;line-height:1.6;color:#102523}"
            "pre{white-space:pre-wrap;background:#f6f1e5;padding:1rem;border-radius:12px;}</style>\n"
            "</head>\n"
            "<body>\n"
            f"<pre>{body}</pre>\n"
            "</body>\n"
            "</html>\n"
        )

    def _render_index_payload(self) -> Dict[str, Any]:
        return {
            "title": self.config.title,
            "description": self.config.description,
            "sections": {
                "sources": len(self.app.config.sources),
                "mounts": len(self.app.catalog.mounts),
                "conflicts": len(self.app.catalog.conflicts),
            },
        }

    def _render_sources_payload(self) -> Dict[str, Any]:
        return {
            "title": "Sources",
            "items": [
                {
                    "name": name,
                    "type": source.type,
                    "description": source.description,
                    "enabled": source.enabled,
                    "base_url": getattr(source, "base_url", None),
                    "executable": getattr(source, "executable", None),
                }
                for name, source in self.app.config.sources.items()
            ],
        }

    def _render_mounts_payload(self) -> Dict[str, Any]:
        return {
            "title": "Mounts",
            "items": [
                {
                    "mount_id": mount.mount_id,
                    "command_path": list(mount.command_path),
                    "stable_name": mount.stable_name,
                    "risk": mount.operation.risk,
                    "provider_type": mount.provider_type,
                    "summary": mount.summary or mount.operation.title,
                    "input_schema": mount.operation.input_schema,
                }
                for mount in self.app.catalog.mounts
            ],
        }

    def _render_catalog_payload(self) -> Dict[str, Any]:
        return {
            "title": "Capability Catalog",
            "catalog": self.app.export_catalog(),
        }

    def _render_cli_reference_payload(self) -> Dict[str, Any]:
        return {
            "title": "CLI Reference",
            "commands": [
                "manage config",
                "manage source",
                "manage mount",
                "manage invoke",
                "manage explain",
                "manage catalog",
                "manage sync",
                "manage doctor",
                "manage serve",
                "manage auth",
                "manage completion",
            ],
        }
    
    def _render_index(self) -> str:
        """Render index page."""
        lines = [
            f"# {self.config.title}",
            "",
        ]
        
        if self.config.description:
            lines.extend([self.config.description, ""])
        
        lines.extend([
            "## Contents",
            "",
            "- [Sources](sources.md) - Configured capability sources",
            "- [Mounts](mounts.md) - Mounted operations and commands",
            "- [Catalog](catalog.md) - Full capability catalog",
            "- [CLI Reference](cli-reference.md) - Command line interface reference",
            "",
            "## Summary",
            "",
            f"- **Sources**: {len(self.app.config.sources)}",
            f"- **Mounts**: {len(self.app.catalog.mounts)}",
            f"- **Conflicts**: {len(self.app.catalog.conflicts)}",
            "",
        ])
        
        return "\n".join(lines)
    
    def _render_sources(self) -> str:
        """Render sources documentation."""
        lines = [
            "# Sources",
            "",
            "This page documents all configured capability sources.",
            "",
        ]
        
        for name, source in self.app.config.sources.items():
            lines.extend(self._render_source_section(name, source))
        
        return "\n".join(lines)
    
    def _render_source_section(self, name: str, source: Any) -> List[str]:
        """Render a single source section."""
        lines = [
            f"## {name}",
            "",
            f"- **Type**: `{source.type}`",
        ]
        
        if source.description:
            lines.append(f"- **Description**: {source.description}")
        
        if source.enabled:
            lines.append(f"- **Status**: Enabled")
        else:
            lines.append(f"- **Status**: Disabled")
        
        lines.append("")
        
        # Add discovery info
        if hasattr(source, "discovery"):
            discovery = source.discovery
            lines.extend([
                "### Discovery",
                "",
                f"- **Mode**: {discovery.mode}",
            ])
            if discovery.manifest:
                lines.append(f"- **Manifest**: `{discovery.manifest}`")
            lines.append("")
        
        # Add provider-specific details
        if source.type == "http" and source.base_url:
            lines.extend([
                "### HTTP Configuration",
                "",
                f"- **Base URL**: `{source.base_url}`",
                "",
            ])
        
        elif source.type == "cli" and source.executable:
            lines.extend([
                "### CLI Configuration",
                "",
                f"- **Executable**: `{source.executable}`",
                "",
            ])
        
        return lines
    
    def _render_mounts(self) -> str:
        """Render mounts documentation."""
        lines = [
            "# Mounts",
            "",
            "This page documents all mounted operations.",
            "",
        ]
        
        # Group by source
        by_source: Dict[str, List] = {}
        for mount in self.app.catalog.mounts:
            by_source.setdefault(mount.source_name, []).append(mount)
        
        for source_name, mounts in sorted(by_source.items()):
            lines.append(f"## Source: {source_name}")
            lines.append("")
            
            for mount in sorted(mounts, key=lambda m: m.mount_id):
                lines.extend(self._render_mount_entry(mount))
        
        return "\n".join(lines)
    
    def _render_mount_entry(self, mount: Any) -> List[str]:
        """Render a single mount entry."""
        lines = [
            f"### {mount.mount_id}",
            "",
            f"- **Command**: `cts {' '.join(mount.command_path)}`",
            f"- **Stable Name**: `{mount.stable_name or 'N/A'}`",
            f"- **Risk Level**: `{mount.operation.risk}`",
            f"- **Provider**: `{mount.provider_type}`",
        ]
        
        if mount.operation.summary:
            lines.append(f"- **Summary**: {mount.operation.summary}")
        
        lines.append("")
        
        # Input schema
        if mount.operation.input_schema:
            lines.extend([
                "#### Input Schema",
                "",
                "```json",
                self._format_json(mount.operation.input_schema),
                "```",
                "",
            ])
        
        # Machine contract
        lines.extend([
            "#### Machine Contract",
            "",
            "```bash",
            f"cts manage invoke {mount.mount_id} --input-json '{{...}}'",
            "```",
            "",
        ])
        
        return lines
    
    def _render_catalog(self) -> str:
        """Render catalog documentation."""
        catalog = self.app.export_catalog()
        
        lines = [
            "# Capability Catalog",
            "",
            "This is the complete capability catalog in machine-readable format.",
            "",
            "```json",
            self._format_json(catalog),
            "```",
            "",
        ]
        
        return "\n".join(lines)
    
    def _render_cli_reference(self) -> str:
        """Render CLI reference documentation."""
        lines = [
            "# CLI Reference",
            "",
            "## Global Options",
            "",
            "```",
            "cts [OPTIONS] COMMAND [ARGS]...",
            "",
            "Options:",
            "  --config PATH          Path to configuration file",
            "  --profile TEXT         Profile name to use",
            "  --output [text|json]   Output format",
            "  --help                 Show help message",
            "  --version              Show version",
            "```",
            "",
            "## Commands",
            "",
        ]
        
        commands = [
            ("manage config", "Configuration management"),
            ("manage source", "Source registry operations"),
            ("manage mount", "Mount registry operations"),
            ("manage invoke", "Invoke a mount by ID"),
            ("manage explain", "Explain a mount execution plan"),
            ("manage catalog", "Export capability catalog"),
            ("manage sync", "Synchronize discovery cache"),
            ("manage doctor", "Run diagnostics"),
            ("manage serve", "Start northbound surfaces"),
            ("manage auth", "Authentication management"),
            ("manage completion", "Shell completion helpers"),
        ]
        
        for cmd, desc in commands:
            lines.append(f"- `cts {cmd}` - {desc}")
        
        lines.extend([
            "",
            "### serve",
            "",
            "Start northbound surface servers.",
            "",
            "```",
            "cts manage serve http [--host HOST] [--port PORT] [--ui]",
            "cts manage serve jsonrpc [--host HOST] [--port PORT]",
            "cts manage serve mcp [--host HOST] [--port PORT]",
            "```",
            "",
        ])
        
        return "\n".join(lines)
    
    def _format_json(self, obj: Any, indent: int = 2) -> str:
        """Format object as JSON string."""
        import json
        return json.dumps(obj, ensure_ascii=False, indent=indent)


def generate_docs(app: CTSApp, output_dir: Optional[Path] = None, **kwargs) -> Dict[str, Path]:
    """Generate documentation for a CTS app."""
    config = DocsConfig(
        output_dir=output_dir or Path("docs/generated"),
        **kwargs,
    )
    generator = DocsGenerator(app, config)
    return generator.generate()
