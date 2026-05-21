from datetime import date

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from src.shared.mixins import TimestampMixin

UQ_SHOP_DASHBOARD_SCORE_DAY = "uq_shop_dashboard_score_day"


class ShopDashboardScore(SQLModel, TimestampMixin, table=True):
    __tablename__ = "shop_dashboard_scores"
    __table_args__ = (
        UniqueConstraint("shop_id", "metric_date", name=UQ_SHOP_DASHBOARD_SCORE_DAY),
    )

    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(max_length=50, index=True)
    shop_name: str | None = Field(default=None, max_length=200)
    metric_date: date = Field(index=True)
    total_score: float | None = None
    product_score: float | None = None
    logistics_score: float | None = None
    service_score: float | None = None
    bad_behavior_score: float | None = None
    source: str = Field(max_length=20)
    status: str = Field(default="success", max_length=20, index=True)
    reason: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)
