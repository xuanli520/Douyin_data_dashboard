from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataSourceType(StrEnum):
    DOUYIN_API = "douyin_api"
    FILE_UPLOAD = "file_upload"
    DATABASE = "database"
    WEBHOOK = "webhook"


class DataSourceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class ScrapingRuleType(StrEnum):
    ORDERS = "orders"
    PRODUCTS = "products"
    USERS = "users"
    COMMENTS = "comments"


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
    data_source_id: int
    name: str = Field(..., min_length=1, max_length=100)
    rule_type: ScrapingRuleType
    config: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = Field(None, max_length=100)
    is_active: bool = True
    description: str | None = Field(None, max_length=500)


class ScrapingRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    schedule: str | None = Field(None, max_length=100)
    is_active: bool | None = None
    description: str | None = Field(None, max_length=500)


class ScrapingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    data_source_id: int
    name: str
    rule_type: ScrapingRuleType
    config: dict[str, Any]
    schedule: str | None = None
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime
