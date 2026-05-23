from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, SQLModel

from src.shared.mixins import TimestampMixin


class AgentCollectionResult(SQLModel, TimestampMixin, table=True):
    __tablename__ = "agent_collection_results"
    __table_args__ = (
        UniqueConstraint(
            "namespace",
            "resource_key",
            "resource_date",
            name="ux_agent_collection_result",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    namespace: str = Field(max_length=100, index=True)
    resource_key: str = Field(max_length=200, index=True)
    resource_date: date = Field(index=True)
    recipe_id: int = Field(foreign_key="agent_recipes.id")
    output: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    status: str = Field(default="success", max_length=20)
    error_message: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text(), nullable=True),
    )
