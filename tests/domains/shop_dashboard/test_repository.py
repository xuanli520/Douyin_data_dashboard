from datetime import date

from sqlalchemy import func, select

from src.domains.shop_dashboard.models import ShopDashboardScore
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
            shop_name="shop-old",
            source="browser_agent",
        )
        second = await repo.upsert_score(
            shop_id="shop-1",
            metric_date=metric_date,
            total_score=4.88,
            product_score=4.89,
            logistics_score=4.83,
            service_score=4.91,
            shop_name="demo-shop",
            source="browser_agent",
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
        assert second.shop_name == "demo-shop"
        assert second.source == "browser_agent"
        assert count == 1


async def test_upsert_score_accepts_optional_bad_behavior_score(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        metric_date = date(2026, 3, 3)

        row = await repo.upsert_score(
            shop_id="shop-1",
            metric_date=metric_date,
            total_score=4.86,
            product_score=4.88,
            logistics_score=4.82,
            service_score=4.90,
            bad_behavior_score=0.0,
            source="browser_agent",
        )

        assert row.total_score == 4.86
        assert row.bad_behavior_score == 0.0
        assert row.source == "browser_agent"


async def test_upsert_score_keeps_bad_behavior_score_nullable(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        metric_date = date(2026, 3, 3)

        row = await repo.upsert_score(
            shop_id="shop-1",
            metric_date=metric_date,
            total_score=4.86,
            product_score=4.88,
            logistics_score=4.82,
            service_score=4.90,
            bad_behavior_score=None,
            source="browser_agent",
        )

        assert row.bad_behavior_score is None


async def test_upsert_score_preserves_degraded_zero_overwrite(test_db):
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
            source="browser_agent",
        )
        second = await repo.upsert_score(
            shop_id="shop-1",
            metric_date=metric_date,
            total_score=0.0,
            product_score=0.0,
            logistics_score=0.0,
            service_score=0.0,
            source="degraded",
        )

        assert first.id == second.id
        assert second.total_score == 0.0
        assert second.product_score == 0.0
        assert second.logistics_score == 0.0
        assert second.service_score == 0.0
        assert second.source == "degraded"


async def test_build_agent_context_returns_score_snapshot(test_db):
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
            bad_behavior_score=0.1,
            source="browser_agent",
        )
        await session.commit()

        context = await repo.build_agent_context(
            shop_id="shop-1",
            metric_date=metric_date,
            reason="retry",
        )

        assert context == {
            "shop_id": "shop-1",
            "metric_date": "2026-03-03",
            "total_score": 4.86,
            "product_score": 4.88,
            "logistics_score": 4.82,
            "service_score": 4.9,
            "bad_behavior_score": 0.1,
            "raw": {},
        }


async def test_list_display_materials_returns_grouped_daily_scores(test_db):
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
            bad_behavior_score=0.2,
            source="browser_agent",
        )
        await session.commit()

        items = await repo.list_display_materials(
            shop_id="shop-1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 5),
        )

        assert items == [
            {
                "shop_id": "shop-1",
                "shop_name": "",
                "metric_date": "2026-03-03",
                "source": "browser_agent",
                "status": "success",
                "reason": None,
                "error_code": None,
                "total_score": 4.86,
                "product_score": 4.88,
                "logistics_score": 4.82,
                "service_score": 4.9,
                "bad_behavior_score": 0.2,
            }
        ]


async def test_list_display_materials_returns_empty_without_scores(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)

        items = await repo.list_display_materials(
            shop_id="shop-1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 3),
        )

        assert items == []
