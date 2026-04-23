from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Integer, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.task.enums import TaskDefinitionStatus, TaskExecutionStatus, TaskType
from src.domains.task.models import TaskDefinition, TaskExecution
from src.shared.repository import BaseRepository


class TaskDefinitionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def create(self, data: dict[str, Any]) -> TaskDefinition:
        task = TaskDefinition(**data)
        await self._add(task)
        await self.session.refresh(task)
        return task

    async def get_by_id(self, task_id: int) -> TaskDefinition | None:
        stmt = select(TaskDefinition).where(TaskDefinition.id == task_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_task_type(self, task_type: TaskType) -> TaskDefinition | None:
        stmt = (
            select(TaskDefinition)
            .where(TaskDefinition.task_type == task_type)
            .order_by(TaskDefinition.id.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_paginated(
        self,
        *,
        page: int,
        size: int,
        status: TaskDefinitionStatus | None = None,
        task_type: TaskType | None = None,
    ) -> tuple[list[TaskDefinition], int]:
        conditions = []
        if status is not None:
            conditions.append(TaskDefinition.status == status)
        if task_type is not None:
            conditions.append(TaskDefinition.task_type == task_type)

        where_clause = and_(*conditions) if conditions else True
        stmt = (
            select(TaskDefinition)
            .where(where_clause)
            .order_by(TaskDefinition.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        count_stmt = select(func.count(TaskDefinition.id)).where(where_clause)
        items = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return items, total

    async def update(
        self,
        task: TaskDefinition,
        data: dict[str, Any],
    ) -> TaskDefinition:
        for key, value in data.items():
            if value is not None:
                setattr(task, key, value)
        await self._flush()
        return task

    async def delete(self, task: TaskDefinition) -> None:
        await self._delete(task)


class TaskExecutionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def create(self, data: dict[str, Any]) -> TaskExecution:
        execution = TaskExecution(**data)
        await self._add(execution)
        await self.session.refresh(execution)
        return execution

    async def get_by_id(self, execution_id: int) -> TaskExecution | None:
        stmt = select(TaskExecution).where(TaskExecution.id == execution_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_queue_task_id(self, queue_task_id: str) -> TaskExecution | None:
        stmt = select(TaskExecution).where(TaskExecution.queue_task_id == queue_task_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> TaskExecution | None:
        stmt = select(TaskExecution).where(
            TaskExecution.idempotency_key == idempotency_key
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_running_older_than(
        self,
        cutoff: datetime,
        *,
        limit: int = 100,
    ) -> list[TaskExecution]:
        age_expr = func.coalesce(
            TaskExecution.started_at,
            TaskExecution.updated_at,
            TaskExecution.created_at,
        )
        stmt = (
            select(TaskExecution)
            .where(
                TaskExecution.status == TaskExecutionStatus.RUNNING,
                TaskExecution.queue_task_id.is_not(None),
                age_expr <= cutoff,
            )
            .order_by(age_expr.asc(), TaskExecution.id.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_latest_completed_by_rule_ids(
        self,
        rule_ids: list[int],
    ) -> dict[int, TaskExecution]:
        if not rule_ids:
            return {}

        rule_id_expr = cast(TaskExecution.payload["rule_id"].as_string(), Integer)
        completed_at_expr = func.coalesce(
            TaskExecution.completed_at,
            TaskExecution.updated_at,
            TaskExecution.created_at,
        )
        ranked = (
            select(
                TaskExecution.id.label("execution_id"),
                rule_id_expr.label("rule_id"),
                func.row_number()
                .over(
                    partition_by=rule_id_expr,
                    order_by=[
                        completed_at_expr.desc(),
                        TaskExecution.id.desc(),
                    ],
                )
                .label("row_num"),
            )
            .where(
                TaskExecution.status.in_(
                    [
                        TaskExecutionStatus.SUCCESS,
                        TaskExecutionStatus.FAILED,
                    ]
                ),
                rule_id_expr.in_(rule_ids),
            )
            .subquery()
        )
        stmt = (
            select(TaskExecution, ranked.c.rule_id)
            .join(ranked, TaskExecution.id == ranked.c.execution_id)
            .where(ranked.c.row_num == 1)
        )
        rows = (await self.session.execute(stmt)).all()
        return {
            int(rule_id): execution
            for execution, rule_id in rows
            if rule_id is not None
        }

    async def list_by_task_id(self, task_id: int) -> list[TaskExecution]:
        stmt = (
            select(TaskExecution)
            .where(TaskExecution.task_id == task_id)
            .order_by(TaskExecution.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_status(
        self,
        execution: TaskExecution,
        *,
        status: TaskExecutionStatus,
        started_at=None,
        completed_at=None,
        processed_rows: int | None = None,
        error_message: str | None = None,
    ) -> TaskExecution:
        execution.status = status
        if started_at is not None:
            execution.started_at = started_at
        if completed_at is not None:
            execution.completed_at = completed_at
        if processed_rows is not None:
            execution.processed_rows = processed_rows
        if error_message is not None:
            execution.error_message = error_message
        await self._flush()
        return execution

    async def update(
        self,
        execution: TaskExecution,
        data: dict[str, Any],
    ) -> TaskExecution:
        for key, value in data.items():
            if value is not None:
                setattr(execution, key, value)
        await self._flush()
        return execution
