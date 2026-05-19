from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domains.agent_recipe.models import AGENT_RECIPE_STATUS_ACTIVE

AgentRecipeStatus = Literal["active", "degraded", "disabled"]


class AgentRecipePayload(BaseModel):
    entrypoint: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    observations: dict[str, Any] = Field(default_factory=dict)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    recovery_policy: dict[str, Any] = Field(default_factory=dict)
    security_policy: dict[str, Any] = Field(default_factory=dict)


class AgentRecipeCreate(AgentRecipePayload):
    namespace: str = Field(..., min_length=1, max_length=100)
    key: str = Field(..., min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    status: AgentRecipeStatus = AGENT_RECIPE_STATUS_ACTIVE


class AgentRecipeVersionCreate(AgentRecipePayload):
    namespace: str = Field(..., min_length=1, max_length=100)
    key: str = Field(..., min_length=1, max_length=200)
    expected_version: int = Field(..., ge=1)


class AgentRecipeMarkDegraded(BaseModel):
    recipe_id: int = Field(..., gt=0)
    expected_version: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1, max_length=500)


class AgentRecipeResponse(AgentRecipePayload):
    model_config = ConfigDict(from_attributes=True)

    id: int
    namespace: str
    key: str
    version: int
    status: AgentRecipeStatus
    created_at: datetime
    updated_at: datetime
