"""Compatibility checking for CTS configuration, providers, and versions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from cts import __version__


class CompatibilityLevel(str, Enum):
    """Compatibility check result level."""
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class CompatibilityCategory(str, Enum):
    """Category of compatibility check."""
    CONFIG_VERSION = "config_version"
    CTS_VERSION = "cts_version"
    PROVIDER_VERSION = "provider_version"
    BINARY_VERSION = "binary_version"
    SCHEMA_VERSION = "schema_version"
    CACHE_VERSION = "cache_version"


@dataclass
class CompatibilityIssue:
    """A single compatibility issue."""
    category: CompatibilityCategory
    level: CompatibilityLevel
    message: str
    object_type: Optional[str] = None
    object_name: Optional[str] = None
    current_version: Optional[str] = None
    required_version: Optional[str] = None
    tested_range: Optional[str] = None
    suggestion: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompatibilityReport:
    """Full compatibility check report."""
    ok: bool
    issues: List[CompatibilityIssue] = field(default_factory=list)
    
    @property
    def errors(self) -> List[CompatibilityIssue]:
        return [i for i in self.issues if i.level == CompatibilityLevel.ERROR]
    
    @property
    def warnings(self) -> List[CompatibilityIssue]:
        return [i for i in self.issues if i.level == CompatibilityLevel.WARNING]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [
                {
                    "category": issue.category.value,
                    "level": issue.level.value,
                    "message": issue.message,
                    "object_type": issue.object_type,
                    "object_name": issue.object_name,
                    "current_version": issue.current_version,
                    "required_version": issue.required_version,
                    "tested_range": issue.tested_range,
                    "suggestion": issue.suggestion,
                }
                for issue in self.issues
            ],
        }


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse a version string into a tuple of integers."""
    # Remove leading 'v' if present
    version_str = version_str.lstrip("v")
    # Extract numeric parts
    parts = re.findall(r"\d+", version_str)
    return tuple(int(p) for p in parts) if parts else (0,)


def compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings. Returns -1, 0, or 1."""
    p1 = parse_version(v1)
    p2 = parse_version(v2)
    if p1 < p2:
        return -1
    elif p1 > p2:
        return 1
    return 0


def version_in_range(version: str, range_spec: str) -> bool:
    """Check if version is within a version range specification.
    
    Supports:
    - ">=1.0,<2.0" - between 1.0 and 2.0
    - ">=1.0" - at least 1.0
    - "<2.0" - less than 2.0
    - "==1.0" - exactly 1.0
    """
    if not range_spec:
        return True
    
    version_tuple = parse_version(version)
    
    # Split by comma for multiple conditions
    conditions = [c.strip() for c in range_spec.split(",")]
    
    for condition in conditions:
        condition = condition.strip()
        if not condition:
            continue
        
        # Parse operator and version
        match = re.match(r"^(>=|<=|>|<|==|!=)?(.+)$", condition)
        if not match:
            continue
        
        op = match.group(1) or "=="
        spec_version = match.group(2).strip()
        spec_tuple = parse_version(spec_version)
        
        if op == ">=":
            if version_tuple < spec_tuple:
                return False
        elif op == "<=":
            if version_tuple > spec_tuple:
                return False
        elif op == ">":
            if version_tuple <= spec_tuple:
                return False
        elif op == "<":
            if version_tuple >= spec_tuple:
                return False
        elif op == "==":
            if version_tuple != spec_tuple:
                return False
        elif op == "!=":
            if version_tuple == spec_tuple:
                return False
    
    return True


class CompatibilityChecker:
    """Check compatibility across CTS configuration and providers."""
    
    CURRENT_CONFIG_VERSION = 2
    MIN_SUPPORTED_CONFIG_VERSION = 1
    MAX_SUPPORTED_CONFIG_VERSION = 2
    
    def __init__(self, app: Any):
        self.app = app
        self._issues: List[CompatibilityIssue] = []
    
    def check_all(self) -> CompatibilityReport:
        """Run all compatibility checks."""
        self._issues = []
        
        self._check_config_version()
        self._check_cts_version()
        self._check_source_versions()
        self._check_provider_versions()
        
        return CompatibilityReport(
            ok=len(self.errors) == 0,
            issues=self._issues,
        )
    
    @property
    def errors(self) -> List[CompatibilityIssue]:
        return [i for i in self._issues if i.level == CompatibilityLevel.ERROR]
    
    @property
    def warnings(self) -> List[CompatibilityIssue]:
        return [i for i in self._issues if i.level == CompatibilityLevel.WARNING]
    
    def _add_issue(self, issue: CompatibilityIssue) -> None:
        self._issues.append(issue)
    
    def _check_config_version(self) -> None:
        """Check configuration version compatibility."""
        config_version = self.app.config.version
        
        if config_version < self.MIN_SUPPORTED_CONFIG_VERSION:
            self._add_issue(CompatibilityIssue(
                category=CompatibilityCategory.CONFIG_VERSION,
                level=CompatibilityLevel.ERROR,
                message=f"Config version {config_version} is too old. Minimum supported: {self.MIN_SUPPORTED_CONFIG_VERSION}",
                object_type="config",
                current_version=str(config_version),
                required_version=str(self.MIN_SUPPORTED_CONFIG_VERSION),
                suggestion="Run 'cts manage config migrate' to upgrade the configuration.",
            ))
        elif config_version > self.MAX_SUPPORTED_CONFIG_VERSION:
            self._add_issue(CompatibilityIssue(
                category=CompatibilityCategory.CONFIG_VERSION,
                level=CompatibilityLevel.ERROR,
                message=f"Config version {config_version} is not supported. Maximum supported: {self.MAX_SUPPORTED_CONFIG_VERSION}",
                object_type="config",
                current_version=str(config_version),
                required_version=str(self.MAX_SUPPORTED_CONFIG_VERSION),
                suggestion="Upgrade CTS to a version that supports this config format.",
            ))
    
    def _check_cts_version(self) -> None:
        """Check CTS version against compatibility requirements."""
        compatibility = self.app.config.compatibility or {}
        min_cts_version = compatibility.get("min_cts_version")
        
        if min_cts_version:
            current = __version__
            if compare_versions(current, min_cts_version) < 0:
                self._add_issue(CompatibilityIssue(
                    category=CompatibilityCategory.CTS_VERSION,
                    level=CompatibilityLevel.ERROR,
                    message=f"CTS version {current} is older than required {min_cts_version}",
                    object_type="cts",
                    current_version=current,
                    required_version=min_cts_version,
                    suggestion="Upgrade CTS to meet the minimum version requirement.",
                ))
    
    def _check_source_versions(self) -> None:
        """Check source-level version compatibility."""
        for source_name, source_config in self.app.config.sources.items():
            compatibility = getattr(source_config, "compatibility", None)
            if not compatibility:
                compatibility = {}
            if hasattr(compatibility, "model_dump"):
                compatibility = compatibility.model_dump()
            
            # Check minimum binary version for CLI sources
            min_binary = compatibility.get("min_binary_version")
            if min_binary and source_config.type in ("cli", "shell"):
                # Try to get actual binary version
                actual_version = self._get_cli_version(source_name, source_config)
                if actual_version:
                    if compare_versions(actual_version, min_binary) < 0:
                        self._add_issue(CompatibilityIssue(
                            category=CompatibilityCategory.BINARY_VERSION,
                            level=CompatibilityLevel.ERROR,
                            message=f"Binary for source '{source_name}' is version {actual_version}, minimum required: {min_binary}",
                            object_type="source",
                            object_name=source_name,
                            current_version=actual_version,
                            required_version=min_binary,
                            suggestion=f"Upgrade the binary for '{source_name}' to meet the minimum version.",
                        ))
            
            # Check tested range
            tested_range = compatibility.get("tested_range")
            if tested_range and source_config.type in ("cli", "shell"):
                actual_version = self._get_cli_version(source_name, source_config)
                if actual_version:
                    if not version_in_range(actual_version, tested_range):
                        level = CompatibilityLevel.WARNING
                        if compatibility.get("break_on_major_upgrade"):
                            level = CompatibilityLevel.ERROR
                        self._add_issue(CompatibilityIssue(
                            category=CompatibilityCategory.BINARY_VERSION,
                            level=level,
                            message=f"Binary for source '{source_name}' version {actual_version} is outside tested range {tested_range}",
                            object_type="source",
                            object_name=source_name,
                            current_version=actual_version,
                            tested_range=tested_range,
                            suggestion="Consider pinning the binary version or updating the tested range.",
                        ))
    
    def _check_provider_versions(self) -> None:
        """Check provider-level version compatibility."""
        # Check for provider SDK version compatibility
        # This would be extended by plugins to check their own compatibility
        pass
    
    def _get_cli_version(self, source_name: str, source_config: Any) -> Optional[str]:
        """Attempt to get the version of a CLI binary."""
        import subprocess
        import shutil
        
        executable = source_config.executable
        if not executable:
            return None
        
        # Find the executable
        binary = shutil.which(executable)
        if not binary:
            return None
        
        # Try common version flags
        for flag in ["--version", "-V", "version"]:
            try:
                result = subprocess.run(
                    [binary, flag],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Extract version from output
                    output = result.stdout.strip().split("\n")[0]
                    # Try to find version pattern
                    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", output)
                    if match:
                        return match.group(1)
            except Exception:
                pass
        
        return None


def check_compatibility(app: Any) -> CompatibilityReport:
    """Run compatibility check on an app instance."""
    checker = CompatibilityChecker(app)
    return checker.check_all()


def doctor_compatibility(app: Any) -> Dict[str, Any]:
    """Run compatibility check as part of doctor command."""
    report = check_compatibility(app)
    return {
        "ok": report.ok,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
        "issues": [
            {
                "level": issue.level.value,
                "category": issue.category.value,
                "message": issue.message,
                "object_name": issue.object_name,
                "suggestion": issue.suggestion,
            }
            for issue in report.issues
        ],
    }
