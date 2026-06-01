from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RecoveryPolicy:
    enabled: bool = False
    max_attempts: int = 1
    confidence_threshold: float = 0.7
    allow_observation_locator_replace: bool = True

    @classmethod
    def from_value(cls, value: Any = None) -> "RecoveryPolicy":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return cls()
        return cls(
            enabled=bool(value.get("enabled", False)),
            max_attempts=max(int(value.get("max_attempts", 1)), 1),
            confidence_threshold=float(value.get("confidence_threshold", 0.7)),
            allow_observation_locator_replace=bool(
                value.get(
                    "allow_observation_locator_replace",
                    value.get("allow_observation_patch", True),
                )
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RecipePatch:
    op: str
    path: str
    value: dict[str, Any]
    confidence: float | None = None

    @classmethod
    def from_value(cls, value: Any) -> "RecipePatch":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError("patch must be a mapping")
        locator = value.get("value")
        if not isinstance(locator, dict):
            raise TypeError("patch value must be a mapping")
        confidence = value.get("confidence")
        return cls(
            op=str(value.get("op", "")),
            path=str(value.get("path", "")),
            value=dict(locator),
            confidence=float(confidence) if confidence is not None else None,
        )


@dataclass(slots=True)
class RecoveryProposal:
    confidence: float
    reason: str
    patches: list[RecipePatch]
    expected_effect: str = ""
    recipe_id: str | int | None = None
    base_version: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: Any) -> "RecoveryProposal":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError("proposal must be a mapping")
        patches = [RecipePatch.from_value(item) for item in value.get("patches", [])]
        return cls(
            confidence=float(value.get("confidence", 0.0)),
            reason=str(value.get("reason", "")),
            patches=patches,
            expected_effect=str(value.get("expected_effect", "")),
            recipe_id=value.get("recipe_id"),
            base_version=(
                int(value["base_version"])
                if value.get("base_version") is not None
                else None
            ),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(slots=True)
class RecoveryRequest:
    recipe_id: str | int | None
    recipe_version: int | None
    failure_type: str
    failed_targets: list[str]
    failure_reasons: list[str]
    recipe_excerpt: dict[str, Any]
    observation_specs: dict[str, Any]
    security_policy: dict[str, Any]
    recovery_policy: dict[str, Any]
    current_url: str | None = None
    rendered_entrypoint_url: str | None = None
    snapshot_markdown: str | None = None
    dom_excerpt: str | None = None
    screenshot_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
