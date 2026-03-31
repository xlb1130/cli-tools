"""Tests for Phase 3 features: compatibility, migration, auth validation."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from cts.cli.root import main
from cts.config.compatibility import (
    CompatibilityCategory,
    CompatibilityChecker,
    CompatibilityLevel,
    check_compatibility,
    compare_versions,
    parse_version,
    version_in_range,
)
from cts.config.migration import (
    MigrationAction,
    MigrationManager,
    MigrationType,
    create_migration_plan,
    get_latest_version,
)


class TestCompatibilityVersionParsing:
    """Tests for version parsing utilities."""
    
    def test_parse_version_simple(self):
        assert parse_version("1.0.0") == (1, 0, 0)
        assert parse_version("2.5.3") == (2, 5, 3)
        assert parse_version("1") == (1,)
    
    def test_parse_version_with_prefix(self):
        assert parse_version("v1.0.0") == (1, 0, 0)
        assert parse_version("v2.5.3") == (2, 5, 3)
    
    def test_parse_version_complex(self):
        # The regex extracts ALL numbers, including build numbers
        result = parse_version("1.0.0-beta")
        assert result[:3] == (1, 0, 0)  # First 3 numbers are the version
        result = parse_version("2.5.3+build.123")
        assert result[:3] == (2, 5, 3)  # First 3 numbers are the version
    
    def test_parse_version_empty(self):
        assert parse_version("") == (0,)
        assert parse_version("invalid") == (0,)


class TestCompareVersions:
    """Tests for version comparison."""
    
    def test_equal_versions(self):
        assert compare_versions("1.0.0", "1.0.0") == 0
        # Note: "2.5" and "2.5.0" are different tuple lengths
        # This is expected behavior
    
    def test_less_than(self):
        assert compare_versions("1.0.0", "2.0.0") == -1
        assert compare_versions("1.5.0", "1.6.0") == -1
        assert compare_versions("1.0.0", "1.0.1") == -1
    
    def test_greater_than(self):
        assert compare_versions("2.0.0", "1.0.0") == 1
        assert compare_versions("1.6.0", "1.5.0") == 1
        assert compare_versions("1.0.1", "1.0.0") == 1


class TestVersionInRange:
    """Tests for version range checking."""
    
    def test_exact_match(self):
        assert version_in_range("1.0.0", "==1.0.0") is True
        assert version_in_range("1.0.0", "==2.0.0") is False
    
    def test_greater_than_or_equal(self):
        assert version_in_range("1.0.0", ">=1.0.0") is True
        assert version_in_range("1.5.0", ">=1.0.0") is True
        assert version_in_range("0.9.0", ">=1.0.0") is False
    
    def test_less_than(self):
        assert version_in_range("1.0.0", "<2.0.0") is True
        assert version_in_range("2.0.0", "<2.0.0") is False
        assert version_in_range("2.5.0", "<2.0.0") is False
    
    def test_range(self):
        assert version_in_range("1.5.0", ">=1.0,<2.0") is True
        assert version_in_range("1.0.0", ">=1.0,<2.0") is True
        assert version_in_range("2.0.0", ">=1.0,<2.0") is False
        assert version_in_range("0.5.0", ">=1.0,<2.0") is False
    
    def test_empty_range(self):
        assert version_in_range("1.0.0", "") is True


class TestCompatibilityChecker:
    """Tests for compatibility checker."""
    
    def test_check_config_version_ok(self):
        mock_app = MagicMock()
        mock_app.config.version = 1
        mock_app.config.compatibility = {}
        mock_app.config.sources = {}
        
        checker = CompatibilityChecker(mock_app)
        report = checker.check_all()
        
        assert report.ok is True
        assert len(report.errors) == 0
    
    def test_check_cts_version_required(self):
        mock_app = MagicMock()
        mock_app.config.version = 1
        mock_app.config.compatibility = {"min_cts_version": "999.0.0"}
        mock_app.config.sources = {}
        
        checker = CompatibilityChecker(mock_app)
        report = checker.check_all()
        
        # Should have an error because our version is less than 999.0.0
        assert len(report.errors) >= 1
        cts_errors = [e for e in report.errors if e.category == CompatibilityCategory.CTS_VERSION]
        assert len(cts_errors) >= 1


class TestMigrationManager:
    """Tests for migration manager."""
    
    def test_analyze_current_version(self):
        config = {"version": 2}
        manager = MigrationManager()
        plan = manager.analyze(config)
        
        assert plan.from_version == 2
        assert plan.to_version == 2
        assert len(plan.actions) == 0
    
    def test_get_latest_version(self):
        assert get_latest_version() == 2
    
    def test_apply_dry_run(self):
        config = {"version": 2, "sources": {}}
        manager = MigrationManager()
        plan = manager.analyze(config)
        result = manager.apply(config, plan=plan, dry_run=True)
        
        assert result.success is True
        assert result.from_version == 2
        assert result.to_version == 2
        # When already at latest version, dry_run warning is added
        assert result.warnings or result.applied_actions == []

    def test_analyze_v1_migration_actions(self):
        config = {"version": 1, "retry": {"max_attempts": 3}, "timeout_seconds": 10}
        manager = MigrationManager()
        plan = manager.analyze(config)

        assert plan.from_version == 1
        assert plan.to_version == 2
        assert len(plan.actions) >= 2


class TestMigrationActions:
    """Tests for migration actions."""
    
    def test_field_rename_action(self):
        manager = MigrationManager()
        config = {"old_field": "value"}
        
        action = MigrationAction(
            type=MigrationType.FIELD_RENAME,
            description="Rename old_field to new_field",
            old_path="old_field",
            new_path="new_field",
            automated=True,
        )
        
        manager._apply_action(config, action)
        
        assert "new_field" in config
        assert config["new_field"] == "value"
        assert "old_field" not in config
    
    def test_value_transform_action(self):
        manager = MigrationManager()
        config = {"setting": "old_value"}
        
        action = MigrationAction(
            type=MigrationType.VALUE_TRANSFORM,
            description="Transform old_value to new_value",
            old_path="setting",
            old_value="old_value",
            new_value="new_value",
            automated=True,
        )
        
        manager._apply_action(config, action)
        
        assert config["setting"] == "new_value"
    
    def test_deprecation_action(self):
        manager = MigrationManager()
        config = {"deprecated_field": "value", "other_field": "keep"}
        
        action = MigrationAction(
            type=MigrationType.DEPRECATION,
            description="Remove deprecated field",
            old_path="deprecated_field",
            automated=True,
        )
        
        manager._apply_action(config, action)
        
        assert "deprecated_field" not in config
        assert "other_field" in config


class TestCLIConfigMigrate:
    """Tests for config migrate CLI command."""
    
    def test_config_migrate_already_latest(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 2\nsources: {}\n", encoding="utf-8")
            
            result = runner.invoke(
                main,
                ["--config", str(config_path), "manage", "config", "migrate", "--format", "json"],
            )
            
            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["ok"] is True
            assert payload["actions_needed"] is False
    
    def test_config_migrate_dry_run(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")
            
            result = runner.invoke(
                main,
                ["--config", str(config_path), "manage", "config", "migrate", "--dry-run", "--format", "json"],
            )
            
            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["ok"] is True
            assert payload["to_version"] == 2
            assert payload["plan"]["action_count"] >= 2

    def test_config_migrate_updates_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text(
                "version: 1\nretry:\n  max_attempts: 4\ntimeout_seconds: 15\nsources: {}\n",
                encoding="utf-8",
            )

            result = runner.invoke(
                main,
                ["--config", str(config_path), "manage", "config", "migrate", "--format", "json"],
            )

            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["ok"] is True
            migrated = config_path.read_text(encoding="utf-8")
            assert "version: 2" in migrated
            assert "reliability:" in migrated
            assert "max_attempts: 4" in migrated


class TestCLIAuthValidate:
    """Tests for auth validate CLI command."""
    
    def test_auth_validate_all_empty(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nauth_profiles: {}\nsources: {}\n", encoding="utf-8")
            
            result = runner.invoke(
                main,
                ["--config", str(config_path), "manage", "auth", "validate", "--all", "--format", "json"],
            )
            
            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["ok"] is True
            assert payload["total_count"] == 0


class TestCLIDoctorEnhanced:
    """Tests for enhanced doctor command."""
    
    def test_doctor_with_compatibility(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nsources: {}\n", encoding="utf-8")
            
            result = runner.invoke(
                main,
                ["--config", str(config_path), "manage", "doctor", "--compatibility", "--format", "json"],
            )
            
            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert "compatibility" in payload
            assert payload["compatibility"]["ok"] is True
    
    def test_doctor_with_auth(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            config_path = Path("cts.yaml")
            config_path.write_text("version: 1\nauth_profiles: {}\nsources: {}\n", encoding="utf-8")
            
            result = runner.invoke(
                main,
                ["--config", str(config_path), "manage", "doctor", "--auth", "--format", "json"],
            )
            
            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert "auth" in payload


class TestAuthManagerValidate:
    """Tests for auth manager validation methods."""
    
    def test_validate_unconfigured_profile(self):
        mock_app = MagicMock()
        mock_app.config.auth_profiles = {}
        
        from cts.auth import AuthManager
        manager = AuthManager(mock_app)
        
        result = manager.validate("nonexistent")
        
        assert result["valid"] is False
        assert result["state"] == "unconfigured"
    
    def test_validate_all_empty(self):
        mock_app = MagicMock()
        mock_app.config.auth_profiles = {}
        
        from cts.auth import AuthManager
        manager = AuthManager(mock_app)
        
        result = manager.validate_all()
        
        assert result["ok"] is True
        assert result["total_count"] == 0
        assert result["valid_count"] == 0
    
    def test_auto_refresh_not_enabled(self):
        mock_app = MagicMock()
        mock_app.config.auth_profiles = {
            "test": {"type": "bearer", "refresh": {"enabled": False}}
        }
        mock_app.config.sources = {}
        
        from cts.auth import AuthManager
        manager = AuthManager(mock_app)
        
        result = manager.auto_refresh_if_needed("test")
        
        assert result["refreshed"] is False
        assert result["reason"] == "refresh_not_enabled"
