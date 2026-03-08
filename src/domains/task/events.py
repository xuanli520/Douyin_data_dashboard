from dataclasses import dataclass, field
from datetime import datetime

from src.domains.task.enums import (
    TaskDefinitionStatus,
    TaskExecutionStatus,
    TaskTriggerMode,
    TaskType,
)
from src.shared.mixins import now


@dataclass(frozen=True, kw_only=True, slots=True, eq=False)
class DomainEvent:
    occurred_at: datetime = field(default_factory=now)


@dataclass(frozen=True, kw_only=True, slots=True, eq=False)
class TaskStatusChangedEvent(DomainEvent):
    task_id: int
    task_type: TaskType
    old_status: TaskDefinitionStatus
    new_status: TaskDefinitionStatus
    changed_by_id: int | None = None


@dataclass(frozen=True, kw_only=True, slots=True, eq=False)
class TaskExecutionTriggeredEvent(DomainEvent):
    task_id: int
    execution_id: int
    trigger_mode: TaskTriggerMode
    status: TaskExecutionStatus
    queue_task_id: str | None = None
    triggered_by: int | None = None
