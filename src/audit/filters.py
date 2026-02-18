from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.audit.schemas import AuditAction, AuditResult
from src.exceptions import (
    AuditConflictActionFiltersException,
    AuditInvalidActionException,
    AuditInvalidResultException,
    AuditInvalidTimeRangeException,
)


class AuditLogFilters(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    action: AuditAction | None = None
    actions: list[AuditAction] | None = Field(default=None, max_length=50)
    result: AuditResult | None = None
    actor_id: int | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    ip: str | None = None
    request_id: str | None = None
    account_type: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)

    @staticmethod
    def _normalize_str(v: str) -> str | None:
        v = v.strip()
        return v or None

    @classmethod
    def _coerce_action(cls, v: str) -> AuditAction:
        try:
            return AuditAction(v)
        except ValueError:
            raise AuditInvalidActionException(v)

    @classmethod
    def _coerce_result(cls, v: str) -> AuditResult:
        try:
            return AuditResult(v)
        except ValueError:
            raise AuditInvalidResultException(v)

    @field_validator("action", mode="before")
    @classmethod
    def parse_action(cls, v):
        if isinstance(v, str):
            v = cls._normalize_str(v)
            if v is None:
                return None
            return cls._coerce_action(v)
        return v

    @field_validator("actions", mode="before")
    @classmethod
    def parse_actions(cls, v):
        if isinstance(v, str):
            items = [cls._normalize_str(item) for item in v.split(",")]
            items = [item for item in items if item]
            if not items:
                return None
            return [cls._coerce_action(item) for item in items]

        if isinstance(v, list):
            if not v:
                return None
            normalized: list[AuditAction] = []
            for idx, item in enumerate(v):
                if isinstance(item, str):
                    item = cls._normalize_str(item)
                    if item is None:
                        continue
                    normalized.append(cls._coerce_action(item))
                elif isinstance(item, AuditAction):
                    normalized.append(item)
                else:
                    raise ValueError(f"invalid actions[{idx}]: {item!r}")
            return normalized or None

        return v

    @field_validator("result", mode="before")
    @classmethod
    def parse_result(cls, v):
        if isinstance(v, str):
            v = cls._normalize_str(v)
            if v is None:
                return None
            return cls._coerce_result(v)
        return v

    @field_validator("account_type", mode="before")
    @classmethod
    def parse_account_type(cls, v):
        if isinstance(v, str):
            return cls._normalize_str(v)
        return v

    @model_validator(mode="after")
    def validate_all(self):
        if (
            self.occurred_from
            and self.occurred_to
            and self.occurred_from > self.occurred_to
        ):
            raise AuditInvalidTimeRangeException(
                occurred_from=str(self.occurred_from),
                occurred_to=str(self.occurred_to),
            )
        if self.action is not None and self.actions is not None:
            raise AuditConflictActionFiltersException()
        return self
