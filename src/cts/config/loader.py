from __future__ import annotations

import copy
import glob
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

import yaml

if TYPE_CHECKING:
    from cts.config.models import CTSConfig

APPEND_LIST_KEYS = {"mounts", "aliases", "hooks", "workflows"}
SUPPORTED_CONFIG_SUFFIXES = {".yaml", ".yml", ".json"}


@dataclass
class LoadedConfig:
    config: CTSConfig
    paths: List[Path]
    raw: Dict[str, Any] = field(default_factory=dict)
    root_paths: List[Path] = field(default_factory=list)


@dataclass
class LoadedRawConfig:
    raw: Dict[str, Any]
    paths: List[Path]
    root_paths: List[Path] = field(default_factory=list)


def deep_merge(left: Dict[str, Any], right: Dict[str, Any], path: tuple = ()) -> Dict[str, Any]:
    merged = copy.deepcopy(left)
    for key, value in right.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value, path + (key,))
        elif (
            key in merged
            and isinstance(merged[key], list)
            and isinstance(value, list)
            and len(path) == 0
            and key in APPEND_LIST_KEYS
        ):
            merged[key] = copy.deepcopy(merged[key]) + copy.deepcopy(value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _default_paths() -> List[Path]:
    """Return default config file search paths in priority order."""
    return [
        Path.home() / ".cts" / "config.yaml",  # User home default (highest priority)
        Path.home() / ".config" / "cts" / "config.yaml",  # XDG config dir
        Path.cwd() / ".cts" / "config.yaml",  # Current directory
        Path.cwd() / "cts.yaml",  # Current directory (simple name)
    ]


def _read_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text or "{}")
    else:
        raw = yaml.safe_load(text) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping: {path}")
    return raw


def _resolve_paths(explicit_path: Optional[str]) -> List[Path]:
    from cts.execution.logging import emit_config_event
    
    emit_config_event(
        event="config.resolve_start",
        message="Resolving config paths",
        data={"explicit_path": explicit_path},
    )
    
    if explicit_path:
        paths = [Path(explicit_path).expanduser().resolve()]
        emit_config_event(
            event="config.resolve_complete",
            message="Using explicit config path",
            path=str(paths[0]) if paths else None,
            data={"source": "explicit", "paths": [str(p) for p in paths]},
        )
        return paths

    env_path = os.environ.get("CTS_CONFIG")
    if env_path:
        paths = [Path(env_path).expanduser().resolve()]
        emit_config_event(
            event="config.resolve_complete",
            message="Using CTS_CONFIG environment variable",
            path=str(paths[0]) if paths else None,
            data={"source": "env", "paths": [str(p) for p in paths]},
        )
        return paths

    paths: List[Path] = []
    searched: List[str] = []
    for candidate in _default_paths():
        searched.append(str(candidate))
        if candidate.exists():
            paths.append(candidate.resolve())
    
    emit_config_event(
        event="config.resolve_complete",
        message=f"Found {len(paths)} config file(s)",
        data={"source": "default_search", "searched": searched, "paths": [str(p) for p in paths]},
    )
    return paths


def load_config(explicit_path: Optional[str] = None) -> LoadedConfig:
    from cts.execution.logging import emit_config_event
    from cts.config.models import CTSConfig
    
    emit_config_event(
        event="config.load_start",
        message="Starting config load",
        data={"explicit_path": explicit_path},
    )
    
    root_paths = _resolve_paths(explicit_path)
    if not root_paths:
        emit_config_event(
            event="config.load_complete",
            level="WARN",
            message="No config files found, using empty config",
            data={"loaded_count": 0},
        )
        return LoadedConfig(config=CTSConfig(), paths=[], raw={}, root_paths=[])

    merged: Dict[str, Any] = {}
    loaded_paths: List[Path] = []
    seen: Set[Path] = set()

    for path in root_paths:
        merged = deep_merge(merged, _load_file_tree(path, loaded_paths, seen, stack=[]))

    config = CTSConfig.model_validate(merged)
    
    emit_config_event(
        event="config.load_complete",
        message=f"Config loaded successfully",
        data={
            "loaded_count": len(loaded_paths),
            "loaded_paths": [str(p) for p in loaded_paths],
            "source_count": len(config.sources),
            "mount_count": len(config.mounts),
        },
    )
    
    return LoadedConfig(config=config, paths=loaded_paths, raw=merged, root_paths=root_paths)


def load_raw_config(explicit_path: Optional[str] = None) -> LoadedRawConfig:
    root_paths = _resolve_paths(explicit_path)
    if not root_paths:
        return LoadedRawConfig(raw={}, paths=[], root_paths=[])

    merged: Dict[str, Any] = {}
    loaded_paths: List[Path] = []
    seen: Set[Path] = set()

    for path in root_paths:
        merged = deep_merge(merged, _load_file_tree(path, loaded_paths, seen, stack=[]))

    return LoadedRawConfig(raw=merged, paths=loaded_paths, root_paths=root_paths)


