from datetime import UTC, datetime

from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
)
from src.core.exceptions import _raise_integrity_error
from src.domains.data_source.models import DataSource
from src.shared.repository import BaseRepository


class DataSourceRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    def _build_conditions(
        self,
        status: DataSourceStatus | None = None,
        source_type: DataSourceType | None = None,
        name: str | None = None,
    ) -> list:
        conds = []
        if status is not None:
            conds.append(DataSource.status == status)
        if source_type is not None:
            conds.append(DataSource.source_type == source_type)
        if name is not None:
            conds.append(DataSource.name.ilike(f"%{name}%"))
        return conds

    async def create(self, data: dict) -> DataSource:
        data_source = DataSource(**data)
        try:

            async def _create():
                self.session.add(data_source)
                return data_source

            await self._tx(_create)
            await self.session.flush()
            await self.session.refresh(data_source)
            return data_source
        except IntegrityError as e:
            _raise_integrity_error(e)

    async def get_by_id(
        self, data_source_id: int, include_rules: bool = False
    ) -> DataSource | None:
        stmt = select(DataSource)
        if include_rules:
            stmt = stmt.options(selectinload(DataSource.scraping_rules))
        stmt = stmt.where(DataSource.id == data_source_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update(self, data_source_id: int, data: dict) -> DataSource | None:
        data_source = await self.get_by_id(data_source_id)
        if not data_source:
            return None

        for key, value in data.items():
            if value is not None:
                setattr(data_source, key, value)

        try:
            await self._flush()
            return data_source
        except IntegrityError as e:
            _raise_integrity_error(e)

    async def delete(self, data_source_id: int) -> bool:
        data_source = await self.get_by_id(data_source_id)
        if not data_source:
            return False
        try:
            await self._delete(data_source)
            await self.session.flush()
            return True
        except IntegrityError as e:
            _raise_integrity_error(e)

    async def get_paginated(
        self,
        page: int,
        size: int,
        status: DataSourceStatus | None = None,
        source_type: DataSourceType | None = None,
        name: str | None = None,
    ) -> tuple[list[DataSource], int]:
        conds = self._build_conditions(status, source_type, name)

        stmt = (
            select(DataSource)
            .where(and_(*conds) if conds else True)
            .order_by(DataSource.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )

        count_stmt = select(func.count(DataSource.id)).where(
            and_(*conds) if conds else True
        )

        data_sources = list((await self.session.execute(stmt)).scalars().all())
        total = (await self.session.execute(count_stmt)).scalar_one()

        return data_sources, int(total)

    async def get_by_status(self, status: DataSourceStatus) -> list[DataSource]:
        stmt = (
            select(DataSource)
            .where(DataSource.status == status)
            .order_by(DataSource.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_type(self, source_type: DataSourceType) -> list[DataSource]:
        stmt = (
            select(DataSource)
            .where(DataSource.source_type == source_type)
            .order_by(DataSource.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_status(
        self, data_source_id: int, status: DataSourceStatus
    ) -> DataSource | None:
        return await self.update(data_source_id, {"status": status})

    async def update_last_used(self, data_source_id: int) -> None:
        data_source = await self.get_by_id(data_source_id)
        if data_source:
            data_source.last_used_at = datetime.now(UTC)
            await self._flush()

    async def record_error(self, data_source_id: int, error_msg: str) -> None:
        data_source = await self.get_by_id(data_source_id)
        if data_source:
            data_source.last_error_at = datetime.now(UTC)
            data_source.last_error_msg = error_msg
            data_source.status = DataSourceStatus.ERROR
            await self._flush()
