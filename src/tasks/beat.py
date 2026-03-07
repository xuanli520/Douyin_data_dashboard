from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from src import session
from src.config import get_settings
from src.domains.data_source.enums import DataSourceStatus, ScrapingRuleStatus
from src.domains.data_source.models import DataSource, ScrapingRule
from src.tasks.collection.douyin_shop_agent import sync_shop_dashboard_agent
from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard
from src.tasks.funboost_compat import ApsJobAdder


def register_jobs() -> None:
    dashboard_rules = _load_active_shop_dashboard_rules()
    dashboard_job = ApsJobAdder(sync_shop_dashboard, job_store_kind="redis")
    for rule in dashboard_rules:
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

    fixed_rule = dashboard_rules[0] if dashboard_rules else None
    if fixed_rule is not None:
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

        agent_job = ApsJobAdder(sync_shop_dashboard_agent, job_store_kind="redis")
        agent_job.add_push_job(
            trigger="cron",
            minute="*/10",
            kwargs={
                "shop_id": fixed_rule.get("shop_id") or "all",
                "date": datetime.now(UTC).date().isoformat(),
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
    }


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
    session_factory = session.async_session_factory
    if session_factory is None:
        return []
    async with session_factory() as db_session:
        stmt = select(ScrapingRule).where(
            ScrapingRule.status == ScrapingRuleStatus.ACTIVE,
            ScrapingRule.schedule.is_not(None),
            ScrapingRule.data_source.has(DataSource.status == DataSourceStatus.ACTIVE),
        )
        rows = list((await db_session.execute(stmt)).scalars().all())
        return [
            {
                "rule_id": row.id if row.id is not None else 0,
                "data_source_id": row.data_source_id,
                "shop_id": None,
                "schedule": row.schedule or {},
            }
            for row in rows
            if row.id is not None
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