def _load_file_tree(path: Path, loaded_paths: List[Path], seen: Set[Path], stack: List[Path]) -> Dict[str, Any]:
    from cts.execution.logging import emit_config_event
    
    resolved = path.expanduser().resolve()
    if resolved in stack:
        cycle = " -> ".join(str(item) for item in stack + [resolved])
        emit_config_event(
            event="config.import_cycle",
            level="ERROR",
            message=f"Config import cycle detected",
            path=str(resolved),
            data={"cycle": cycle},
        )
        raise ValueError(f"config import cycle detected: {cycle}")
    if resolved in seen:
        return {}
    if not resolved.exists():
        emit_config_event(
            event="config.file_not_found",
            level="ERROR",
            message=f"Config file not found",
            path=str(resolved),
        )
        raise ValueError(f"config file not found: {resolved}")
    if resolved.suffix.lower() not in SUPPORTED_CONFIG_SUFFIXES:
        emit_config_event(
            event="config.unsupported_type",
            level="ERROR",
            message=f"Unsupported config file type",
            path=str(resolved),
        )
        raise ValueError(f"unsupported config file type: {resolved}")

    emit_config_event(
        event="config.file_load_start",
        message=f"Loading config file",
        path=str(resolved),
    )
    
    raw = _annotate_origins(_read_file(resolved), resolved)
    imports = raw.pop("imports", []) or []
    if not isinstance(imports, list):
        raise ValueError(f"'imports' must be a list: {resolved}")

    merged: Dict[str, Any] = {}
    next_stack = stack + [resolved]
    imported_files: List[str] = []
    import_errors: List[str] = []
    
    for item in imports:
        if not isinstance(item, str):
            raise ValueError(f"import entry must be a string in {resolved}")
        try:
            for imported in _expand_import(resolved.parent, item):
                merged = deep_merge(merged, _load_file_tree(imported, loaded_paths, seen, next_stack))
                imported_files.append(str(imported))
        except Exception as e:
            import_errors.append(f"{item}: {str(e)}")
            emit_config_event(
                event="config.import_error",
                level="WARN",
                message=f"Failed to import: {item}",
                path=str(resolved),
                data={"import": item, "error": str(e)},
            )

    seen.add(resolved)
    loaded_paths.append(resolved)
    
    emit_config_event(
        event="config.file_load_complete",
        message=f"Config file loaded",
        path=str(resolved),
        data={
            "imports_count": len(imported_files),
            "imports": imported_files[:20],  # Limit to avoid huge logs
            "import_errors": import_errors if import_errors else None,
            "keys": list(raw.keys()),
        },
    )
    
    return deep_merge(merged, raw)


def _expand_import(base_dir: Path, entry: str) -> List[Path]:
    candidate = Path(entry).expanduser()
    target = candidate if candidate.is_absolute() else (base_dir / candidate)
    target_string = str(target)
    matches: List[Path] = []

    if glob.has_magic(target_string):
        matches = [Path(item).resolve() for item in sorted(glob.glob(target_string, recursive=True))]
    elif target.is_dir():
        matches = sorted(
            [item.resolve() for item in target.rglob("*") if item.is_file() and item.suffix.lower() in SUPPORTED_CONFIG_SUFFIXES]
        )
    else:
        matches = [target.resolve()]

    if not matches:
        raise ValueError(f"config import matched no files: {entry}")

    filtered = [item for item in matches if item.suffix.lower() in SUPPORTED_CONFIG_SUFFIXES]
    if not filtered:
        raise ValueError(f"config import matched no supported config files: {entry}")
    return filtered


def _annotate_origins(raw: Dict[str, Any], path: Path) -> Dict[str, Any]:
    annotated = copy.deepcopy(raw)
    origin = str(path)

    if isinstance(annotated.get("sources"), dict):
        for value in annotated["sources"].values():
            if isinstance(value, dict):
                value["__origin_file__"] = origin

    if isinstance(annotated.get("mounts"), list):
        for value in annotated["mounts"]:
            if isinstance(value, dict):
                value["__origin_file__"] = origin

    if isinstance(annotated.get("profiles"), dict):
        for value in annotated["profiles"].values():
            if isinstance(value, dict):
                value["__origin_file__"] = origin

    if isinstance(annotated.get("plugins"), dict):
        for value in annotated["plugins"].values():
            if isinstance(value, dict):
                value["__origin_file__"] = origin

    if isinstance(annotated.get("secrets"), dict):
        for value in annotated["secrets"].values():
            if isinstance(value, dict):
                value["__origin_file__"] = origin

    if isinstance(annotated.get("auth_profiles"), dict):
        for value in annotated["auth_profiles"].values():
            if isinstance(value, dict):
                value["__origin_file__"] = origin

    if isinstance(annotated.get("hooks"), list):
        for value in annotated["hooks"]:
            if isinstance(value, dict):
                value["__origin_file__"] = origin

    if isinstance(annotated.get("workflows"), list):
        for value in annotated["workflows"]:
            if isinstance(value, dict):
                value["__origin_file__"] = origin

    return annotated
