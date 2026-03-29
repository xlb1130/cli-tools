from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
from subprocess import TimeoutExpired
from typing import Any, Dict, List, Optional

import httpx
import yaml

from cts.providers.base import ProviderError


class CTSStructuredError(RuntimeError):
    error_type = "ExecutionError"
    error_code = "execution_error"
    default_exit_code = 9
    retryable = False
    user_fixable = False

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        exit_code: Optional[int] = None,
        retryable: Optional[bool] = None,
        user_fixable: Optional[bool] = None,
        suggestions: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.error_code
        self.exit_code = exit_code or self.default_exit_code
        self.retryable = self.retryable if retryable is None else retryable
        self.user_fixable = self.user_fixable if user_fixable is None else user_fixable
        self.suggestions = list(suggestions or [])
        self.details = dict(details or {})


class ConfigError(CTSStructuredError):
    error_type = "ConfigError"
    error_code = "invalid_config"
    default_exit_code = 2
    user_fixable = True


class RegistryError(CTSStructuredError):
    error_type = "RegistryError"
    error_code = "registry_error"
    default_exit_code = 2
    user_fixable = True


class ValidationError(CTSStructuredError):
    error_type = "ValidationError"
    error_code = "invalid_input"
    default_exit_code = 3
    user_fixable = True


class AuthError(CTSStructuredError):
    error_type = "AuthError"
    error_code = "auth_error"
    default_exit_code = 4
    user_fixable = True


class PolicyError(CTSStructuredError):
    error_type = "PolicyError"
    error_code = "policy_blocked"
    default_exit_code = 5
    user_fixable = True


class TimeoutError(CTSStructuredError):
    error_type = "TimeoutError"
    error_code = "timeout"
    default_exit_code = 7
    retryable = True


@dataclass
class ErrorClassification:
    type: str
    code: str
    exit_code: int
    retryable: bool
    user_fixable: bool
    details: Dict[str, Any]
    suggestions: List[str]


def classify_exception(exc: Exception, stage: str) -> ErrorClassification:
    if stage in {"config_load", "config_lint"} and isinstance(exc, (ValueError, FileNotFoundError, JSONDecodeError, yaml.YAMLError)):
        return ErrorClassification(
            type="ConfigError",
            code="invalid_config",
            exit_code=2,
            retryable=False,
            user_fixable=True,
            details={},
            suggestions=[
                "检查配置文件路径、YAML/JSON 语法以及 imports 配置。",
                "可以先执行 `cts config lint --format json` 查看结构化结果。",
            ],
        )

    if isinstance(exc, CTSStructuredError):
        return ErrorClassification(
            type=exc.error_type,
            code=exc.code,
            exit_code=exc.exit_code,
            retryable=exc.retryable,
            user_fixable=exc.user_fixable,
            details=dict(exc.details),
            suggestions=list(exc.suggestions or _default_suggestions(exc, stage)),
        )

    if isinstance(exc, JSONDecodeError):
        details = {"line": exc.lineno, "column": exc.colno}
        return ErrorClassification(
            type="ValidationError",
            code="invalid_json_input",
            exit_code=3,
            retryable=False,
            user_fixable=True,
            details=details,
            suggestions=[
                "检查 `--input-json` 或 `--input-file` 是否为合法 JSON。",
                "也可以改用显式参数传值后再执行。",
            ],
        )

    if isinstance(exc, (TimeoutExpired, httpx.TimeoutException)):
        return ErrorClassification(
            type="TimeoutError",
            code="timeout",
            exit_code=7,
            retryable=True,
            user_fixable=False,
            details={},
            suggestions=[
                "稍后重试，或提高 source/mount 的 timeout 配置。",
                "如果是上游服务慢，先用 `cts explain` 确认最终请求。",
            ],
        )

    if isinstance(exc, ProviderError):
        message = str(exc)
        if message.startswith("input validation failed:"):
            return ErrorClassification(
                type="ValidationError",
                code="invalid_input",
                exit_code=3,
                retryable=False,
                user_fixable=True,
                details={},
                suggestions=[
                    "检查必填参数、类型和枚举值是否满足 schema。",
                    "先执行 `cts explain <mount-id> --format json` 查看标准化请求。",
                ],
            )
        return ErrorClassification(
            type="ProviderError",
            code="provider_error",
            exit_code=6,
            retryable=False,
            user_fixable=False,
            details={},
            suggestions=[
                "检查 source/provider 配置是否完整。",
                "先执行 `cts source test <source-name>` 或 `cts doctor --format json` 排查 provider 状态。",
            ],
        )

    return ErrorClassification(
        type=exc.__class__.__name__,
        code="internal_error",
        exit_code=9,
        retryable=False,
        user_fixable=False,
        details={},
        suggestions=_default_suggestions(exc, stage),
    )


def exit_code_for_exception(exc: Exception, stage: str) -> int:
    return classify_exception(exc, stage).exit_code


def _default_suggestions(exc: Exception, stage: str) -> List[str]:
    if stage == "config_load":
        return ["检查配置文件是否存在且格式正确。"]
    if stage == "config_lint":
        return ["修复配置后重新执行 `cts config lint`。"]
    if stage in {"invoke", "explain"}:
        return ["查看结构化错误详情并结合 `cts doctor` 或 `cts inspect` 继续排查。"]
    if stage.startswith("inspect") or stage.startswith("show"):
        return ["检查资源 id/name 是否正确，可先执行 list 命令确认。"]
    return ["查看结构化错误详情进一步排查。"]
