from __future__ import annotations

from typing import Any, Callable

from src.domains.task.enums import TaskType
from src.exceptions import TaskPushFailedException

TaskDispatchHandler = Callable[[dict[str, Any], int | None, int], Any]


class TaskDispatcherRegistry:
    def __init__(self):
        self._handlers: dict[TaskType, TaskDispatchHandler] = {}

    def register(
        self,
        task_type: TaskType,
        handler: TaskDispatchHandler,
    ) -> None:
        self._handlers[task_type] = handler

    def has_handler(self, task_type: TaskType) -> bool:
        return task_type in self._handlers

    def dispatch(
        self,
        *,
        task_type: TaskType,
        payload: dict[str, Any],
        triggered_by: int | None,
        execution_id: int,
    ) -> Any:
        handler = self._handlers.get(task_type)
        if handler is None:
            raise TaskPushFailedException()
        return handler(payload, triggered_by, execution_id)
