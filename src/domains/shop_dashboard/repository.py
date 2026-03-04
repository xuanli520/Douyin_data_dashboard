from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shop_dashboard.models import (
    ShopDashboardReview,
    ShopDashboardScore,
    ShopDashboardViolation,
)
from src.shared.repository import BaseRepository


class ShopDashboardRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def upsert_score(
        self,
        *,
        shop_id: str,
        metric_date: date,
        total_score: float,
        product_score: float,
        logistics_score: float,
        service_score: float,
        source: str,
    ) -> ShopDashboardScore:
        stmt = select(ShopDashboardScore).where(
            ShopDashboardScore.shop_id == shop_id,
            ShopDashboardScore.metric_date == metric_date,
        )
        score = (await self.session.execute(stmt)).scalar_one_or_none()
        if score is None:
            score = ShopDashboardScore(
                shop_id=shop_id,
                metric_date=metric_date,
                total_score=total_score,
                product_score=product_score,
                logistics_score=logistics_score,
                service_score=service_score,
                source=source,
            )
            self.session.add(score)
        else:
            score.total_score = total_score
            score.product_score = product_score
            score.logistics_score = logistics_score
            score.service_score = service_score
            score.source = source

        await self._flush()
        await self.session.refresh(score)
        return score

    async def replace_reviews(
        self,
        *,
        shop_id: str,
        metric_date: date,
        reviews: list[dict],
    ) -> list[ShopDashboardReview]:
        await self.session.execute(
            delete(ShopDashboardReview).where(
                ShopDashboardReview.shop_id == shop_id,
                ShopDashboardReview.metric_date == metric_date,
            )
        )

        rows = [
            ShopDashboardReview(
                shop_id=shop_id,
                metric_date=metric_date,
                review_id=str(item["review_id"]),
                content=str(item["content"]),
                is_replied=bool(item.get("is_replied", False)),
                source=str(item["source"]),
            )
            for item in reviews
        ]
        self.session.add_all(rows)
        await self._flush()
        return rows

    async def replace_violations(
        self,
        *,
        shop_id: str,
        metric_date: date,
        violations: list[dict],
    ) -> list[ShopDashboardViolation]:
        await self.session.execute(
            delete(ShopDashboardViolation).where(
                ShopDashboardViolation.shop_id == shop_id,
                ShopDashboardViolation.metric_date == metric_date,
            )
        )

        rows = [
            ShopDashboardViolation(
                shop_id=shop_id,
                metric_date=metric_date,
                violation_id=str(item["violation_id"]),
                violation_type=str(item["violation_type"]),
                description=item.get("description"),
                score=int(item.get("score", 0)),
                source=str(item["source"]),
            )
            for item in violations
        ]
        self.session.add_all(rows)
        await self._flush()
        return rows
