from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    namespace: str
    resource_key: str
    resource_date: date
    recipe_id: int
    output: dict[str, Any]
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentResultListResponse(BaseModel):
    items: list[AgentResultResponse]
    total: int
    page: int
    size: int
