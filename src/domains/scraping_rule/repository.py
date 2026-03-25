from sqlalchemy import and_, func, select
from sqlalchemy.exc import DataError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.data_source.enums import ScrapingRuleStatus, TargetType
from src.domains.scraping_rule.models import ScrapingRule
from src.shared.repository import BaseRepository


class ScrapingRuleRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def create(self, data: dict) -> ScrapingRule:
        rule = ScrapingRule(**data)

        async def _create():
            self.session.add(rule)
            return rule

        try:
            await self._tx(_create)
            await self.session.flush()
            await self.session.refresh(rule)
            return rule
        except DataError:
            await self.session.rollback()
            raise

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

    async def update(self, rule_id: int, data: dict) -> ScrapingRule | None:
        rule = await self.get_by_id(rule_id)
        if not rule:
            return None

        for key, value in data.items():
            if value is not None:
                setattr(rule, key, value)

        await self._flush()
        return rule

    async def delete(self, rule_id: int) -> bool:
        rule = await self.get_by_id(rule_id)
        if not rule:
            return False
        await self._delete(rule)
        await self.session.flush()
        return True

    async def get_paginated(
        self,
        page: int,
        size: int,
        name: str | None = None,
        rule_type: TargetType | None = None,
        status: ScrapingRuleStatus | None = None,
        data_source_id: int | None = None,
    ) -> tuple[list[ScrapingRule], int]:
        conds = []
        if name:
            conds.append(ScrapingRule.name.ilike(f"%{name}%"))
        if rule_type:
            conds.append(ScrapingRule.target_type == rule_type)
        if status:
            conds.append(ScrapingRule.status == status)
        if data_source_id:
            conds.append(ScrapingRule.data_source_id == data_source_id)

        stmt = (
            select(ScrapingRule)
            .options(selectinload(ScrapingRule.data_source))
            .where(and_(*conds) if conds else True)
            .order_by(ScrapingRule.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )

        count_stmt = select(func.count(ScrapingRule.id)).where(
            and_(*conds) if conds else True
        )

        rules = list((await self.session.execute(stmt)).scalars().all())
        total = (await self.session.execute(count_stmt)).scalar()

        return rules, int(total)
