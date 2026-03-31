from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from cts.models import MountRecord


class Catalog:
    def __init__(self) -> None:
        self.mounts: List[MountRecord] = []
        self._mounts_by_id: Dict[str, MountRecord] = {}
        self._path_index: Dict[Tuple[str, ...], MountRecord] = {}
        self._group_help: Dict[Tuple[str, ...], Dict[str, str]] = {}
        self._conflicts: List[Dict[str, Any]] = []

    @property
    def conflicts(self) -> List[Dict[str, Any]]:
        return list(self._conflicts)

    def add_mount(self, mount: MountRecord) -> None:
        if mount.mount_id in self._mounts_by_id:
            self._conflicts.append(
                {"type": "mount_id", "mount_id": mount.mount_id, "command_path": mount.command_path}
            )
            return

        if not self._register_path(mount.command_path, mount, path_type="command_path"):
            return

        self.mounts.append(mount)
        self._mounts_by_id[mount.mount_id] = mount
        for alias in mount.aliases:
            self._register_path(alias, mount, path_type="mount_alias", target_path=mount.command_path)

    def add_alias(self, alias_path: Iterable[str], target_path: Iterable[str]) -> None:
        target_tokens = tuple(target_path)
        mount = self._path_index.get(target_tokens)
        if mount is None:
            self._conflicts.append(
                {
                    "type": "alias_target_not_found",
                    "alias_path": list(alias_path),
                    "target_path": list(target_path),
                }
            )
            return

        alias_tokens = list(alias_path)
        if alias_tokens not in mount.aliases:
            mount.aliases.append(alias_tokens)
        self._register_path(alias_tokens, mount, path_type="config_alias", target_path=target_tokens)

    def _register_path(
        self,
        path: Iterable[str],
        mount: MountRecord,
        *,
        path_type: str,
        target_path: Optional[Iterable[str]] = None,
    ) -> bool:
        key = tuple(path)
        if not key:
            return False

        if key in self._path_index:
            existing = self._path_index[key]
            if existing.mount_id == mount.mount_id:
                return True
            self._conflicts.append(
                {
                    "type": "command_path",
                    "path": list(key),
                    "mount_id": mount.mount_id,
                    "existing_mount_id": existing.mount_id,
                    "path_type": path_type,
                    "target_path": list(target_path) if target_path else None,
                }
            )
            return False

        for existing_key, existing_mount in self._path_index.items():
            if key[: len(existing_key)] == existing_key or existing_key[: len(key)] == key:
                self._conflicts.append(
                    {
                        "type": "path_prefix",
                        "path": list(key),
                        "existing_path": list(existing_key),
                        "mount_id": mount.mount_id,
                        "existing_mount_id": existing_mount.mount_id,
                        "path_type": path_type,
                        "target_path": list(target_path) if target_path else None,
                    }
                )
                return False
        self._path_index[key] = mount
        return True

    def find_by_id(self, mount_id: str) -> Optional[MountRecord]:
        return self._mounts_by_id.get(mount_id)

    def find_by_path(self, path: Iterable[str]) -> Optional[MountRecord]:
        return self._path_index.get(tuple(path))

    def find_by_source_and_operation(self, source_name: str, operation_id: str) -> Optional[MountRecord]:
        for mount in self.mounts:
            if mount.source_name == source_name and mount.operation.id == operation_id:
                return mount
        return None

    def has_group(self, prefix: Iterable[str]) -> bool:
        prefix_tuple = tuple(prefix)
        for path in self._path_index:
            if len(path) > len(prefix_tuple) and path[: len(prefix_tuple)] == prefix_tuple:
                return True
        return prefix_tuple in self._group_help

    def child_tokens(self, prefix: Iterable[str]) -> List[str]:
        prefix_tuple = tuple(prefix)
        tokens = set()
        for path in self._path_index:
            if len(path) <= len(prefix_tuple):
                continue
            if path[: len(prefix_tuple)] == prefix_tuple:
                tokens.add(path[len(prefix_tuple)])
        return sorted(tokens)

    def group_summary(self, prefix: Iterable[str]) -> str:
        help_payload = self._group_help.get(tuple(prefix)) or {}
        return help_payload.get("summary") or "Dynamic command group for " + " ".join(prefix)

    def group_description(self, prefix: Iterable[str]) -> str:
        help_payload = self._group_help.get(tuple(prefix)) or {}
        return help_payload.get("description") or self.group_summary(prefix)

    def add_group_help(self, prefix: Iterable[str], *, summary: Optional[str], description: Optional[str]) -> None:
        prefix_tuple = tuple(prefix)
        if not prefix_tuple:
            return
        self._group_help[prefix_tuple] = {
            "summary": summary or " ".join(prefix_tuple),
            "description": description or summary or "Dynamic command group for " + " ".join(prefix_tuple),
        }

    def to_catalog(self) -> Dict[str, Any]:
        return {
            "mounts": [mount.to_summary() for mount in self.mounts],
            "conflicts": list(self._conflicts),
        }
