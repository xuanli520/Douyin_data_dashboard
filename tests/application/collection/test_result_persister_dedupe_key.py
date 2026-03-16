import logging
from datetime import date
from types import SimpleNamespace

from sqlalchemy import func, select

from src.application.collection.result_persister import CollectionResultPersister
from src.domains.shop_dashboard.models import ShopDashboardScore


async def test_persist_should_dedupe_same_logical_shop_key(test_db):
    async with test_db() as session:
        persister = CollectionResultPersister()
        runtime = SimpleNamespace(shop_id="0001001")

        await persister.persist(
            session=session,
            runtime=runtime,
            metric_date="2026-03-16",
            payload={
                "shop_id": "0001001",
                "target_shop_id": "0001001",
                "actual_shop_id": "0001001",
                "total_score": 80.0,
                "product_score": 82.0,
                "logistics_score": 78.0,
                "service_score": 81.0,
                "bad_behavior_score": 0.0,
                "shop_name": "shop-a",
                "source": "script",
                "reviews": {"items": []},
                "violations": {"waiting_list": []},
                "raw": {},
            },
        )

        await persister.persist(
            session=session,
            runtime=runtime,
            metric_date="2026-03-16",
            payload={
                "shop_id": "1001",
                "target_shop_id": "1001",
                "actual_shop_id": "001001",
                "total_score": 90.0,
                "product_score": 91.0,
                "logistics_score": 89.0,
                "service_score": 92.0,
                "bad_behavior_score": 1.0,
                "shop_name": "shop-b",
                "source": "http",
                "reviews": {"items": []},
                "violations": {"waiting_list": []},
                "raw": {},
            },
        )

        count = (
            await session.execute(
                select(func.count(ShopDashboardScore.id)).where(
                    ShopDashboardScore.metric_date == date(2026, 3, 16)
                )
            )
        ).scalar_one()
        row = (
            await session.execute(
                select(ShopDashboardScore).where(
                    ShopDashboardScore.metric_date == date(2026, 3, 16)
                )
            )
        ).scalar_one()

    assert count == 1
    assert row.shop_id == "1001"
    assert float(row.total_score) == 90.0
    assert row.shop_name == "shop-b"


async def test_persist_should_log_structured_fields_when_shop_mismatch(test_db, caplog):
    async with test_db() as session:
        caplog.set_level(logging.WARNING)
        persister = CollectionResultPersister()

        await persister.persist(
            session=session,
            runtime=SimpleNamespace(shop_id="1001"),
            metric_date="2026-03-16",
            payload={
                "shop_id": "2002",
                "target_shop_id": "1001",
                "actual_shop_id": "2002",
                "total_score": 0.0,
                "product_score": 0.0,
                "logistics_score": 0.0,
                "service_score": 0.0,
                "bad_behavior_score": 0.0,
                "source": "script",
                "reviews": {"items": []},
                "violations": {"waiting_list": []},
                "raw": {},
            },
        )

        count = (
            await session.execute(
                select(func.count(ShopDashboardScore.id)).where(
                    ShopDashboardScore.metric_date == date(2026, 3, 16)
                )
            )
        ).scalar_one()

    assert count == 0
    assert "target_shop_id=1001" in caplog.text
    assert "actual_shop_id=2002" in caplog.text
    assert "resolved_shop_id=2002" in caplog.text
    assert "metric_date=2026-03-16" in caplog.text
