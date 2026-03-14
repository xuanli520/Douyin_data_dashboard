from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domains.data_source.enums import ScrapingRuleStatus, TargetType


class ScrapingRuleCreate(BaseModel):
    data_source_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=100)
    target_type: TargetType
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    description: str | None = Field(None, max_length=500)


class ScrapingRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict[str, Any] | None = None
    is_active: bool | None = None
    description: str | None = Field(None, max_length=500)


class ScrapingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    data_source_id: int
    name: str
    target_type: TargetType
    config: dict[str, Any]
    is_active: bool
    status: ScrapingRuleStatus
    version: int
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
    is_active: bool
    status: ScrapingRuleStatus
    version: int
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
