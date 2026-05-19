from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureType(str, Enum):
    LOCATOR_NOT_FOUND = "locator_not_found"
    OBSERVATION_EMPTY = "observation_empty"
    PARSE_FAILED = "parse_failed"
    ASSERTION_FAILED = "assertion_failed"
    TIMEOUT = "timeout"
    AUTH_REQUIRED = "auth_required"
    ACCESS_DENIED = "access_denied"
    SUBJECT_CONTEXT_MISMATCH = "subject_context_mismatch"
    URL_NOT_ALLOWED = "url_not_allowed"
    DANGEROUS_PAGE = "dangerous_page"
    SECURITY_POLICY_VIOLATION = "security_policy_violation"
    DRIVER_CRASHED = "driver_crashed"
    RECIPE_SCHEMA_INVALID = "recipe_schema_invalid"
    UNKNOWN = "unknown"


_FAILURE_ALIASES: dict[FailureType, set[str]] = {
    FailureType.LOCATOR_NOT_FOUND: {
        "locator_not_found",
        "locator_resolution_failed",
        "locator_failed",
    },
    FailureType.OBSERVATION_EMPTY: {"observation_empty", "empty_result", "empty_value"},
    FailureType.PARSE_FAILED: {"parse_failed", "value_parse_failed"},
    FailureType.ASSERTION_FAILED: {"assertion_failed"},
    FailureType.TIMEOUT: {"timeout", "result_not_ready"},
    FailureType.AUTH_REQUIRED: {"auth_required", "login_expired"},
    FailureType.ACCESS_DENIED: {"access_denied", "permission_denied"},
    FailureType.SUBJECT_CONTEXT_MISMATCH: {"subject_context_mismatch"},
    FailureType.URL_NOT_ALLOWED: {"url_not_allowed"},
    FailureType.DANGEROUS_PAGE: {"dangerous_page"},
    FailureType.SECURITY_POLICY_VIOLATION: {
        "security_policy_violation",
        "security_violation",
    },
    FailureType.DRIVER_CRASHED: {"driver_crashed", "browser_error"},
    FailureType.RECIPE_SCHEMA_INVALID: {"recipe_schema_invalid"},
}

_RECOVERABLE_FAILURE_TYPES = {
    FailureType.LOCATOR_NOT_FOUND,
    FailureType.OBSERVATION_EMPTY,
    FailureType.PARSE_FAILED,
    FailureType.ASSERTION_FAILED,
    FailureType.TIMEOUT,
}


@dataclass(slots=True)
class FailureClassification:
    failure_type: FailureType
    recoverable: bool
    reason: str
    failed_targets: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class FailureClassifier:
    def classify(self, failure: dict[str, Any] | None) -> FailureClassification:
        payload = dict(failure or {})
        failure_type = self._resolve_failure_type(payload)
        failed_targets = self._collect_targets(payload)
        reasons = self._collect_reasons(payload)
        recoverable = (
            failure_type in _RECOVERABLE_FAILURE_TYPES
            and bool(failed_targets)
            and all(
                self._is_observation_locator_target(target) for target in failed_targets
            )
        )
        reason = reasons[0] if reasons else failure_type.value
        return FailureClassification(
            failure_type=failure_type,
            recoverable=recoverable,
            reason=reason,
            failed_targets=failed_targets,
            failure_reasons=reasons,
            raw=payload,
        )

    def _resolve_failure_type(self, failure: dict[str, Any]) -> FailureType:
        candidates = (
            failure.get("type"),
            failure.get("code"),
            failure.get("failure_type"),
        )
        for candidate in candidates:
            normalized = self._normalize_value(candidate)
            if not normalized:
                continue
            for failure_type, aliases in _FAILURE_ALIASES.items():
                if normalized in aliases:
                    return failure_type
        return FailureType.UNKNOWN

    def _collect_targets(self, failure: dict[str, Any]) -> list[str]:
        raw_targets = failure.get("failed_targets")
        targets: list[str] = []
        if isinstance(raw_targets, list):
            targets.extend(self._normalize_target(item) for item in raw_targets if item)
        elif isinstance(raw_targets, str) and raw_targets:
            targets.append(self._normalize_target(raw_targets))
        observation_id = failure.get("observation_id")
        if observation_id:
            targets.append(f"/observations/{observation_id}/locator")
        target = failure.get("target")
        if isinstance(target, str) and target:
            targets.append(self._normalize_target(target))
        deduped: list[str] = []
        for item in targets:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    def _collect_reasons(self, failure: dict[str, Any]) -> list[str]:
        reasons = failure.get("failure_reasons")
        if isinstance(reasons, list):
            return [str(item) for item in reasons if item]
        reason = failure.get("reason") or failure.get("message")
        if reason:
            return [str(reason)]
        return []

    def _normalize_value(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip().lower().replace(" ", "_")

    def _normalize_target(self, value: str) -> str:
        normalized = value.strip()
        if normalized.startswith("/observations/") and normalized.endswith("/locator"):
            return normalized
        if (
            normalized.startswith("/observations/")
            and "/" not in normalized[len("/observations/") :]
        ):
            return f"{normalized}/locator"
        if normalized.startswith("observations."):
            observation_id = normalized.split(".", 2)[1]
            return f"/observations/{observation_id}/locator"
        if "/" not in normalized:
            return f"/observations/{normalized}/locator"
        return normalized

    def _is_observation_locator_target(self, target: str) -> bool:
        return target.startswith("/observations/") and target.endswith("/locator")
