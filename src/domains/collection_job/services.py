from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.collection_job.models import CollectionJob
from src.domains.collection_job.repository import CollectionJobRepository
from src.domains.collection_job.schemas import CollectionJobCreate, ScheduleConfig
from src.domains.task.enums import TaskType
from src.session import get_session


class CollectionJobService:
    def __init__(
        self,
        session: AsyncSession,
        repo: CollectionJobRepository | None = None,
    ):
        self.session = session
        self.repo = repo or CollectionJobRepository(session=session)

    async def create_job(
        self,
        *,
        name: str,
        task_type: TaskType,
        data_source_id: int,
        rule_id: int,
        schedule: dict[str, Any] | ScheduleConfig,
        status: CollectionJobStatus = CollectionJobStatus.ACTIVE,
    ) -> CollectionJob:
        schedule_config = ScheduleConfig.model_validate(schedule)
        job = await self.repo.create(
            {
                "name": name,
                "task_type": task_type,
                "data_source_id": data_source_id,
                "rule_id": rule_id,
                "schedule": schedule_config.model_dump(mode="python"),
                "status": status,
            }
        )
        await self.session.commit()
        return self._normalize_schedule(job)

    async def create(self, payload: CollectionJobCreate) -> CollectionJob:
        return await self.create_job(
            name=payload.name,
            task_type=payload.task_type,
            data_source_id=payload.data_source_id,
            rule_id=payload.rule_id,
            schedule=payload.schedule,
            status=payload.status,
        )

    async def list_enabled_jobs(
        self,
        *,
        task_type: TaskType | str | None = None,
    ) -> list[CollectionJob]:
        resolved_task_type = self._resolve_task_type(task_type)
        jobs = await self.repo.list_enabled(task_type=resolved_task_type)
        return [self._normalize_schedule(job) for job in jobs]

    def _resolve_task_type(self, task_type: TaskType | str | None) -> TaskType | None:
        if task_type is None or isinstance(task_type, TaskType):
            return task_type
        return TaskType(str(task_type))

    def _normalize_schedule(self, job: CollectionJob) -> CollectionJob:
        schedule = ScheduleConfig.model_validate(job.schedule or {})
        job.schedule = schedule.model_dump(mode="python")
        return job


async def get_collection_job_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[CollectionJobService, None]:
    yield CollectionJobService(session=session)
