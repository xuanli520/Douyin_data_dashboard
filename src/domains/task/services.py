from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import (
    BusinessException,
    TaskInvalidPayloadException,
    TaskInvalidStatusException,
    TaskNotFoundException,
    TaskPushFailedException,
)
from src.domains.task.enums import (
    TaskDefinitionStatus,
    TaskExecutionStatus,
    TaskTriggerMode,
    TaskType,
)
from src.domains.task.events import (
    TaskDomainEvent,
    TaskExecutionTriggeredEvent,
    TaskStatusChangedEvent,
)
from src.domains.task.dispatch import TaskDispatcherRegistry
from src.domains.task.exceptions import (
    ScrapingFailedException,
    ShopDashboardNoTargetShopsException,
)
from src.domains.task.models import TaskDefinition, TaskExecution
from src.domains.task.repository import (
    TaskDefinitionRepository,
    TaskExecutionRepository,
)
from src.domains.task.schemas import (
    TaskDefinitionCreate,
    TaskExecutionCreate,
)
from src.application.collection.runtime_loader import CollectionRuntimeLoader
from src.scrapers.shop_dashboard.shop_selection_validator import (
    ensure_explicit_shop_selection_valid,
    has_explicit_shop_selection,
    normalize_shop_selection_payload,
)
from src.session import get_session
from src.shared.errors import ErrorCode


