from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.domains.data_source.enums import DataSourceStatus, DataSourceType
from src.shared.mixins import now


@dataclass(frozen=True, kw_only=True, slots=True)
class DomainEvent:
    occurred_at: datetime = field(default_factory=now)


@dataclass(frozen=True, kw_only=True, slots=True)
class DataSourceCreatedEvent(DomainEvent):
    data_source_id: int
    name: str
    source_type: DataSourceType
    status: DataSourceStatus
    created_by_id: int | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class DataSourceStatusChangedEvent(DomainEvent):
    data_source_id: int
    name: str
    old_status: DataSourceStatus
    new_status: DataSourceStatus
    changed_by_id: int | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class ScrapingRuleUpdatedEvent(DomainEvent):
    rule_id: int
    data_source_id: int
    name: str
    old_config: dict[str, Any] = field(default_factory=dict)
    new_config: dict[str, Any] = field(default_factory=dict)
    updated_fields: list[str] = field(default_factory=list)
