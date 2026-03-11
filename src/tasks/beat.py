from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy import select

from src import session
from src.config import get_settings
from src.domains.data_source.enums import DataSourceStatus, ScrapingRuleStatus
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.tasks.collection.douyin_shop_agent import sync_shop_dashboard_agent
from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard
from src.tasks.funboost_compat import ApsJobAdder


def register_jobs() -> None:
    dashboard_rules = _load_active_shop_dashboard_rules()
    fixed_rule = dashboard_rules[0] if dashboard_rules else None
    if fixed_rule is not None:
        dashboard_job = ApsJobAdder(sync_shop_dashboard, job_store_kind="redis")
        dashboard_job.add_push_job(
            trigger="cron",
            minute=0,
            hour=2,
            kwargs=_build_dashboard_job_kwargs(fixed_rule, execution_tag="full_sync"),
            id="shop_dashboard_full_sync",
        )
        dashboard_job.add_push_job(
            trigger="cron",
            minute=0,
            hour="6,10,14,18",
            kwargs=_build_dashboard_job_kwargs(
                fixed_rule,
                execution_tag="incremental_sync",
            ),
            id="shop_dashboard_incremental_sync",
        )
        dashboard_job.add_push_job(
            trigger="cron",
            minute="*/30",
            kwargs=_build_dashboard_job_kwargs(
                fixed_rule,
                execution_tag="cookie_health_check",
            ),
            id="shop_dashboard_cookie_health_check",
        )

        shop_id = str(fixed_rule.get("shop_id") or "").strip()
        if shop_id:
            agent_job = ApsJobAdder(sync_shop_dashboard_agent, job_store_kind="redis")
            agent_job.add_push_job(
                trigger="cron",
                minute="*/10",
                kwargs={
                    "shop_id": shop_id,
                    "reason": "agent_backfill",
                    "triggered_by": None,
                },
                id="shop_dashboard_agent_backfill",
            )


def _build_dashboard_job_kwargs(
    rule: dict[str, Any], execution_tag: str
) -> dict[str, Any]:
    return {
        "data_source_id": int(rule["data_source_id"]),
        "rule_id": int(rule["rule_id"]),
        "execution_id": f"cron_{execution_tag}_{rule['rule_id']}",
        "triggered_by": None,
        "granularity": rule.get("granularity"),
        "timezone": str(rule.get("timezone") or "Asia/Shanghai"),
        "incremental_mode": rule.get("incremental_mode"),
        "data_latency": rule.get("data_latency"),
    }


def _load_active_shop_dashboard_rules() -> list[dict]:
    return asyncio.run(_load_active_shop_dashboard_rules_async())


async def _load_active_shop_dashboard_rules_async() -> list[dict]:
    session_factory = session.async_session_factory
    if session_factory is None:
        return []
    async with session_factory() as db_session:
        stmt = (
            select(ScrapingRule, DataSource.shop_id)
            .join(DataSource, ScrapingRule.data_source_id == DataSource.id)
            .where(
                ScrapingRule.status == ScrapingRuleStatus.ACTIVE,
                DataSource.status == DataSourceStatus.ACTIVE,
            )
        )
        rows = list((await db_session.execute(stmt)).all())
        return [
            {
                "rule_id": rule.id if rule.id is not None else 0,
                "data_source_id": rule.data_source_id,
                "shop_id": shop_id,
                "timezone": str(rule.timezone or "Asia/Shanghai"),
                "granularity": str(
                    rule.granularity.value
                    if hasattr(rule.granularity, "value")
                    else rule.granularity
                ),
                "incremental_mode": str(
                    rule.incremental_mode.value
                    if hasattr(rule.incremental_mode, "value")
                    else rule.incremental_mode
                ),
                "data_latency": str(
                    rule.data_latency.value
                    if hasattr(rule.data_latency, "value")
                    else rule.data_latency
                ),
            }
            for rule, shop_id in rows
            if rule.id is not None
        ]


def _init_scheduler_db() -> None:
    settings = get_settings()
    asyncio.run(session.init_db(settings.db.url, settings.db.echo))


def main() -> None:
    _init_scheduler_db()
    register_jobs()
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
