from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domains.task.enums import (
    TaskDefinitionStatus,
    TaskExecutionStatus,
    TaskTriggerMode,
    TaskType,
)


class TaskDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    task_type: TaskType
    config: dict[str, Any] = Field(default_factory=dict)
    schedule: dict[str, Any] | None = None
    status: TaskDefinitionStatus = TaskDefinitionStatus.ACTIVE


class TaskDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: TaskDefinitionStatus | None = None
    config: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None


class TaskDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    task_type: TaskType
    status: TaskDefinitionStatus
    config: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime
    updated_at: datetime


class TaskExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    queue_task_id: str | None = None
    status: TaskExecutionStatus
    trigger_mode: TaskTriggerMode
    payload: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processed_rows: int = 0
    error_message: str | None = None
    triggered_by: int | None = None
    created_at: datetime
    updated_at: datetime


class TaskExecutionCreate(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    trigger_mode: TaskTriggerMode = TaskTriggerMode.MANUAL
