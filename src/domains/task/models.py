from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, JSON
from sqlmodel import Field, SQLModel

from src.domains.task.enums import (
    TaskDefinitionStatus,
    TaskExecutionStatus,
    TaskTriggerMode,
    TaskType,
)
from src.shared.mixins import TimestampMixin


class TaskDefinition(SQLModel, TimestampMixin, table=True):
    __tablename__ = "task_definitions"
    __table_args__ = (
        Index("idx_task_definitions_task_type_status", "task_type", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, index=True)
    task_type: TaskType = Field(index=True)
    status: TaskDefinitionStatus = Field(
        default=TaskDefinitionStatus.ACTIVE,
        index=True,
    )
    config: dict | None = Field(default=None, sa_type=JSON)
    schedule: dict | None = Field(default=None, sa_type=JSON)
    created_by_id: int | None = Field(default=None)
    updated_by_id: int | None = Field(default=None)


class TaskExecution(SQLModel, TimestampMixin, table=True):
    __tablename__ = "task_executions"
    __table_args__ = (
        Index("idx_task_executions_task_id_created_at", "task_id", "created_at"),
        Index("ux_task_executions_queue_task_id", "queue_task_id", unique=True),
        Index("ux_task_executions_idempotency_key", "idempotency_key", unique=True),
    )

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(
        foreign_key="task_definitions.id",
        index=True,
        ondelete="CASCADE",
    )
    queue_task_id: str | None = Field(default=None, max_length=100)
    idempotency_key: str | None = Field(default=None, max_length=160)
    status: TaskExecutionStatus = Field(default=TaskExecutionStatus.QUEUED, index=True)
    trigger_mode: TaskTriggerMode = Field(default=TaskTriggerMode.MANUAL)
    payload: dict | None = Field(default=None, sa_type=JSON)
    rule_version: int | None = Field(default=None)
    effective_config_snapshot: dict | None = Field(default=None, sa_type=JSON)
    started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    completed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    processed_rows: int = Field(default=0)
    error_message: str | None = Field(default=None, max_length=1000)
    triggered_by: int | None = Field(default=None)
