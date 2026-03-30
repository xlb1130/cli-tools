"""Configuration migration framework for CTS."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

import yaml


class MigrationType(str, Enum):
    """Type of migration."""
    FIELD_RENAME = "field_rename"
    FIELD_MOVE = "field_move"
    VALUE_TRANSFORM = "value_transform"
    STRUCTURE_CHANGE = "structure_change"
    DEPRECATION = "deprecation"


@dataclass
class MigrationAction:
    """A single migration action."""
    type: MigrationType
    description: str
    old_path: Optional[str] = None
    new_path: Optional[str] = None
    old_value: Any = None
    new_value: Any = None
    automated: bool = True
    requires_confirmation: bool = False


@dataclass
class MigrationPlan:
    """A migration plan with all actions."""
    from_version: int
    to_version: int
    actions: List[MigrationAction] = field(default_factory=list)
    
    @property
    def automated_actions(self) -> List[MigrationAction]:
        return [a for a in self.actions if a.automated]
    
    @property
    def manual_actions(self) -> List[MigrationAction]:
        return [a for a in self.actions if not a.automated]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "action_count": len(self.actions),
            "automated_count": len(self.automated_actions),
            "manual_count": len(self.manual_actions),
            "actions": [
                {
                    "type": action.type.value,
                    "description": action.description,
                    "old_path": action.old_path,
                    "new_path": action.new_path,
                    "automated": action.automated,
                    "requires_confirmation": action.requires_confirmation,
                }
                for action in self.actions
            ],
        }


@dataclass
class MigrationResult:
    """Result of applying a migration."""
    success: bool
    from_version: int
    to_version: int
    applied_actions: List[MigrationAction] = field(default_factory=list)
    skipped_actions: List[MigrationAction] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "applied_count": len(self.applied_actions),
            "skipped_count": len(self.skipped_actions),
            "errors": self.errors,
            "warnings": self.warnings,
        }


# Type for migration functions
MigrationFunc = Callable[[Dict[str, Any]], List[MigrationAction]]


# Registry of migrations
_MIGRATIONS: Dict[int, Dict[int, MigrationFunc]] = {}


def register_migration(from_version: int, to_version: int):
    """Decorator to register a migration function."""
    def decorator(func: MigrationFunc) -> MigrationFunc:
        if from_version not in _MIGRATIONS:
            _MIGRATIONS[from_version] = {}
        _MIGRATIONS[from_version][to_version] = func
        return func
    return decorator


def get_available_migrations(from_version: int) -> Dict[int, MigrationFunc]:
    """Get all available migrations from a version."""
    return _MIGRATIONS.get(from_version, {})


def get_latest_version() -> int:
    """Get the latest supported config version."""
    return 2


class MigrationManager:
    """Manage configuration migrations."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
    
    def analyze(self, config: Dict[str, Any]) -> MigrationPlan:
        """Analyze a configuration and create a migration plan."""
        current_version = config.get("version", 1)
        latest_version = get_latest_version()
        
        if current_version >= latest_version:
            return MigrationPlan(from_version=current_version, to_version=current_version)
        
        # Find migration path
        actions = self._collect_migration_actions(config, current_version, latest_version)
        
        return MigrationPlan(
            from_version=current_version,
            to_version=latest_version,
            actions=actions,
        )
    
    def _collect_migration_actions(
        self,
        config: Dict[str, Any],
        from_version: int,
        to_version: int,
    ) -> List[MigrationAction]:
        """Collect all migration actions between versions."""
        actions = []
        current_version = from_version
        
        while current_version < to_version:
            migrations = get_available_migrations(current_version)
            if not migrations:
                # No direct migration, try step by step
                next_version = current_version + 1
                if next_version > to_version:
                    break
                migrations = get_available_migrations(current_version)
                if not migrations:
                    break
                current_version = next_version
                continue
            
            # Get the migration to the next version
            next_version = min(migrations.keys())
            migration_func = migrations.get(next_version)
            if migration_func:
                actions.extend(migration_func(config))
            current_version = next_version
        
        return actions
    
    def apply(
        self,
        config: Dict[str, Any],
        plan: Optional[MigrationPlan] = None,
        dry_run: bool = False,
    ) -> MigrationResult:
        """Apply a migration plan to a configuration."""
        if plan is None:
            plan = self.analyze(config)
        
        if plan.from_version == plan.to_version:
            return MigrationResult(
                success=True,
                from_version=plan.from_version,
                to_version=plan.to_version,
            )
        
        result = MigrationResult(
            success=True,
            from_version=plan.from_version,
            to_version=plan.to_version,
        )
        
        # Work on a copy
        updated = copy.deepcopy(config)
        
        for action in plan.actions:
            if not action.automated:
                result.skipped_actions.append(action)
                result.warnings.append(f"Skipped manual action: {action.description}")
                continue
            
            try:
                self._apply_action(updated, action)
                result.applied_actions.append(action)
            except Exception as e:
                result.skipped_actions.append(action)
                result.errors.append(f"Failed to apply {action.description}: {str(e)}")
        
        # Update version
        updated["version"] = plan.to_version
        
        if dry_run:
            result.warnings.append("Dry run: no changes were saved")
        else:
            # Save the migrated config
            if self.config_path:
                self._save_config(updated)
        
        return result
    
    def _apply_action(self, config: Dict[str, Any], action: MigrationAction) -> None:
        """Apply a single migration action."""
        if action.type == MigrationType.FIELD_RENAME:
            if action.old_path and action.new_path:
                value = self._get_value(config, action.old_path)
                if value is not None:
                    self._set_value(config, action.new_path, value)
                    self._delete_value(config, action.old_path)
        
        elif action.type == MigrationType.FIELD_MOVE:
            if action.old_path and action.new_path:
                value = self._get_value(config, action.old_path)
                if value is not None:
                    self._set_value(config, action.new_path, value)
                    self._delete_value(config, action.old_path)
        
        elif action.type == MigrationType.VALUE_TRANSFORM:
            if action.old_path:
                value = self._get_value(config, action.old_path)
                if value is None and action.old_value is None:
                    self._set_value(config, action.old_path, action.new_value)
                elif value is not None and value == action.old_value:
                    self._set_value(config, action.old_path, action.new_value)
        
        elif action.type == MigrationType.STRUCTURE_CHANGE:
            # Custom handling would be needed for complex changes
            pass
        
        elif action.type == MigrationType.DEPRECATION:
            if action.old_path:
                self._delete_value(config, action.old_path)
    
    def _get_value(self, config: Dict[str, Any], path: str) -> Any:
        """Get a value from config by dotted path."""
        keys = path.split(".")
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
    
    def _set_value(self, config: Dict[str, Any], path: str, value: Any) -> None:
        """Set a value in config by dotted path."""
        keys = path.split(".")
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
    
    def _delete_value(self, config: Dict[str, Any], path: str) -> None:
        """Delete a value from config by dotted path."""
        keys = path.split(".")
        current = config
        for key in keys[:-1]:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return
        if isinstance(current, dict) and keys[-1] in current:
            del current[keys[-1]]
    
    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        if not self.config_path:
            return
        
        from pathlib import Path
        path = Path(self.config_path)
        content = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
        path.write_text(content, encoding="utf-8")