class TaskService:
    def __init__(
        self,
        session: AsyncSession,
        task_repo: TaskDefinitionRepository | None = None,
        execution_repo: TaskExecutionRepository | None = None,
        dispatcher_registry: TaskDispatcherRegistry | None = None,
    ):
        self.session = session
        self.task_repo = task_repo or TaskDefinitionRepository(session)
        self.execution_repo = execution_repo or TaskExecutionRepository(session)
        if dispatcher_registry is None:
            raise BusinessException(
                ErrorCode.TASK_DISPATCHER_REQUIRED,
                "dispatcher_registry is required",
            )
        self.dispatcher_registry = dispatcher_registry
        self._events: list[TaskDomainEvent] = []

    @property
    def events(self) -> list[TaskDomainEvent]:
        return list(self._events)

    def pull_events(self) -> list[TaskDomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def _emit_status_changed_event(
        self,
        *,
        task: TaskDefinition,
        old_status: TaskDefinitionStatus,
        changed_by_id: int | None,
    ) -> None:
        self._events.append(
            TaskStatusChangedEvent(
                task_id=task.id if task.id is not None else 0,
                task_type=task.task_type,
                old_status=old_status,
                new_status=task.status,
                changed_by_id=changed_by_id,
            )
        )

    def _emit_execution_triggered_event(self, execution: TaskExecution) -> None:
        self._events.append(
            TaskExecutionTriggeredEvent(
                task_id=execution.task_id,
                execution_id=execution.id if execution.id is not None else 0,
                trigger_mode=execution.trigger_mode,
                status=execution.status,
                queue_task_id=execution.queue_task_id,
                triggered_by=execution.triggered_by,
            )
        )

    async def create_task(
        self,
        payload: TaskDefinitionCreate,
        *,
        created_by_id: int | None,
    ) -> TaskDefinition:
        task = await self.task_repo.create(
            {
                "name": payload.name,
                "task_type": payload.task_type,
                "status": payload.status,
                "config": payload.config,
                "schedule": payload.schedule,
                "created_by_id": created_by_id,
                "updated_by_id": created_by_id,
            }
        )
        await self.session.commit()
        return task

    async def list_tasks(
        self,
        *,
        page: int,
        size: int,
        status: TaskDefinitionStatus | None = None,
        task_type: TaskType | None = None,
    ) -> tuple[list[TaskDefinition], int]:
        return await self.task_repo.list_paginated(
            page=page,
            size=size,
            status=status,
            task_type=task_type,
        )

    async def get_task(self, task_id: int) -> TaskDefinition | None:
        return await self.task_repo.get_by_id(task_id)

    async def cancel_task(
        self,
        task: TaskDefinition,
        *,
        changed_by_id: int | None,
    ) -> TaskDefinition:
        old_status = task.status
        updated = await self.task_repo.update(
            task,
            {
                "status": TaskDefinitionStatus.CANCELLED,
                "updated_by_id": changed_by_id,
            },
        )
        await self.session.commit()
        self._emit_status_changed_event(
            task=updated,
            old_status=old_status,
            changed_by_id=changed_by_id,
        )
        return updated

    async def create_execution(
        self,
        task: TaskDefinition,
        *,
        payload: TaskExecutionCreate,
        queue_task_id: str | None = None,
        triggered_by: int | None = None,
        emit_event: bool = False,
    ) -> TaskExecution:
        execution = await self.execution_repo.create(
            {
                "task_id": task.id if task.id is not None else 0,
                "queue_task_id": queue_task_id,
                "status": TaskExecutionStatus.QUEUED,
                "trigger_mode": payload.trigger_mode,
                "payload": payload.payload,
                "triggered_by": triggered_by,
            }
        )
        await self.session.commit()
        if emit_event:
            self._emit_execution_triggered_event(execution)
        return execution

    async def run_task(
        self,
        *,
        task_id: int,
        payload: dict[str, Any] | None = None,
        triggered_by: int | None = None,
        trigger_mode: TaskTriggerMode = TaskTriggerMode.MANUAL,
    ) -> TaskExecution:
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundException(task_id=str(task_id))
        if task.status != TaskDefinitionStatus.ACTIVE:
            raise TaskInvalidStatusException(task_id=str(task_id), status=task.status)

        task_payload = dict(payload or {})
        task_payload = await self._validate_payload(
            task_type=task.task_type,
            payload=task_payload,
        )
        execution = await self.create_execution(
            task,
            payload=TaskExecutionCreate(
                payload=task_payload, trigger_mode=trigger_mode
            ),
            triggered_by=triggered_by,
        )
        try:
            async_result = self._dispatch_task(
                task_type=task.task_type,
                payload=task_payload,
                triggered_by=triggered_by,
                execution_id=execution.id if execution.id is not None else 0,
            )
            queue_task_id = str(getattr(async_result, "task_id", "") or "")
            if not queue_task_id:
                raise TaskPushFailedException()

            execution = await self.execution_repo.update(
                execution,
                {"queue_task_id": queue_task_id},
            )
            await self.session.commit()
            self._emit_execution_triggered_event(execution)
            return execution
        except Exception as exc:
            error_message = (
                exc.msg if isinstance(exc, BusinessException) else str(exc)
            )[:1000]
            await self.execution_repo.update(
                execution,
                {
                    "status": TaskExecutionStatus.FAILED,
                    "error_message": error_message,
                },
            )
            await self.session.commit()
            raise

    async def run_task_by_type(
        self,
        *,
        task_type: TaskType,
        payload: dict[str, Any] | None = None,
        triggered_by: int | None = None,
        trigger_mode: TaskTriggerMode = TaskTriggerMode.MANUAL,
        task_name: str | None = None,
    ) -> TaskExecution:
        task = await self.task_repo.get_by_task_type(task_type)
        if task is None:
            task = await self.create_task(
                TaskDefinitionCreate(
                    name=task_name or task_type.value.lower(),
                    task_type=task_type,
                ),
                created_by_id=triggered_by,
            )
        return await self.run_task(
            task_id=task.id if task.id is not None else 0,
            payload=payload,
            triggered_by=triggered_by,
            trigger_mode=trigger_mode,
        )

    async def list_executions(self, task_id: int) -> list[TaskExecution]:
        return await self.execution_repo.list_by_task_id(task_id)

    async def mark_execution_status(
        self,
        *,
        queue_task_id: str,
        status: TaskExecutionStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        processed_rows: int | None = None,
        error_message: str | None = None,
    ) -> TaskExecution | None:
        execution = await self.execution_repo.get_by_queue_task_id(queue_task_id)
        if execution is None:
            return None
        updated = await self.execution_repo.update_status(
            execution,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            processed_rows=processed_rows,
            error_message=error_message,
        )
        await self.session.commit()
        return updated

    def _dispatch_task(
        self,
        *,
        task_type: TaskType,
        payload: dict[str, Any],
        triggered_by: int | None,
        execution_id: int,
    ) -> Any:
        return self.dispatcher_registry.dispatch(
            task_type=task_type,
            payload=payload,
            triggered_by=triggered_by,
            execution_id=execution_id,
        )

    async def _validate_payload(
        self,
        *,
        task_type: TaskType,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_payload = dict(payload)
        if task_type == TaskType.SHOP_DASHBOARD_COLLECTION:
            validated_payload["data_source_id"] = self._require_positive_int(
                validated_payload, field="data_source_id"
            )
            validated_payload["rule_id"] = self._require_positive_int(
                validated_payload, field="rule_id"
            )
            validated_payload = normalize_shop_selection_payload(validated_payload)
            if has_explicit_shop_selection(payload):
                try:
                    ensure_explicit_shop_selection_valid(validated_payload)
                except ValueError as exc:
                    raise TaskInvalidPayloadException(
                        message=str(exc),
                        field="shop_id",
                    ) from exc
            await self._validate_shop_dashboard_target_shops(validated_payload)
        return validated_payload

    async def _validate_shop_dashboard_target_shops(
        self,
        payload: dict[str, Any],
    ) -> None:
        execution_id = str(payload.get("execution_id") or "").strip()
        if not execution_id:
            execution_id = "api-run-task-validation"
        loader = CollectionRuntimeLoader()
        try:
            await loader.load(
                session=self.session,
                data_source_id=int(payload["data_source_id"]),
                rule_id=int(payload["rule_id"]),
                execution_id=execution_id,
                overrides=payload,
            )
        except (ScrapingFailedException, ShopDashboardNoTargetShopsException) as exc:
            error_data = getattr(exc, "error_data", None)
            field = "rule_id"
            if isinstance(error_data, dict):
                if "data_source_id" in error_data:
                    field = "data_source_id"
                elif "rule_id" in error_data:
                    field = "rule_id"
                elif "shop_id" in error_data or "shop_ids" in error_data:
                    field = "shop_id"
            raise TaskInvalidPayloadException(message=exc.msg, field=field) from exc

    def _require_positive_int(self, payload: dict[str, Any], *, field: str) -> int:
        raw = payload.get(field)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raise TaskInvalidPayloadException(
                message=f"Missing required field: {field}",
                field=field,
            )
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise TaskInvalidPayloadException(
                message=f"Invalid integer field: {field}",
                field=field,
            ) from exc
        if value <= 0:
            raise TaskInvalidPayloadException(
                message=f"Field {field} must be > 0",
                field=field,
            )
        return value


def get_task_dispatcher_registry(request: Request) -> TaskDispatcherRegistry:
    registry = getattr(request.app.state, "task_dispatcher_registry", None)
    if isinstance(registry, TaskDispatcherRegistry):
        return registry
    from src.tasks.bootstrap import build_task_dispatcher_registry

    registry = build_task_dispatcher_registry()
    request.app.state.task_dispatcher_registry = registry
    return registry


async def get_task_service(
    session: AsyncSession = Depends(get_session),
    dispatcher_registry: TaskDispatcherRegistry = Depends(get_task_dispatcher_registry),
) -> AsyncGenerator[TaskService, None]:
    yield TaskService(session=session, dispatcher_registry=dispatcher_registry)
