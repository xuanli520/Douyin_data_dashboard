from datetime import date
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from src.shared.mixins import TimestampMixin


class ShopDashboardScore(SQLModel, TimestampMixin, table=True):
    __tablename__ = "shop_dashboard_scores"
    __table_args__ = (
        UniqueConstraint("shop_id", "metric_date", name="uq_shop_dashboard_score_day"),
    )

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(max_length=50, index=True)
    metric_date: date = Field(index=True)
    total_score: float
    product_score: float
    logistics_score: float
    service_score: float
    source: str = Field(max_length=20)


class ShopDashboardReview(SQLModel, TimestampMixin, table=True):
    __tablename__ = "shop_dashboard_reviews"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "metric_date",
            "review_id",
            name="uq_shop_dashboard_review_day",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(max_length=50, index=True)
    metric_date: date = Field(index=True)
    review_id: str = Field(max_length=100)
    content: str
    is_replied: bool = False
    source: str = Field(max_length=20)


class ShopDashboardViolation(SQLModel, TimestampMixin, table=True):
    __tablename__ = "shop_dashboard_violations"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "metric_date",
            "violation_id",
            name="uq_shop_dashboard_violation_day",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(max_length=50, index=True)
    metric_date: date = Field(index=True)
    violation_id: str = Field(max_length=100)
    violation_type: str = Field(max_length=50)
    description: str | None = Field(default=None, max_length=1000)
    score: int = 0
    source: str = Field(max_length=20)


class ShopDashboardColdMetric(SQLModel, TimestampMixin, table=True):
    __tablename__ = "shop_dashboard_cold_metrics"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "metric_date",
            "reason",
            name="uq_shop_dashboard_cold_metric_day_reason",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(max_length=50, index=True)
    metric_date: date = Field(index=True)
    reason: str = Field(max_length=50)
    violations_detail: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    arbitration_detail: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    dsr_trend: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    source: str = Field(max_length=20, default="llm")
