from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel

from src.domains.data_source.enums import (
    DataLatency,
    Granularity,
    IncrementalMode,
    ScrapingRuleStatus,
    TargetType,
)
from src.shared.mixins import TimestampMixin

if TYPE_CHECKING:
    from src.domains.data_source.models import DataSource


class ScrapingRule(SQLModel, TimestampMixin, table=True):
    __tablename__ = "scraping_rules"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=500)
    status: ScrapingRuleStatus = Field(default=ScrapingRuleStatus.ACTIVE)
    version: int = Field(default=1)

    data_source_id: int = Field(
        foreign_key="data_sources.id",
        index=True,
        ondelete="CASCADE",
    )

    target_type: TargetType = Field(default=TargetType.SHOP_OVERVIEW)
    granularity: Granularity = Field(default=Granularity.DAY)
    timezone: str = Field(default="Asia/Shanghai", max_length=50)
    time_range: dict | None = Field(default=None, sa_type=JSON)
    incremental_mode: IncrementalMode = Field(default=IncrementalMode.BY_DATE)
    backfill_last_n_days: int = Field(default=3)
    filters: dict | None = Field(default=None, sa_type=JSON)
    dimensions: list[str] | None = Field(default=None, sa_type=JSON)
    metrics: list[str] | None = Field(default=None, sa_type=JSON)
    dedupe_key: str | None = Field(default=None, max_length=255)
    rate_limit: dict | None = Field(default=None, sa_type=JSON)
    data_latency: DataLatency = Field(default=DataLatency.T_PLUS_1)
    top_n: int | None = Field(default=None)
    sort_by: str | None = Field(default=None, max_length=100)
    include_long_tail: bool = Field(default=False)
    session_level: bool = Field(default=False)
    last_executed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    last_execution_id: str | None = Field(default=None, max_length=100)
    extra_config: dict | None = Field(default=None, sa_type=JSON)

    data_source: "DataSource" = Relationship(back_populates="scraping_rules")
