from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import and_, delete, func, inspect as sa_inspect, literal_column, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shop_dashboard.models import (
    ShopDashboardColdMetric,
    ShopDashboardReview,
    ShopDashboardScore,
    ShopDashboardViolation,
)
from src.shared.mixins import now
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
        bad_behavior_score: float | None = None,
        shop_name: str | None = None,
        source: str,
    ) -> ShopDashboardScore:
        normalized_bad_behavior_score = (
            0.0 if bad_behavior_score is None else float(bad_behavior_score)
        )
        normalized_shop_name = str(shop_name or "").strip() or None
        insert_timestamp = now()
        update_timestamp = now()
        values = {
            "shop_id": shop_id,
            "metric_date": metric_date,
            "total_score": total_score,
            "product_score": product_score,
            "logistics_score": logistics_score,
            "service_score": service_score,
            "bad_behavior_score": normalized_bad_behavior_score,
            "shop_name": normalized_shop_name,
            "source": source,
            "created_at": insert_timestamp,
            "updated_at": insert_timestamp,
        }
        update_values = {
            "total_score": total_score,
            "product_score": product_score,
            "logistics_score": logistics_score,
            "service_score": service_score,
            "bad_behavior_score": normalized_bad_behavior_score,
            "shop_name": normalized_shop_name,
            "source": source,
            "updated_at": update_timestamp,
        }
        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""

        if dialect_name == "postgresql":
            stmt = (
                postgresql_insert(ShopDashboardScore)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["shop_id", "metric_date"],
                    set_=update_values,
                )
                .returning(
                    ShopDashboardScore,
                    literal_column("xmax = 0").label("is_insert"),
                )
            )
            row = (await self.session.execute(stmt)).one()
            operation = "insert" if bool(row[1]) else "update"
        elif dialect_name == "sqlite":
            stmt = (
                sqlite_insert(ShopDashboardScore)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["shop_id", "metric_date"],
                    set_=update_values,
                )
                .returning(ShopDashboardScore)
            )
            await self.session.execute(stmt)
            operation = "unknown"
        else:
            raise RuntimeError(
                f"unsupported database dialect for upsert: {dialect_name}"
            )

        score_stmt = (
            select(ShopDashboardScore)
            .where(
                ShopDashboardScore.shop_id == shop_id,
                ShopDashboardScore.metric_date == metric_date,
            )
            .execution_options(populate_existing=True)
        )
        score = (await self.session.execute(score_stmt)).scalar_one()
        if operation == "unknown":
            operation = (
                "insert"
                if score.created_at == insert_timestamp
                and score.updated_at == insert_timestamp
                else "update"
            )

        sa_inspect(score).info["insert_or_update"] = operation
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
            "bad_behavior_score": float(score.bad_behavior_score) if score else 0.0,
            "reviews": {
                "summary": {},
                "items": [
                    {
                        "id": row.review_id,
                        "content": row.content,
                        "is_replied": row.is_replied,
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
        return await self.list_display_materials(
            shop_id=shop_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def list_shops(self) -> list[dict[str, Any]]:
        latest_metric_date_subquery = (
            select(
                ShopDashboardScore.shop_id.label("shop_id"),
                func.max(ShopDashboardScore.metric_date).label("metric_date"),
            )
            .group_by(ShopDashboardScore.shop_id)
            .subquery()
        )
        stmt = (
            select(ShopDashboardScore)
            .join(
                latest_metric_date_subquery,
                and_(
                    ShopDashboardScore.shop_id == latest_metric_date_subquery.c.shop_id,
                    ShopDashboardScore.metric_date
                    == latest_metric_date_subquery.c.metric_date,
                ),
            )
            .order_by(ShopDashboardScore.shop_id.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "shop_id": row.shop_id,
                    "shop_name": row.shop_name or "",
                    "metric_date": row.metric_date.isoformat(),
                    "source": row.source,
                    "total_score": float(row.total_score),
                    "product_score": float(row.product_score),
                    "logistics_score": float(row.logistics_score),
                    "service_score": float(row.service_score),
                    "bad_behavior_score": float(row.bad_behavior_score),
                    "updated_at": row.updated_at.isoformat(),
                }
            )

        return items

    async def list_display_materials(
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
            .order_by(
                ShopDashboardScore.metric_date.asc(),
                ShopDashboardScore.updated_at.desc(),
                ShopDashboardScore.id.desc(),
            )
        )
        scores = (await self.session.execute(score_stmt)).scalars().all()

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

        latest_score_by_day: dict[date, ShopDashboardScore] = {}
        for row in scores:
            if row.metric_date not in latest_score_by_day:
                latest_score_by_day[row.metric_date] = row

        metric_dates = sorted(
            set(latest_score_by_day)
            | set(reviews_by_day)
            | set(violations_by_day)
            | set(cold_by_day)
        )
        if not metric_dates:
            return []

        items: list[dict[str, Any]] = []
        for metric_date in metric_dates:
            row = latest_score_by_day.get(metric_date)
            items.append(
                {
                    "shop_id": shop_id,
                    "shop_name": (row.shop_name if row else None) or "",
                    "metric_date": metric_date.isoformat(),
                    "source": row.source if row else "",
                    "total_score": float(row.total_score) if row else 0.0,
                    "product_score": float(row.product_score) if row else 0.0,
                    "logistics_score": float(row.logistics_score) if row else 0.0,
                    "service_score": float(row.service_score) if row else 0.0,
                    "bad_behavior_score": float(row.bad_behavior_score) if row else 0.0,
                    "reviews": reviews_by_day.get(metric_date, []),
                    "violations": violations_by_day.get(metric_date, []),
                    "cold_metrics": cold_by_day.get(metric_date, []),
                }
            )
        return items
