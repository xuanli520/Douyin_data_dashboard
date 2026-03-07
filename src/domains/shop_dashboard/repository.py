from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shop_dashboard.models import (
    ShopDashboardColdMetric,
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

    async def upsert_cold_metrics(
        self,
        *,
        shop_id: str,
        metric_date: date,
        reason: str,
        violations_detail: list[dict[str, Any]],
        arbitration_detail: list[dict[str, Any]],
        dsr_trend: list[dict[str, Any]],
        source: str = "llm",
    ) -> ShopDashboardColdMetric:
        stmt = select(ShopDashboardColdMetric).where(
            ShopDashboardColdMetric.shop_id == shop_id,
            ShopDashboardColdMetric.metric_date == metric_date,
            ShopDashboardColdMetric.reason == reason,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ShopDashboardColdMetric(
                shop_id=shop_id,
                metric_date=metric_date,
                reason=reason,
                violations_detail=violations_detail,
                arbitration_detail=arbitration_detail,
                dsr_trend=dsr_trend,
                source=source,
            )
            self.session.add(row)
        else:
            row.violations_detail = violations_detail
            row.arbitration_detail = arbitration_detail
            row.dsr_trend = dsr_trend
            row.source = source
        await self._flush()
        await self.session.refresh(row)
        return row

    async def build_agent_context(
        self,
        *,
        shop_id: str,
        metric_date: date,
        reason: str,
    ) -> dict[str, Any]:
        score_stmt = select(ShopDashboardScore).where(
            ShopDashboardScore.shop_id == shop_id,
            ShopDashboardScore.metric_date == metric_date,
        )
        score = (await self.session.execute(score_stmt)).scalar_one_or_none()

        reviews_stmt = (
            select(ShopDashboardReview)
            .where(
                ShopDashboardReview.shop_id == shop_id,
                ShopDashboardReview.metric_date == metric_date,
            )
            .order_by(ShopDashboardReview.review_id)
        )
        reviews = (await self.session.execute(reviews_stmt)).scalars().all()

        violations_stmt = (
            select(ShopDashboardViolation)
            .where(
                ShopDashboardViolation.shop_id == shop_id,
                ShopDashboardViolation.metric_date == metric_date,
            )
            .order_by(ShopDashboardViolation.violation_id)
        )
        violations = (await self.session.execute(violations_stmt)).scalars().all()

        cold_stmt = select(ShopDashboardColdMetric).where(
            ShopDashboardColdMetric.shop_id == shop_id,
            ShopDashboardColdMetric.metric_date == metric_date,
            ShopDashboardColdMetric.reason == reason,
        )
        cold = (await self.session.execute(cold_stmt)).scalar_one_or_none()

        return {
            "shop_id": shop_id,
            "metric_date": metric_date.isoformat(),
            "total_score": float(score.total_score) if score else 0.0,
            "product_score": float(score.product_score) if score else 0.0,
            "logistics_score": float(score.logistics_score) if score else 0.0,
            "service_score": float(score.service_score) if score else 0.0,
            "reviews": {
                "summary": {},
                "items": [
                    {
                        "id": row.review_id,
                        "content": row.content,
                        "shop_reply": row.is_replied,
                    }
                    for row in reviews
                ],
            },
            "violations": {
                "summary": {},
                "waiting_list": [
                    {
                        "id": row.violation_id,
                        "type": row.violation_type,
                        "description": row.description,
                        "score": row.score,
                    }
                    for row in violations
                ],
            },
            "violations_detail": (
                list(cold.violations_detail) if cold is not None else []
            ),
            "arbitration_detail": (
                list(cold.arbitration_detail) if cold is not None else []
            ),
            "dsr_trend": list(cold.dsr_trend) if cold is not None else [],
            "raw": {},
        }

    async def query_dashboard_results(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        score_stmt = (
            select(ShopDashboardScore)
            .where(
                ShopDashboardScore.shop_id == shop_id,
                ShopDashboardScore.metric_date >= start_date,
                ShopDashboardScore.metric_date <= end_date,
            )
            .order_by(ShopDashboardScore.metric_date.asc())
        )
        scores = (await self.session.execute(score_stmt)).scalars().all()
        if not scores:
            return []

        review_stmt = select(ShopDashboardReview).where(
            ShopDashboardReview.shop_id == shop_id,
            ShopDashboardReview.metric_date >= start_date,
            ShopDashboardReview.metric_date <= end_date,
        )
        violation_stmt = select(ShopDashboardViolation).where(
            ShopDashboardViolation.shop_id == shop_id,
            ShopDashboardViolation.metric_date >= start_date,
            ShopDashboardViolation.metric_date <= end_date,
        )
        cold_stmt = select(ShopDashboardColdMetric).where(
            ShopDashboardColdMetric.shop_id == shop_id,
            ShopDashboardColdMetric.metric_date >= start_date,
            ShopDashboardColdMetric.metric_date <= end_date,
        )

        review_rows = (await self.session.execute(review_stmt)).scalars().all()
        violation_rows = (await self.session.execute(violation_stmt)).scalars().all()
        cold_rows = (await self.session.execute(cold_stmt)).scalars().all()

        reviews_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for row in review_rows:
            reviews_by_day[row.metric_date].append(
                {
                    "id": row.review_id,
                    "content": row.content,
                    "is_replied": row.is_replied,
                    "source": row.source,
                }
            )

        violations_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for row in violation_rows:
            violations_by_day[row.metric_date].append(
                {
                    "id": row.violation_id,
                    "type": row.violation_type,
                    "description": row.description,
                    "score": row.score,
                    "source": row.source,
                }
            )

        cold_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for row in cold_rows:
            cold_by_day[row.metric_date].append(
                {
                    "reason": row.reason,
                    "source": row.source,
                    "violations_detail": list(row.violations_detail),
                    "arbitration_detail": list(row.arbitration_detail),
                    "dsr_trend": list(row.dsr_trend),
                }
            )

        items: list[dict[str, Any]] = []
        for row in scores:
            metric_date = row.metric_date
            items.append(
                {
                    "shop_id": row.shop_id,
                    "metric_date": metric_date.isoformat(),
                    "source": row.source,
                    "total_score": float(row.total_score),
                    "product_score": float(row.product_score),
                    "logistics_score": float(row.logistics_score),
                    "service_score": float(row.service_score),
                    "reviews": reviews_by_day.get(metric_date, []),
                    "violations": violations_by_day.get(metric_date, []),
                    "cold_metrics": cold_by_day.get(metric_date, []),
                }
            )
        return items
