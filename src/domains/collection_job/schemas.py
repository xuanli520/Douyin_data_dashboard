from __future__ import annotations

from datetime import datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.task.enums import TaskType
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class ScheduleConfig(BaseModel):
    cron: str
    timezone: str = "Asia/Shanghai"
    kwargs: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def _split_cron_fields(
        cls,
        value: str,
        *,
        normalize_question_mark: bool = False,
    ) -> tuple[str, list[str]]:
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
        if not normalize_question_mark:
            return cron, fields

        normalized_fields = list(fields)
        day_index = 2 if len(fields) == 5 else 3
        day_of_week_index = 4 if len(fields) == 5 else 5
        for index, field in enumerate(normalized_fields):
            if field != "?":
                continue
            if index not in {day_index, day_of_week_index}:
                raise BusinessException(
                    ErrorCode.COLLECTION_JOB_INVALID_CRON,
                    "invalid cron expression",
                )
            normalized_fields[index] = "*"
        return cron, normalized_fields

    @classmethod
    def _build_aps_job_kwargs(
        cls,
        fields: list[str],
        *,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        if len(fields) == 5:
            minute, hour, day, month, day_of_week = fields
            job_kwargs: dict[str, Any] = {
                "minute": minute,
                "hour": hour,
                "day": day,
                "month": month,
                "day_of_week": day_of_week,
            }
        elif len(fields) == 6:
            second, minute, hour, day, month, day_of_week = fields
            job_kwargs = {
                "second": second,
                "minute": minute,
                "hour": hour,
                "day": day,
                "month": month,
                "day_of_week": day_of_week,
            }
        else:
            raise BusinessException(
                ErrorCode.COLLECTION_JOB_INVALID_CRON,
                "cron must contain 5 or 6 fields",
            )
        if timezone is not None:
            job_kwargs["timezone"] = timezone
        return job_kwargs

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        cron, fields = cls._split_cron_fields(value, normalize_question_mark=True)
        try:
            CronTrigger(**cls._build_aps_job_kwargs(fields))
        except ValueError as exc:
            raise BusinessException(
                ErrorCode.COLLECTION_JOB_INVALID_CRON,
                "invalid cron expression",
            ) from exc
        return cron

    def to_aps_job_kwargs(self) -> dict[str, Any]:
        _, parts = self._split_cron_fields(self.cron, normalize_question_mark=True)
        return {
            "trigger": "cron",
            **self._build_aps_job_kwargs(parts, timezone=self.timezone),
        }


class CollectionJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    task_type: TaskType
    data_source_id: int = Field(..., gt=0)
    rule_id: int = Field(..., gt=0)
    schedule: ScheduleConfig
    status: CollectionJobStatus = CollectionJobStatus.ACTIVE


class CollectionJobUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    schedule: ScheduleConfig | None = None
    status: CollectionJobStatus | None = None


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
