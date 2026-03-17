from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
)


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
