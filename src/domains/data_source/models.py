from datetime import datetime

from sqlalchemy import DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel

from src.shared.mixins import TimestampMixin
from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
    ScrapingRuleStatus,
    TargetType,
    Granularity,
    IncrementalMode,
    DataLatency,
)


class DataSource(SQLModel, TimestampMixin, table=True):
    __tablename__ = "data_sources"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, index=True)
    description: str | None = Field(default=None, max_length=500)
    source_type: DataSourceType = Field(default=DataSourceType.DOUYIN_SHOP)
    status: DataSourceStatus = Field(default=DataSourceStatus.ACTIVE)

    shop_id: str | None = Field(default=None, max_length=50, index=True)
    account_name: str | None = Field(default=None, max_length=100)
    cookies: str | None = Field(default=None)
    proxy: str | None = Field(default=None, max_length=255)

    api_key: str | None = Field(default=None, max_length=255)
    api_secret: str | None = Field(default=None, max_length=255)
    access_token: str | None = Field(default=None)
    refresh_token: str | None = Field(default=None)
    token_expires_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )

    rate_limit: int = Field(default=100)
    retry_count: int = Field(default=3)
    timeout: int = Field(default=30)
    extra_config: dict | None = Field(default=None, sa_type=JSON)

    last_used_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    last_error_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    last_error_msg: str | None = Field(default=None, max_length=500)

    created_by_id: int | None = Field(default=None, foreign_key="users.id")
    updated_by_id: int | None = Field(default=None, foreign_key="users.id")

    scraping_rules: list["ScrapingRule"] = Relationship(
        back_populates="data_source",
        cascade_delete=True,
    )


class ScrapingRule(SQLModel, TimestampMixin, table=True):
    __tablename__ = "scraping_rules"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=500)
    status: ScrapingRuleStatus = Field(default=ScrapingRuleStatus.ACTIVE)

    data_source_id: int = Field(
        foreign_key="data_sources.id",
        index=True,
        ondelete="CASCADE",
    )

    target_type: TargetType = Field(default=TargetType.SHOP_OVERVIEW)
    granularity: Granularity = Field(default=Granularity.DAY)
    timezone: str = Field(default="Asia/Shanghai", max_length=50)

    time_range: dict | None = Field(default=None, sa_type=JSON)

    schedule: dict | None = Field(default=None, sa_type=JSON)

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

    data_source: DataSource = Relationship(back_populates="scraping_rules")
