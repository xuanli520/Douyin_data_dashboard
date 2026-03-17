import asyncio
from datetime import date

from sqlalchemy import func, select

from src.domains.shop_dashboard.models import ShopDashboardScore
from src.domains.shop_dashboard.repository import ShopDashboardRepository


async def test_upsert_score_is_atomic_under_concurrency(test_db):
    metric_date = date(2026, 3, 16)

    async def write_once(total_score: float, source: str) -> None:
        async with test_db() as session:
            repo = ShopDashboardRepository(session)
            await repo.upsert_score(
                shop_id="1001",
                metric_date=metric_date,
                total_score=total_score,
                product_score=4.8,
                logistics_score=4.7,
                service_score=4.9,
                bad_behavior_score=0.0,
                shop_name="demo-shop",
                source=source,
            )
            await session.commit()

    await asyncio.gather(
        write_once(4.81, "script"),
        write_once(4.86, "http"),
        write_once(4.92, "browser"),
    )

    async with test_db() as session:
        count = (
            await session.execute(
                select(func.count(ShopDashboardScore.id)).where(
                    ShopDashboardScore.shop_id == "1001",
                    ShopDashboardScore.metric_date == metric_date,
                )
            )
        ).scalar_one()
        row = (
            await session.execute(
                select(ShopDashboardScore).where(
                    ShopDashboardScore.shop_id == "1001",
                    ShopDashboardScore.metric_date == metric_date,
                )
            )
        ).scalar_one()

    assert count == 1
    assert row.total_score in {4.81, 4.86, 4.92}
