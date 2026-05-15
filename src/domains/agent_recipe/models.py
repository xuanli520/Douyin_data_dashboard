from typing import Any

from sqlalchemy import JSON, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from src.shared.mixins import TimestampMixin

AGENT_RECIPE_STATUS_ACTIVE = "active"
AGENT_RECIPE_STATUS_DEGRADED = "degraded"
AGENT_RECIPE_STATUS_DISABLED = "disabled"


class AgentRecipe(SQLModel, TimestampMixin, table=True):
    __tablename__ = "agent_recipes"
    __table_args__ = (
        UniqueConstraint(
            "namespace",
            "key",
            "version",
            name="ux_agent_recipes_namespace_key_version",
        ),
        Index(
            "ix_agent_recipes_namespace_key_status_version",
            "namespace",
            "key",
            "status",
            "version",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    namespace: str = Field(max_length=100, index=True)
    key: str = Field(max_length=200, index=True)
    version: int = Field(default=1, ge=1)
    status: str = Field(default=AGENT_RECIPE_STATUS_ACTIVE, max_length=20)

    entrypoint: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    steps: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    observations: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    assertions: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    recovery_policy: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    security_policy: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

