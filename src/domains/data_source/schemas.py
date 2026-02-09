from datetime import datetime
from typing import Any

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
    TargetType,
)


def validate_cron(value: str | None) -> str | None:
    if value is None:
        return None
    if not croniter.is_valid(value):
        raise ValueError("Invalid cron expression")
    return value


class DataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: DataSourceType
    config: dict[str, Any] = Field(default_factory=dict)
    status: DataSourceStatus = DataSourceStatus.ACTIVE
    description: str | None = Field(None, max_length=500)


class DataSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    status: DataSourceStatus | None = None
    description: str | None = Field(None, max_length=500)


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: DataSourceType
    config: dict[str, Any]
    status: DataSourceStatus
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class ScrapingRuleCreate(BaseModel):
    data_source_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=100)
    target_type: TargetType
    config: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = Field(None, max_length=100)
    is_active: bool = True
    description: str | None = Field(None, max_length=500)

    @field_validator("schedule", mode="before")
    @classmethod
    def validate_schedule(cls, v: str | None) -> str | None:
        return validate_cron(v)


class ScrapingRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    schedule: str | None = Field(None, max_length=100)
    is_active: bool | None = None
    description: str | None = Field(None, max_length=500)

    @field_validator("schedule", mode="before")
    @classmethod
    def validate_schedule(cls, v: str | None) -> str | None:
        return validate_cron(v)


class ScrapingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    data_source_id: int
    name: str
    target_type: TargetType
    config: dict[str, Any]
    schedule: str | None = None
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class ScrapingRuleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    data_source_id: int
    name: str
    target_type: TargetType
    config: dict[str, Any]
    schedule: str | None = None
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    data_source_name: str | None = None


class ScrapingRuleListResponse(BaseModel):
    items: list[ScrapingRuleListItem]
    total: int
    page: int
    size: int
    pages: int
