from datetime import datetime

from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.data_source.enums import DataSourceStatus, DataSourceType
from src.domains.data_source.models import DataSource, ScrapingRule
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class DataSourceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

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
        try:
            if self.session.in_transaction():
                data_source = DataSource(**data)
                self.session.add(data_source)
                await self.session.flush()
            else:
                async with self.session.begin():
                    data_source = DataSource(**data)
                    self.session.add(data_source)
                    await self.session.flush()
            await self.session.refresh(data_source)
            return data_source
        except IntegrityError as e:
            await self.session.rollback()
            constraint_name = (
                str(e.orig.diag.constraint_name) if e.orig and e.orig.diag else ""
            )
            if "name" in constraint_name:
                raise BusinessException(
                    ErrorCode.DATASOURCE_NAME_CONFLICT, "DataSource name already exists"
                ) from e
            raise

    async def get_by_id(
        self, data_source_id: int, include_rules: bool = False
    ) -> DataSource | None:
        stmt = select(DataSource)
        if include_rules:
            stmt = stmt.options(selectinload(DataSource.scraping_rules))
        stmt = stmt.where(DataSource.id == data_source_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update(self, data_source_id: int, data: dict) -> DataSource:
        data_source = await self.get_by_id(data_source_id)
        if not data_source:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        if self.session.in_transaction():
            for key, value in data.items():
                if value is not None:
                    setattr(data_source, key, value)
            await self.session.flush()
        else:
            async with self.session.begin():
                for key, value in data.items():
                    if value is not None:
                        setattr(data_source, key, value)
                await self.session.flush()

        await self.session.refresh(data_source)
        return data_source

    async def delete(self, data_source_id: int) -> None:
        data_source = await self.get_by_id(data_source_id)
        if not data_source:
            raise BusinessException(
                ErrorCode.DATASOURCE_NOT_FOUND, "DataSource not found"
            )

        if self.session.in_transaction():
            await self.session.delete(data_source)
        else:
            async with self.session.begin():
                await self.session.delete(data_source)

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

    async def get_by_shop_id(self, shop_id: str) -> DataSource | None:
        stmt = select(DataSource).where(DataSource.shop_id == shop_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update_status(
        self, data_source_id: int, status: DataSourceStatus
    ) -> DataSource:
        return await self.update(data_source_id, {"status": status})

    async def update_last_used(self, data_source_id: int) -> None:
        data_source = await self.get_by_id(data_source_id)
        if data_source:
            data_source.last_used_at = datetime.now()
            if self.session.in_transaction():
                await self.session.flush()
            else:
                async with self.session.begin():
                    await self.session.flush()

    async def record_error(self, data_source_id: int, error_msg: str) -> None:
        data_source = await self.get_by_id(data_source_id)
        if data_source:
            data_source.last_error_at = datetime.now()
            data_source.last_error_msg = error_msg
            data_source.status = DataSourceStatus.ERROR
            if self.session.in_transaction():
                await self.session.flush()
            else:
                async with self.session.begin():
                    await self.session.flush()


class ScrapingRuleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: dict) -> ScrapingRule:
        if self.session.in_transaction():
            rule = ScrapingRule(**data)
            self.session.add(rule)
            await self.session.flush()
        else:
            async with self.session.begin():
                rule = ScrapingRule(**data)
                self.session.add(rule)
                await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def get_by_id(self, rule_id: int) -> ScrapingRule | None:
        stmt = (
            select(ScrapingRule)
            .options(selectinload(ScrapingRule.data_source))
            .where(ScrapingRule.id == rule_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_data_source(self, data_source_id: int) -> list[ScrapingRule]:
        stmt = (
            select(ScrapingRule)
            .where(ScrapingRule.data_source_id == data_source_id)
            .order_by(ScrapingRule.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update(self, rule_id: int, data: dict) -> ScrapingRule:
        rule = await self.get_by_id(rule_id)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )

        if self.session.in_transaction():
            for key, value in data.items():
                if value is not None:
                    setattr(rule, key, value)
            await self.session.flush()
        else:
            async with self.session.begin():
                for key, value in data.items():
                    if value is not None:
                        setattr(rule, key, value)
                await self.session.flush()

        await self.session.refresh(rule)
        return rule

    async def delete(self, rule_id: int) -> None:
        rule = await self.get_by_id(rule_id)
        if not rule:
            raise BusinessException(
                ErrorCode.SCRAPING_RULE_NOT_FOUND, "ScrapingRule not found"
            )

        if self.session.in_transaction():
            await self.session.delete(rule)
        else:
            async with self.session.begin():
                await self.session.delete(rule)
