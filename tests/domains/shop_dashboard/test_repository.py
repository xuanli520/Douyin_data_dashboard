from datetime import date

from sqlalchemy import func, select

from src.domains.shop_dashboard.models import (
    ShopDashboardColdMetric,
    ShopDashboardReview,
    ShopDashboardScore,
    ShopDashboardViolation,
)
from src.domains.shop_dashboard.repository import ShopDashboardRepository


async def test_upsert_score_by_shop_and_date(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        metric_date = date(2026, 3, 3)

        first = await repo.upsert_score(
            shop_id="shop-1",
            metric_date=metric_date,
            total_score=4.86,
            product_score=4.88,
            logistics_score=4.82,
            service_score=4.90,
            source="http",
        )
        second = await repo.upsert_score(
            shop_id="shop-1",
            metric_date=metric_date,
            total_score=4.88,
            product_score=4.89,
            logistics_score=4.83,
            service_score=4.91,
            source="browser",
        )

        count = (
            await session.execute(
                select(func.count(ShopDashboardScore.id)).where(
                    ShopDashboardScore.shop_id == "shop-1",
                    ShopDashboardScore.metric_date == metric_date,
                )
            )
        ).scalar_one()

        assert first.id == second.id
        assert second.total_score == 4.88
        assert second.source == "browser"
        assert count == 1


async def test_replace_reviews_by_shop_and_date(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        metric_date = date(2026, 3, 3)

        await repo.replace_reviews(
            shop_id="shop-1",
            metric_date=metric_date,
            reviews=[
                {
                    "review_id": "r-1",
                    "content": "bad package",
                    "is_replied": False,
                    "source": "http",
                },
                {
                    "review_id": "r-2",
                    "content": "late delivery",
                    "is_replied": True,
                    "source": "http",
                },
            ],
        )
        await repo.replace_reviews(
            shop_id="shop-1",
            metric_date=metric_date,
            reviews=[
                {
                    "review_id": "r-2",
                    "content": "late delivery",
                    "is_replied": True,
                    "source": "browser",
                },
                {
                    "review_id": "r-3",
                    "content": "service issue",
                    "is_replied": False,
                    "source": "browser",
                },
            ],
        )

        rows = (
            (
                await session.execute(
                    select(ShopDashboardReview)
                    .where(
                        ShopDashboardReview.shop_id == "shop-1",
                        ShopDashboardReview.metric_date == metric_date,
                    )
                    .order_by(ShopDashboardReview.review_id)
                )
            )
            .scalars()
            .all()
        )

        assert len(rows) == 2
        assert [row.review_id for row in rows] == ["r-2", "r-3"]
        assert rows[0].source == "browser"


async def test_replace_violations_by_shop_and_date(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        metric_date = date(2026, 3, 3)

        await repo.replace_violations(
            shop_id="shop-1",
            metric_date=metric_date,
            violations=[
                {
                    "violation_id": "v-1",
                    "violation_type": "A",
                    "description": "description-a",
                    "score": 4,
                    "source": "http",
                },
                {
                    "violation_id": "v-2",
                    "violation_type": "B",
                    "description": "description-b",
                    "score": 2,
                    "source": "http",
                },
            ],
        )
        await repo.replace_violations(
            shop_id="shop-1",
            metric_date=metric_date,
            violations=[
                {
                    "violation_id": "v-2",
                    "violation_type": "B",
                    "description": "description-b",
                    "score": 3,
                    "source": "llm",
                },
                {
                    "violation_id": "v-3",
                    "violation_type": "A",
                    "description": "description-c",
                    "score": 1,
                    "source": "llm",
                },
            ],
        )

        rows = (
            (
                await session.execute(
                    select(ShopDashboardViolation)
                    .where(
                        ShopDashboardViolation.shop_id == "shop-1",
                        ShopDashboardViolation.metric_date == metric_date,
                    )
                    .order_by(ShopDashboardViolation.violation_id)
                )
            )
            .scalars()
            .all()
        )

        assert len(rows) == 2
        assert [row.violation_id for row in rows] == ["v-2", "v-3"]
        assert rows[0].score == 3
        assert rows[0].source == "llm"


async def test_upsert_cold_metrics_by_shop_date_and_reason(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        metric_date = date(2026, 3, 3)

        first = await repo.upsert_cold_metrics(
            shop_id="shop-1",
            metric_date=metric_date,
            reason="cold_metric",
            violations_detail=[{"id": "v-1"}],
            arbitration_detail=[{"id": "a-1"}],
            dsr_trend=[{"date": "2026-03-03", "score": 4.7}],
            source="llm",
        )
        second = await repo.upsert_cold_metrics(
            shop_id="shop-1",
            metric_date=metric_date,
            reason="cold_metric",
            violations_detail=[{"id": "v-2"}],
            arbitration_detail=[{"id": "a-2"}],
            dsr_trend=[{"date": "2026-03-03", "score": 4.8}],
            source="llm",
        )

        count = (
            await session.execute(
                select(func.count(ShopDashboardColdMetric.id)).where(
                    ShopDashboardColdMetric.shop_id == "shop-1",
                    ShopDashboardColdMetric.metric_date == metric_date,
                    ShopDashboardColdMetric.reason == "cold_metric",
                )
            )
        ).scalar_one()

        assert first.id == second.id
        assert second.violations_detail == [{"id": "v-2"}]
        assert count == 1


async def test_build_agent_context_includes_existing_cold_metrics(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        metric_date = date(2026, 3, 3)

        await repo.upsert_score(
            shop_id="shop-1",
            metric_date=metric_date,
            total_score=4.86,
            product_score=4.88,
            logistics_score=4.82,
            service_score=4.90,
            source="http",
        )
        await repo.replace_violations(
            shop_id="shop-1",
            metric_date=metric_date,
            violations=[
                {
                    "violation_id": "v-1",
                    "violation_type": "A",
                    "description": "description-a",
                    "score": 4,
                    "source": "http",
                }
            ],
        )
        await repo.upsert_cold_metrics(
            shop_id="shop-1",
            metric_date=metric_date,
            reason="cold_metric",
            violations_detail=[{"id": "v-llm"}],
            arbitration_detail=[{"id": "a-llm"}],
            dsr_trend=[{"date": "2026-03-03", "score": 4.7}],
            source="llm",
        )
        await session.commit()

        context = await repo.build_agent_context(
            shop_id="shop-1",
            metric_date=metric_date,
            reason="cold_metric",
        )

        assert context["total_score"] == 4.86
        assert context["violations"]["waiting_list"][0]["id"] == "v-1"
        assert context["violations_detail"] == [{"id": "v-llm"}]
