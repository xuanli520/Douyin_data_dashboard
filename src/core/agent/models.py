from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.agent.exceptions import RecipeValidationError

ActionName = Literal[
    "goto",
    "back",
    "reload",
    "click",
    "fill",
    "select",
    "scroll_down",
    "scroll_up",
    "scroll_to_element",
    "wait_visible",
    "wait_network_idle",
    "extract_table",
    "extract_list",
    "extract_text",
]
ObservationKind = Literal["text", "table", "list", "attribute", "url", "title"]
AssertionKind = Literal[
    "exists",
    "not_empty",
    "equals",
    "contains",
    "matches",
    "url_allowed",
]
AssertionSeverity = Literal["error", "warning"]


class LocatorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["css", "xpath", "text", "role"]
    value: str

    @model_validator(mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> Any:
        if isinstance(value, str):
            locator_value = value.strip()
            return {
                "kind": _infer_locator_kind(locator_value),
                "value": _strip_locator_prefix(locator_value),
            }
        if isinstance(value, dict):
            normalized = dict(value)
            if "type" in normalized and "kind" not in normalized:
                normalized["kind"] = normalized.pop("type")
            if "selector" in normalized:
                selector = normalized.pop("selector")
                if "value" not in normalized:
                    normalized["value"] = selector
            if "locator" in normalized:
                locator = normalized.pop("locator")
                if "value" not in normalized:
                    normalized["value"] = locator
            raw_value = normalized.get("value")
            if isinstance(raw_value, str):
                if "kind" not in normalized:
                    normalized["kind"] = _infer_locator_kind(raw_value)
                normalized["value"] = _strip_locator_prefix(raw_value)
            return normalized
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("locator value cannot be empty")
        if len(normalized) > 500:
            raise ValueError("locator value is too long")
        return normalized


def _infer_locator_kind(value: str) -> str:
    text = value.strip()
    lowered = text.lower()
    if lowered.startswith("xpath="):
        return "xpath"
    if lowered.startswith("css="):
        return "css"
    if lowered.startswith("text="):
        return "text"
    if text.startswith("//") or text.startswith("(//"):
        return "xpath"
    return "css"


def _strip_locator_prefix(value: str) -> str:
    text = value.strip()
    lowered = text.lower()
    for prefix in ("xpath=", "css=", "text="):
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


class Entrypoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("entrypoint url cannot be empty")
        return normalized


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    action: ActionName
    target: LocatorSpec | None = None
    value: str | None = None
    timeout_seconds: float | None = None
    save_as: str | None = None
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("step id cannot be empty")
        return normalized


class ObservationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ObservationKind
    locator: LocatorSpec | None = None
    parser: str | None = None
    required: bool = False
    max_items: int | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("observation id cannot be empty")
        return normalized


class AssertionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: AssertionKind
    source: str
    expected: Any | None = None
    severity: AssertionSeverity = "error"

    @field_validator("id", "source")
    @classmethod
    def validate_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("assertion fields cannot be empty")
        return normalized


class RecoveryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    minimum_confidence: float = 0.7
    max_attempts: int = 1


class SecurityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_origins: list[str] = Field(default_factory=list)
    blocked_patterns: list[str] = Field(default_factory=list)
    snapshot_max_chars: int = 30000


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str
    key: str
    version: int = 1
    entrypoint: Entrypoint
    steps: list[Step] = Field(default_factory=list)
    observations: dict[str, ObservationSpec] = Field(default_factory=dict)
    assertions: list[AssertionSpec] = Field(default_factory=list)
    recovery_policy: RecoveryPolicy = Field(default_factory=RecoveryPolicy)
    security_policy: SecurityPolicy = Field(default_factory=SecurityPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("namespace", "key")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("recipe identifier cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_graph(self) -> "Recipe":
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise RecipeValidationError("step ids must be unique")
        known_step_ids = set(step_ids)
        for step in self.steps:
            missing = set(step.depends_on) - known_step_ids
            if missing:
                raise RecipeValidationError(
                    f"step {step.id} depends on unknown steps: {sorted(missing)}"
                )
        observation_ids = set(self.observations)
        if observation_ids != {item.id for item in self.observations.values()}:
            raise RecipeValidationError("observation keys must match observation ids")
        for assertion in self.assertions:
            if assertion.source not in observation_ids:
                raise RecipeValidationError(
                    f"assertion {assertion.id} references unknown source"
                )
        return self


class Failure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    message: str
    step_id: str | None = None
    observation_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    recoverable: bool = False


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    kind: str


class RunContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    storage_state_path: str | None = None
    headed: bool = False


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["succeeded", "failed", "recovered", "degraded"]
    output: dict[str, Any] = Field(default_factory=dict)
    failure: Failure | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"succeeded", "recovered"}