# Define built-in migrations
# These would be registered as needed for future version changes

@register_migration(from_version=1, to_version=2)
def migrate_v1_to_v2(config: Dict[str, Any]) -> List[MigrationAction]:
    """Migrate from config version 1 to 2."""
    actions: List[MigrationAction] = []

    if "retry" in config:
        actions.append(
            MigrationAction(
                type=MigrationType.FIELD_MOVE,
                description="Move top-level retry settings to reliability.defaults.retry",
                old_path="retry",
                new_path="reliability.defaults.retry",
                automated=True,
            )
        )

    if "timeout_seconds" in config:
        actions.append(
            MigrationAction(
                type=MigrationType.FIELD_MOVE,
                description="Move top-level timeout_seconds to reliability.defaults.timeout_seconds",
                old_path="timeout_seconds",
                new_path="reliability.defaults.timeout_seconds",
                automated=True,
            )
        )

    if "concurrency" in config:
        actions.append(
            MigrationAction(
                type=MigrationType.FIELD_MOVE,
                description="Move top-level concurrency settings to reliability.defaults.concurrency",
                old_path="concurrency",
                new_path="reliability.defaults.concurrency",
                automated=True,
            )
        )

    compatibility = config.get("compatibility")
    if not isinstance(compatibility, dict) or "catalog_version" not in compatibility:
        actions.append(
            MigrationAction(
                type=MigrationType.VALUE_TRANSFORM,
                description="Initialize compatibility.catalog_version to 1",
                old_path="compatibility.catalog_version",
                old_value=None,
                new_value=1,
                automated=True,
            )
        )

    if not isinstance(compatibility, dict) or "error_contract_version" not in compatibility:
        actions.append(
            MigrationAction(
                type=MigrationType.VALUE_TRANSFORM,
                description="Initialize compatibility.error_contract_version to 1",
                old_path="compatibility.error_contract_version",
                old_value=None,
                new_value=1,
                automated=True,
            )
        )

    return actions


def create_migration_plan(config: Dict[str, Any]) -> MigrationPlan:
    """Create a migration plan for a configuration."""
    manager = MigrationManager()
    return manager.analyze(config)


def apply_migration(
    config: Dict[str, Any],
    config_path: Optional[str] = None,
    dry_run: bool = False,
) -> MigrationResult:
    """Apply migration to a configuration."""
    manager = MigrationManager(config_path=config_path)
    plan = manager.analyze(config)
    return manager.apply(config, plan=plan, dry_run=dry_run)
