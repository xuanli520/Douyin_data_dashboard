from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.collection_job.enums import CollectionJobStatus
from src.domains.collection_job.models import CollectionJob
from src.domains.task.enums import TaskType
from src.shared.repository import BaseRepository


class CollectionJobRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def create(self, data: dict[str, Any]) -> CollectionJob:
        job = CollectionJob(**data)
        await self._add(job)
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: int) -> CollectionJob | None:
        stmt = select(CollectionJob).where(CollectionJob.id == job_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update(self, job: CollectionJob, data: dict[str, Any]) -> CollectionJob:
        for key, value in data.items():
            if value is not None:
                setattr(job, key, value)
        await self._flush()
        return job

    async def delete(self, job: CollectionJob) -> None:
        await self._delete(job)

    async def list_enabled(
        self,
        *,
        task_type: TaskType | None = None,
    ) -> list[CollectionJob]:
        stmt = select(CollectionJob).where(
            CollectionJob.status == CollectionJobStatus.ACTIVE
        )
        if task_type is not None:
            stmt = stmt.where(CollectionJob.task_type == task_type)
        stmt = stmt.order_by(CollectionJob.task_type.asc(), CollectionJob.id.asc())
        return list((await self.session.execute(stmt)).scalars().all())
