from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from src.shared.mixins import TimestampMixin


class ExperienceMetricDaily(SQLModel, TimestampMixin, table=True):
    __tablename__ = "experience_metric_daily"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "metric_date",
            "dimension",
            "metric_key",
            name="uq_experience_metric_daily_shop_day_dimension_metric",
        ),
        Index(
            "ix_experience_metric_daily_shop_metric_date",
            "shop_id",
            "metric_date",
        ),
        Index(
            "ix_experience_metric_daily_shop_dimension_metric_date",
            "shop_id",
            "dimension",
            "metric_date",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(max_length=50, index=True)
    metric_date: date = Field(index=True)
    dimension: str = Field(max_length=30, index=True)
    metric_key: str = Field(max_length=80, index=True)
    metric_score: float = Field(default=0.0)
    metric_value: float = Field(default=0.0)
    metric_unit: str = Field(default="pt", max_length=16)
    source_field: str = Field(default="", max_length=128)
    formula_expr: str | None = Field(default=None, max_length=255)
    is_penalty: bool = Field(default=False)
    deduct_points: float = Field(default=0.0)
    source: str = Field(default="collector", max_length=20)
    extra: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )


class ExperienceIssueDaily(SQLModel, TimestampMixin, table=True):
    __tablename__ = "experience_issue_daily"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "metric_date",
            "issue_key",
            name="uq_experience_issue_daily_shop_day_issue",
        ),
        Index(
            "ix_experience_issue_daily_shop_metric_date",
            "shop_id",
            "metric_date",
        ),
        Index(
            "ix_experience_issue_daily_shop_dimension_metric_date",
            "shop_id",
            "dimension",
            "metric_date",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(max_length=50, index=True)
    metric_date: date = Field(index=True)
    dimension: str = Field(max_length=30, index=True)
    issue_key: str = Field(max_length=100)
    issue_title: str = Field(max_length=200)
    status: str = Field(default="pending", max_length=30, index=True)
    owner: str = Field(default="", max_length=60)
    impact_score: float = Field(default=0.0)
    deduct_points: float = Field(default=0.0)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    deadline_at: datetime | None = None
    source: str = Field(default="collector", max_length=20)
    extra: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
