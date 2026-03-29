from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from cts.config.loader import LoadedConfig
from cts.providers.registry import ProviderRegistry


def lint_loaded_config(loaded_config: LoadedConfig) -> Dict[str, List[Dict[str, Any]]]:
    config = loaded_config.config
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    supported_provider_types = ProviderRegistry().supported_types()

    if config.app.default_profile and config.app.default_profile not in config.profiles:
        errors.append(
            _issue(
                "ConfigError",
                "default_profile_not_found",
                f"default_profile '{config.app.default_profile}' was not found in profiles.",
                details={"default_profile": config.app.default_profile},
            )
        )

    for source_name, source in config.sources.items():
        source_origin = _origin_file(source)
        if source.type not in supported_provider_types:
            errors.append(
                _issue(
                    "ConfigError",
                    "unsupported_provider_type",
                    f"source '{source_name}' uses unsupported provider type '{source.type}'.",
                    details={"source": source_name, "provider_type": source.type, "origin_file": source_origin},
                )
            )

        if source.auth_ref and source.auth_ref not in config.auth_profiles:
            errors.append(
                _issue(
                    "ConfigError",
                    "auth_profile_not_found",
                    f"source '{source_name}' references missing auth profile '{source.auth_ref}'.",
                    details={"source": source_name, "auth_ref": source.auth_ref, "origin_file": source_origin},
                )
            )

        if source.discovery.manifest:
            manifest_path = _resolve_source_path(loaded_config, source, source.discovery.manifest)
            if not manifest_path.exists():
                errors.append(
                    _issue(
                        "ConfigError",
                        "manifest_not_found",
                        f"source '{source_name}' manifest file was not found.",
                        details={
                            "source": source_name,
                            "manifest": source.discovery.manifest,
                            "resolved_path": str(manifest_path),
                            "origin_file": source_origin,
                        },
                    )
                )

        if source.config_file:
            config_file = _resolve_source_path(loaded_config, source, source.config_file)
            if not config_file.exists():
                errors.append(
                    _issue(
                        "ConfigError",
                        "source_config_file_not_found",
                        f"source '{source_name}' config_file was not found.",
                        details={
                            "source": source_name,
                            "config_file": source.config_file,
                            "resolved_path": str(config_file),
                            "origin_file": source_origin,
                        },
                    )
                )

        if source.working_dir:
            working_dir = _resolve_source_path(loaded_config, source, source.working_dir)
            if not working_dir.exists():
                warnings.append(
                    _issue(
                        "ConfigWarning",
                        "working_dir_not_found",
                        f"source '{source_name}' working_dir does not exist yet.",
                        details={
                            "source": source_name,
                            "working_dir": source.working_dir,
                            "resolved_path": str(working_dir),
                            "origin_file": source_origin,
                        },
                    )
                )

    source_names = set(config.sources.keys())
    for mount in config.mounts:
        mount_origin = _origin_file(mount)
        if mount.source not in source_names:
            errors.append(
                _issue(
                    "ConfigError",
                    "mount_source_not_found",
                    f"mount '{mount.id}' references missing source '{mount.source}'.",
                    details={"mount_id": mount.id, "source": mount.source, "origin_file": mount_origin},
                )
            )
            continue

        source = config.sources[mount.source]
        source_surfaces = set(source.expose_to_surfaces or [])
        mount_surfaces = set(mount.machine.expose_via or [])
        if source_surfaces and mount_surfaces and not mount_surfaces.issubset(source_surfaces):
            warnings.append(
                _issue(
                    "ConfigWarning",
                    "mount_surface_not_exposed_by_source",
                    f"mount '{mount.id}' exposes surfaces not declared by source '{mount.source}'.",
                    details={
                        "mount_id": mount.id,
                        "source": mount.source,
                        "mount_surfaces": sorted(mount_surfaces),
                        "source_surfaces": sorted(source_surfaces),
                        "origin_file": mount_origin,
                    },
                )
            )

    return {"errors": errors, "warnings": warnings}


def _issue(issue_type: str, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "type": issue_type,
        "code": code,
        "message": message,
        "details": details or {},
    }


def _origin_file(owner: Any) -> Optional[str]:
    model_extra = getattr(owner, "model_extra", None) or {}
    origin = model_extra.get("__origin_file__")
    return str(origin) if origin else None


def _resolve_source_path(loaded_config: LoadedConfig, owner: Any, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    origin = _origin_file(owner)
    if origin:
        return (Path(origin).parent / candidate).resolve()
    base_dir = loaded_config.root_paths[-1].parent if loaded_config.root_paths else Path.cwd()
    return (base_dir / candidate).resolve()
