from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, field_serializer, model_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from sqlmodel import Field, SQLModel

from src.shared.mixins import now


class AuditAction(StrEnum):
    LOGIN = "login"
    LOGOUT = "logout"
    REFRESH = "refresh"
    REGISTER = "register"
    VERIFY_EMAIL = "verify_email"
    FORGOT_PASSWORD = "forgot_password"
    RESET_PASSWORD = "reset_password"
    PERMISSION_CHECK = "permission_check"
    ROLE_CHECK = "role_check"
    PROTECTED_RESOURCE_ACCESS = "protected_resource_access"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    DATA_SOURCE_BIND = "data_source_bind"
    DATA_SOURCE_UNBIND = "data_source_unbind"
    DATA_SOURCE_UPDATE = "data_source_update"
    DATA_SOURCE_SYNC = "data_source_sync"
    TASK_CREATE = "task_create"
    TASK_UPDATE = "task_update"
    TASK_ENABLE = "task_enable"
    TASK_DISABLE = "task_disable"
    TASK_RUN = "task_run"
    TASK_STOP = "task_stop"
    TASK_FAIL = "task_fail"


class AuditResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    GRANTED = "granted"
    DENIED = "denied"


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)

    id: int | None = Field(default=None, primary_key=True)
    occurred_at: datetime = Field(
        default_factory=now,
        sa_type=DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    request_id: str | None = Field(
        default=None,
        max_length=36,
        description="Request correlation ID - groups all audit logs from a single HTTP request",
    )
    actor_id: int | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), index=True),
    )
    action: AuditAction = Field(
        max_length=64,
        sa_column=Column(String(64), nullable=False, index=True),
    )
    resource_type: str | None = Field(default=None, max_length=64)
    resource_id: str | None = Field(default=None, sa_column=Column(Text))
    result: AuditResult = Field(
        max_length=32,
        sa_column=Column(String(32), nullable=False),
    )
    user_agent: str | None = Field(default=None, sa_column=Column(Text))
    ip: str | None = Field(default=None, max_length=45)
    extra: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    @field_serializer("action")
    def serialize_action(self, action: AuditAction) -> str:
        if isinstance(action, str):
            return action
        return action.value

    @field_serializer("result")
    def serialize_result(self, result: AuditResult) -> str:
        if isinstance(result, str):
            return result
        return result.value

    @model_validator(mode="before")
    @classmethod
    def parse_action_result(cls, data):
        if isinstance(data, dict):
            if isinstance(data.get("action"), str):
                data["action"] = AuditAction(data["action"])
            if isinstance(data.get("result"), str):
                data["result"] = AuditResult(data["result"])
        return data
