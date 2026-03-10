from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.experience.models import ExperienceIssueDaily, ExperienceMetricDaily
from src.shared.repository import BaseRepository


class ExperienceRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def upsert_metric(
        self,
        *,
        shop_id: str,
        metric_date: date,
        dimension: str,
        metric_key: str,
        metric_score: float,
        metric_value: float,
        metric_unit: str,
        source_field: str,
        formula_expr: str | None = None,
        is_penalty: bool = False,
        deduct_points: float = 0.0,
        source: str = "collector",
        extra: dict[str, Any] | None = None,
    ) -> ExperienceMetricDaily:
        stmt = select(ExperienceMetricDaily).where(
            ExperienceMetricDaily.shop_id == shop_id,
            ExperienceMetricDaily.metric_date == metric_date,
            ExperienceMetricDaily.dimension == dimension,
            ExperienceMetricDaily.metric_key == metric_key,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ExperienceMetricDaily(
                shop_id=shop_id,
                metric_date=metric_date,
                dimension=dimension,
                metric_key=metric_key,
                metric_score=metric_score,
                metric_value=metric_value,
                metric_unit=metric_unit,
                source_field=source_field,
                formula_expr=formula_expr,
                is_penalty=is_penalty,
                deduct_points=deduct_points,
                source=source,
                extra=dict(extra or {}),
            )
            self.session.add(row)
        else:
            row.metric_score = metric_score
            row.metric_value = metric_value
            row.metric_unit = metric_unit
            row.source_field = source_field
            row.formula_expr = formula_expr
            row.is_penalty = is_penalty
            row.deduct_points = deduct_points
            row.source = source
            row.extra = dict(extra or {})
        await self._flush()
        await self.session.refresh(row)
        return row

    async def upsert_issue(
        self,
        *,
        shop_id: str,
        metric_date: date,
        dimension: str,
        issue_key: str,
        issue_title: str,
        status: str,
        owner: str,
        impact_score: float,
        deduct_points: float,
        occurred_at,
        deadline_at,
        source: str = "collector",
        extra: dict[str, Any] | None = None,
    ) -> ExperienceIssueDaily:
        stmt = select(ExperienceIssueDaily).where(
            ExperienceIssueDaily.shop_id == shop_id,
            ExperienceIssueDaily.metric_date == metric_date,
            ExperienceIssueDaily.issue_key == issue_key,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ExperienceIssueDaily(
                shop_id=shop_id,
                metric_date=metric_date,
                dimension=dimension,
                issue_key=issue_key,
                issue_title=issue_title,
                status=status,
                owner=owner,
                impact_score=impact_score,
                deduct_points=deduct_points,
                occurred_at=occurred_at,
                deadline_at=deadline_at,
                source=source,
                extra=dict(extra or {}),
            )
            self.session.add(row)
        else:
            row.dimension = dimension
            row.issue_title = issue_title
            row.status = status
            row.owner = owner
            row.impact_score = impact_score
            row.deduct_points = deduct_points
            row.occurred_at = occurred_at
            row.deadline_at = deadline_at
            row.source = source
            row.extra = dict(extra or {})
        await self._flush()
        await self.session.refresh(row)
        return row

    async def list_metric_rows(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
        dimension: str | None = None,
        metric_key: str | None = None,
    ) -> list[ExperienceMetricDaily]:
        filters = [
            ExperienceMetricDaily.shop_id == shop_id,
            ExperienceMetricDaily.metric_date >= start_date,
            ExperienceMetricDaily.metric_date <= end_date,
        ]
        if dimension:
            filters.append(ExperienceMetricDaily.dimension == dimension)
        if metric_key:
            filters.append(ExperienceMetricDaily.metric_key == metric_key)
        stmt = (
            select(ExperienceMetricDaily)
            .where(and_(*filters))
            .order_by(
                ExperienceMetricDaily.metric_date.asc(),
                ExperienceMetricDaily.dimension.asc(),
                ExperienceMetricDaily.metric_key.asc(),
            )
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_latest_metric_date(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
        dimension: str | None = None,
    ) -> date | None:
        filters = [
            ExperienceMetricDaily.shop_id == shop_id,
            ExperienceMetricDaily.metric_date >= start_date,
            ExperienceMetricDaily.metric_date <= end_date,
        ]
        if dimension:
            filters.append(ExperienceMetricDaily.dimension == dimension)

        stmt = select(func.max(ExperienceMetricDaily.metric_date)).where(and_(*filters))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_rows_for_metric_date(
        self,
        *,
        shop_id: str,
        metric_date: date,
        dimension: str | None = None,
    ) -> list[ExperienceMetricDaily]:
        filters = [
            ExperienceMetricDaily.shop_id == shop_id,
            ExperienceMetricDaily.metric_date == metric_date,
        ]
        if dimension:
            filters.append(ExperienceMetricDaily.dimension == dimension)
        stmt = (
            select(ExperienceMetricDaily)
            .where(and_(*filters))
            .order_by(ExperienceMetricDaily.metric_key.asc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_latest_metric_row(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
        metric_key: str,
    ) -> ExperienceMetricDaily | None:
        stmt = (
            select(ExperienceMetricDaily)
            .where(
                ExperienceMetricDaily.shop_id == shop_id,
                ExperienceMetricDaily.metric_date >= start_date,
                ExperienceMetricDaily.metric_date <= end_date,
                ExperienceMetricDaily.metric_key == metric_key,
            )
            .order_by(ExperienceMetricDaily.metric_date.desc())
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_issues(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
        dimension: str | None,
        status: str | None,
        page: int,
        size: int,
    ) -> tuple[list[ExperienceIssueDaily], int]:
        filters = [
            ExperienceIssueDaily.shop_id == shop_id,
            ExperienceIssueDaily.metric_date >= start_date,
            ExperienceIssueDaily.metric_date <= end_date,
        ]
        if dimension:
            filters.append(ExperienceIssueDaily.dimension == dimension)
        if status:
            filters.append(ExperienceIssueDaily.status == status)

        total_stmt = select(func.count(ExperienceIssueDaily.id)).where(and_(*filters))
        total = (await self.session.execute(total_stmt)).scalar_one()

        stmt = (
            select(ExperienceIssueDaily)
            .where(and_(*filters))
            .order_by(
                ExperienceIssueDaily.metric_date.desc(),
                ExperienceIssueDaily.id.desc(),
            )
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return rows, int(total)

    async def list_issue_rows(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
    ) -> list[ExperienceIssueDaily]:
        stmt = (
            select(ExperienceIssueDaily)
            .where(
                ExperienceIssueDaily.shop_id == shop_id,
                ExperienceIssueDaily.metric_date >= start_date,
                ExperienceIssueDaily.metric_date <= end_date,
            )
            .order_by(ExperienceIssueDaily.metric_date.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()
