from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.data_import.enums import ImportStatus
from src.domains.data_import.models import DataImportDetail, DataImportRecord
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode
from src.shared.repository import BaseRepository, UNSET


class DataImportRecordRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    def _build_conditions(
        self,
        status: ImportStatus | None = None,
        data_source_id: int | None = None,
    ) -> list:
        conds = []
        if status is not None:
            conds.append(DataImportRecord.status == status)
        if data_source_id is not None:
            conds.append(DataImportRecord.data_source_id == data_source_id)
        return conds

    async def create(self, data: dict) -> DataImportRecord:
        record = DataImportRecord(**data)

        async def _create():
            self.session.add(record)
            return record

        await self._tx(_create)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_by_id(
        self, record_id: int, include_details: bool = False
    ) -> DataImportRecord | None:
        stmt = select(DataImportRecord)
        if include_details:
            stmt = stmt.options(selectinload(DataImportRecord.details))
        stmt = stmt.where(DataImportRecord.id == record_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_batch_no(self, batch_no: str) -> DataImportRecord | None:
        stmt = select(DataImportRecord).where(DataImportRecord.batch_no == batch_no)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update(self, record_id: int, data: dict) -> DataImportRecord:
        record = await self.get_by_id(record_id)
        if not record:
            raise BusinessException(ErrorCode.NOT_FOUND, "DataImportRecord not found")

        for key, value in data.items():
            if value is not UNSET:
                setattr(record, key, value)

        await self._flush()
        return record

    async def delete(self, record_id: int) -> None:
        record = await self.get_by_id(record_id)
        if not record:
            raise BusinessException(ErrorCode.NOT_FOUND, "DataImportRecord not found")
        await self._delete(record)
        await self.session.flush()

    async def get_paginated(
        self,
        page: int,
        size: int,
        user_id: int | None = None,
        status: ImportStatus | None = None,
        data_source_id: int | None = None,
    ) -> tuple[list[DataImportRecord], int]:
        conds = self._build_conditions(status, data_source_id)
        if user_id is not None:
            conds.append(DataImportRecord.created_by_id == user_id)

        stmt = (
            select(DataImportRecord)
            .where(and_(*conds) if conds else True)
            .order_by(DataImportRecord.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )

        count_stmt = select(func.count(DataImportRecord.id)).where(
            and_(*conds) if conds else True
        )

        records = list((await self.session.execute(stmt)).scalars().all())
        total = (await self.session.execute(count_stmt)).scalar_one()

        return records, int(total)

    async def update_status(
        self,
        record_id: int,
        status: ImportStatus,
        error_message: str | None = UNSET,
    ) -> DataImportRecord:
        data: dict[str, Any] = {
            "status": status,
            "error_message": error_message,
        }
        if status == ImportStatus.PROCESSING:
            data["started_at"] = datetime.now(timezone.utc)
        return await self.update(record_id, data)

    async def update_counts(
        self,
        record_id: int,
        total_rows: int | None = None,
        success_rows: int | None = None,
        failed_rows: int | None = None,
    ) -> DataImportRecord:
        data: dict[str, Any] = {}
        if total_rows is not None:
            data["total_rows"] = total_rows
        if success_rows is not None:
            data["success_rows"] = success_rows
        if failed_rows is not None:
            data["failed_rows"] = failed_rows
        return await self.update(record_id, data)

    async def mark_completed(
        self, record_id: int, success_rows: int, failed_rows: int
    ) -> DataImportRecord:
        status = ImportStatus.SUCCESS if failed_rows == 0 else ImportStatus.PARTIAL
        return await self.update(
            record_id,
            {
                "status": status,
                "success_rows": success_rows,
                "failed_rows": failed_rows,
                "completed_at": datetime.now(timezone.utc),
            },
        )


class DataImportDetailRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def create(self, data: dict) -> DataImportDetail:
        detail = DataImportDetail(**data)

        async def _create():
            self.session.add(detail)
            return detail

        await self._tx(_create)
        await self.session.flush()
        await self.session.refresh(detail)
        return detail

    async def bulk_create(self, details: list[dict]) -> list[DataImportDetail]:
        if not details:
            return []

        entities = [DataImportDetail(**data) for data in details]

        async def _bulk_create():
            for entity in entities:
                self.session.add(entity)
            return entities

        await self._tx(_bulk_create)
        await self.session.flush()
        self.session.expire_all()
        return entities

    async def get_by_id(self, detail_id: int) -> DataImportDetail | None:
        stmt = select(DataImportDetail).where(DataImportDetail.id == detail_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_import_record(
        self, import_record_id: int
    ) -> list[DataImportDetail]:
        stmt = (
            select(DataImportDetail)
            .where(DataImportDetail.import_record_id == import_record_id)
            .order_by(DataImportDetail.row_number)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_failed_by_import_record(
        self, import_record_id: int
    ) -> list[DataImportDetail]:
        stmt = (
            select(DataImportDetail)
            .where(
                and_(
                    DataImportDetail.import_record_id == import_record_id,
                    DataImportDetail.status == ImportStatus.FAILED,
                )
            )
            .order_by(DataImportDetail.row_number)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_status(
        self,
        detail_id: int,
        status: ImportStatus,
        error_message: str | None = None,
    ) -> DataImportDetail:
        detail = await self.get_by_id(detail_id)
        if not detail:
            raise BusinessException(ErrorCode.NOT_FOUND, "DataImportDetail not found")

        detail.status = status
        detail.error_message = error_message
        await self._flush()
        return detail

    async def delete_by_import_record(self, import_record_id: int) -> int:
        stmt = delete(DataImportDetail).where(
            DataImportDetail.import_record_id == import_record_id
        )
        result = await self.session.execute(stmt)
        return result.rowcount
