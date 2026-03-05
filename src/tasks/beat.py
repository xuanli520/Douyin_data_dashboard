from __future__ import annotations

import asyncio
import time

from sqlalchemy import select

from src.domains.data_source.enums import ScrapingRuleStatus
from src.domains.data_source.models import ScrapingRule
from src.tasks.collection.douyin_orders import sync_orders
from src.tasks.collection.douyin_products import sync_products
from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard
from src.tasks.funboost_compat import ApsJobAdder
from src.session import async_session_factory


def register_jobs() -> None:
    orders_job = ApsJobAdder(sync_orders, job_store_kind="redis")
    orders_job.add_push_job(
        trigger="cron",
        hour=2,
        minute=0,
        kwargs={"shop_id": "all", "date": "yesterday"},
        id="daily_collection_orders_sync",
    )

    products_job = ApsJobAdder(sync_products, job_store_kind="redis")
    products_job.add_push_job(
        trigger="cron",
        hour=2,
        minute=30,
        kwargs={"shop_id": "all", "date": "yesterday"},
        id="daily_collection_products_sync",
    )

    dashboard_job = ApsJobAdder(sync_shop_dashboard, job_store_kind="redis")
    for rule in _load_active_shop_dashboard_rules():
        schedule = dict(rule.get("schedule") or {})
        cron_expression = schedule.get("cron")
        cron_parts = _parse_cron(cron_expression)
        if cron_parts is None:
            continue
        dashboard_job.add_push_job(
            trigger="cron",
            minute=cron_parts["minute"],
            hour=cron_parts["hour"],
            day=cron_parts["day"],
            month=cron_parts["month"],
            day_of_week=cron_parts["day_of_week"],
            kwargs={
                "data_source_id": rule["data_source_id"],
                "rule_id": rule["rule_id"],
                "execution_id": f"cron_rule_{rule['rule_id']}",
                "triggered_by": None,
            },
            id=f"scraping_rule_{rule['rule_id']}_collection_shop_dashboard_sync",
        )


def _parse_cron(cron_expression: str | None) -> dict[str, str] | None:
    if not cron_expression:
        return None
    parts = [part.strip() for part in cron_expression.split(" ") if part.strip()]
    if len(parts) != 5:
        return None
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


def _load_active_shop_dashboard_rules() -> list[dict]:
    return asyncio.run(_load_active_shop_dashboard_rules_async())


async def _load_active_shop_dashboard_rules_async() -> list[dict]:
    if async_session_factory is None:
        return []
    async with async_session_factory() as session:
        stmt = select(ScrapingRule).where(
            ScrapingRule.status == ScrapingRuleStatus.ACTIVE,
            ScrapingRule.schedule.is_not(None),
        )
        rows = list((await session.execute(stmt)).scalars().all())
        return [
            {
                "rule_id": row.id if row.id is not None else 0,
                "data_source_id": row.data_source_id,
                "schedule": row.schedule or {},
            }
            for row in rows
            if row.id is not None
        ]


def main() -> None:
    register_jobs()
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
