from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

import yaml

from cts.app import CTSApp, build_app
from cts.config.loader import LoadedConfig, load_config
from cts.config.models import CTSConfig
from cts.execution.errors import ConfigError


SUPPORTED_CONFIG_SUFFIXES = {".yaml", ".yml", ".json"}


class ConfigEditError(ConfigError):
    pass


@dataclass
class ConfigEditSession:
    loaded: LoadedConfig
    target_path: Path
    validation_reference: Optional[Path]
    target_exists: bool
    target_raw: Dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    @property
    def created(self) -> bool:
        return not self.target_exists


def prepare_edit_session(
    explicit_config_path: Optional[Path],
    *,
    target_file: Optional[Path] = None,
) -> ConfigEditSession:
    loaded, validation_reference = _load_for_edit(explicit_config_path)
    configured_root = loaded.root_paths[-1] if loaded.root_paths else _default_new_target(validation_reference)
    target_path = _resolve_target_path(
        loaded,
        validation_reference=validation_reference,
        target_file=target_file,
        configured_root=configured_root,
    )
    target_exists = target_path.exists()
    target_raw = _read_raw(target_path) if target_exists else {}
    warnings: list[str] = []

    if loaded.paths and target_path == configured_root and len(loaded.paths) > 1:
        warnings.append(
            "当前配置已启用 imports，新增内容默认写入 root config；如需写入某个分文件，请显式传入 --file。"
        )

    return ConfigEditSession(
        loaded=loaded,
        target_path=target_path,
        validation_reference=validation_reference,
        target_exists=target_exists,
        target_raw=target_raw,
        warnings=warnings,
    )


def apply_update(
    session: ConfigEditSession,
    mutator: Callable[[Dict[str, Any]], None],
    *,
    compile_runtime: bool = False,
    profile: Optional[str] = None,
    baseline_conflicts: Optional[Iterable[str]] = None,
) -> tuple[Dict[str, Any], Optional[CTSApp]]:
    updated = copy.deepcopy(session.target_raw)
    if not updated:
        updated["version"] = 1
    mutator(updated)
    if "version" not in updated:
        updated["version"] = 1

    original_text = session.target_path.read_text(encoding="utf-8") if session.target_exists else None
    session.target_path.parent.mkdir(parents=True, exist_ok=True)
    session.target_path.write_text(_serialize_raw(updated, session.target_path), encoding="utf-8")

    try:
        validation_reference = str(session.validation_reference) if session.validation_reference else None
        load_config(validation_reference)
        compiled_app: Optional[CTSApp] = None
        if compile_runtime:
            compiled_app = build_app(validation_reference, profile=profile)
            if baseline_conflicts is not None:
                current = conflict_signatures(compiled_app.catalog.conflicts)
                introduced = current.difference(set(baseline_conflicts))
                if introduced:
                    raise ConfigEditError(
                        "新增配置引入了命令冲突: " + "; ".join(sorted(introduced))
                    )
        return updated, compiled_app
    except Exception:
        _restore_original(session.target_path, original_text)
        raise


def conflict_signatures(conflicts: Sequence[Dict[str, Any]]) -> set[str]:
    return {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in conflicts}


def apply_assignment(payload: Dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = [part for part in dotted_path.split(".") if part]
    if not parts:
        raise ConfigEditError("配置覆盖路径不能为空。")

    current: Dict[str, Any] = payload
    for part in parts[:-1]:
        next_value = current.get(part)
        if next_value is None:
            next_value = {}
            current[part] = next_value
        if not isinstance(next_value, dict):
            raise ConfigEditError(f"无法在非映射节点上继续写入: {dotted_path}")
        current = next_value
    current[parts[-1]] = value


def parse_assignment(assignment: str) -> tuple[str, Any]:
    if "=" not in assignment:
        raise ConfigEditError(f"配置覆盖必须是 key=value 格式: {assignment}")
    key, raw_value = assignment.split("=", 1)
    key = key.strip()
    if not key:
        raise ConfigEditError(f"配置覆盖路径不能为空: {assignment}")
    return key, yaml.safe_load(raw_value)


def parse_string_map_item(raw: str, *, field_name: str) -> tuple[str, str]:
    if "=" not in raw:
        raise ConfigEditError(f"{field_name} 必须是 key=value 格式: {raw}")
    key, value = raw.split("=", 1)
    key = key.strip()
    if not key:
        raise ConfigEditError(f"{field_name} 的 key 不能为空: {raw}")
    return key, value


def ensure_mapping(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    current = payload.get(key)
    if current is None:
        current = {}
        payload[key] = current
    if not isinstance(current, dict):
        raise ConfigEditError(f"字段 '{key}' 必须是对象。")
    return current


def ensure_list(payload: Dict[str, Any], key: str) -> list[Any]:
    current = payload.get(key)
    if current is None:
        current = []
        payload[key] = current
    if not isinstance(current, list):
        raise ConfigEditError(f"字段 '{key}' 必须是数组。")
    return current


def _load_for_edit(explicit_config_path: Optional[Path]) -> tuple[LoadedConfig, Optional[Path]]:
    if explicit_config_path:
        resolved = explicit_config_path.expanduser().resolve()
        if resolved.exists():
            return load_config(str(resolved)), resolved
        return (
            LoadedConfig(config=CTSConfig(), paths=[], raw={}, root_paths=[resolved]),
            resolved,
        )

    loaded = load_config(None)
    return loaded, None


def _resolve_target_path(
    loaded: LoadedConfig,
    *,
    validation_reference: Optional[Path],
    target_file: Optional[Path],
    configured_root: Path,
) -> Path:
    if target_file is None:
        return configured_root

    target_path = target_file.expanduser().resolve()
    allowed_existing = set(loaded.paths) | set(loaded.root_paths)
    if target_path.exists():
        if allowed_existing and target_path not in allowed_existing:
            raise ConfigEditError(
                "目标文件必须已经是当前配置图中的已加载文件；若要创建新 root config，请使用 --config 指向它。"
            )
        if not allowed_existing and target_path != configured_root:
            raise ConfigEditError(
                "当前没有已加载配置，只有 root config 文件允许被直接创建或编辑。"
            )
        return target_path

    if target_path != configured_root:
        raise ConfigEditError(
            "只能自动创建 root config 文件；如果想写入分文件，请先把该文件加入 imports 后再使用 --file。"
        )

    if target_path.suffix.lower() not in SUPPORTED_CONFIG_SUFFIXES:
        raise ConfigEditError(f"不支持的配置文件类型: {target_path}")

    if validation_reference is None and loaded.root_paths:
        return target_path
    return target_path


def _default_new_target(validation_reference: Optional[Path]) -> Path:
    if validation_reference is not None:
        return validation_reference
    return (Path.cwd() / ".cts" / "config.yaml").resolve()


def _read_raw(path: Path) -> Dict[str, Any]:
    if path.suffix.lower() not in SUPPORTED_CONFIG_SUFFIXES:
        raise ConfigEditError(f"不支持的配置文件类型: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text or "{}")
    else:
        raw = yaml.safe_load(text) or {}
    if not isinstance(raw, dict):
        raise ConfigEditError(f"配置文件根节点必须是对象: {path}")
    return raw


def _serialize_raw(payload: Dict[str, Any], path: Path) -> str:
    if path.suffix.lower() == ".json":
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def _restore_original(path: Path, original_text: Optional[str]) -> None:
    if original_text is None:
        if path.exists():
            path.unlink()
        return
    path.write_text(original_text, encoding="utf-8")
