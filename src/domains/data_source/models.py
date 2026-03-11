from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel

from src.shared.mixins import TimestampMixin
from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
)

if TYPE_CHECKING:
    from src.domains.scraping_rule.models import ScrapingRule


class DataSource(SQLModel, TimestampMixin, table=True):
    __tablename__ = "data_sources"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, index=True)
    description: str | None = Field(default=None, max_length=500)
    source_type: DataSourceType = Field(default=DataSourceType.DOUYIN_SHOP)
    status: DataSourceStatus = Field(default=DataSourceStatus.ACTIVE)

    shop_id: str | None = Field(default=None, max_length=50, index=True)
    account_name: str | None = Field(default=None, max_length=100)
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
