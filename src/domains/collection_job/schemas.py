from __future__ import annotations

from datetime import datetime
from typing import Any

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.task.enums import TaskType
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class ScheduleConfig(BaseModel):
    cron: str
    timezone: str = "Asia/Shanghai"
    kwargs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        cron = " ".join(value.split())
        if not cron:
            raise BusinessException(
                ErrorCode.COLLECTION_JOB_INVALID_CRON,
                "cron is required",
            )
        fields = cron.split(" ")
        if len(fields) not in (5, 6):
            raise BusinessException(
                ErrorCode.COLLECTION_JOB_INVALID_CRON,
                "cron must contain 5 or 6 fields",
            )
        if not croniter.is_valid(cron):
            raise BusinessException(
                ErrorCode.COLLECTION_JOB_INVALID_CRON,
                "invalid cron expression",
            )
        return cron

    def to_aps_job_kwargs(self) -> dict[str, Any]:
        parts = self.cron.split(" ")
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
            return {
                "trigger": "cron",
                "minute": minute,
                "hour": hour,
                "day": day,
                "month": month,
                "day_of_week": day_of_week,
                "timezone": self.timezone,
            }
        if len(parts) == 6:
            second, minute, hour, day, month, day_of_week = parts
            return {
                "trigger": "cron",
                "second": second,
                "minute": minute,
                "hour": hour,
                "day": day,
                "month": month,
                "day_of_week": day_of_week,
                "timezone": self.timezone,
            }
        raise BusinessException(
            ErrorCode.COLLECTION_JOB_INVALID_CRON,
            "cron must contain 5 or 6 fields",
        )


class CollectionJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    task_type: TaskType
    data_source_id: int = Field(..., gt=0)
    rule_id: int = Field(..., gt=0)
    schedule: ScheduleConfig
    status: CollectionJobStatus = CollectionJobStatus.ACTIVE


class CollectionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    task_type: TaskType
    data_source_id: int
    rule_id: int
    schedule: dict[str, Any]
    status: CollectionJobStatus
    created_at: datetime
    updated_at: datetime
