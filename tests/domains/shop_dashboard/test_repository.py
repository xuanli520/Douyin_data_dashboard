from datetime import date

from sqlalchemy import func, select

from src.domains.shop_dashboard.models import (
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
