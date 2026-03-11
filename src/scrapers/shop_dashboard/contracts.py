from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class DataSourceContract:
    id: int
    status: str
    timeout: int = 30
    retry_count: int = 3
    rate_limit: int | dict[str, Any] | None = None
    extra_config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ScrapingRuleContract:
    id: int
    status: str
    version: int = 1
    target_type: str = "SHOP_OVERVIEW"
    granularity: str = "DAY"
    timezone: str = "Asia/Shanghai"
    time_range: dict[str, Any] | None = None
    incremental_mode: str = "BY_DATE"
    backfill_last_n_days: int = 3
    data_latency: str = "T+1"
    filters: dict[str, Any] | None = None
    dimensions: list[str] | None = None
    metrics: list[str] | None = None
    dedupe_key: str | None = None
    rate_limit: int | dict[str, Any] | None = None
    top_n: int | None = None
    sort_by: str | None = None
    include_long_tail: bool = False
    session_level: bool = False
    extra_config: dict[str, Any] = field(default_factory=dict)
