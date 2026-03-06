import pytest

from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
    ScrapingRuleStatus,
    TargetType,
)
from src.domains.data_source.models import DataSource, ScrapingRule
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.collection import douyin_shop_dashboard as module
from src.tasks.exceptions import ScrapingFailedException


async def test_load_runtime_config_rejects_inactive_data_source(test_db, monkeypatch):
    async with test_db() as db_session:
        data_source = DataSource(
            name="inactive-runtime-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.INACTIVE,
        )
        db_session.add(data_source)
        await db_session.flush()

        rule = ScrapingRule(
            name="active-runtime-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            status=ScrapingRuleStatus.ACTIVE,
            schedule={"cron": "0 3 * * *"},
        )
        db_session.add(rule)
        await db_session.commit()

    monkeypatch.setattr(module, "async_session_factory", test_db, raising=False)

    with pytest.raises(ScrapingFailedException):
        await module._load_runtime_config(
            data_source_id=data_source.id if data_source.id is not None else 0,
            rule_id=rule.id if rule.id is not None else 0,
            execution_id="exec-inactive-data-source",
        )


async def test_load_runtime_config_rejects_inactive_rule(test_db, monkeypatch):
    async with test_db() as db_session:
        data_source = DataSource(
            name="active-runtime-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        db_session.add(data_source)
        await db_session.flush()

        rule = ScrapingRule(
            name="inactive-runtime-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            status=ScrapingRuleStatus.INACTIVE,
            schedule={"cron": "0 3 * * *"},
        )
        db_session.add(rule)
        await db_session.commit()

    monkeypatch.setattr(module, "async_session_factory", test_db, raising=False)

    with pytest.raises(ScrapingFailedException):
        await module._load_runtime_config(
            data_source_id=data_source.id if data_source.id is not None else 0,
            rule_id=rule.id if rule.id is not None else 0,
            execution_id="exec-inactive-rule",
        )


async def test_load_runtime_config_rejects_empty_api_groups(test_db, monkeypatch):
    async with test_db() as db_session:
        data_source = DataSource(
            name="runtime-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        db_session.add(data_source)
        await db_session.flush()

        rule = ScrapingRule(
            name="runtime-traffic-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            status=ScrapingRuleStatus.ACTIVE,
            target_type=TargetType.TRAFFIC,
            metrics=[],
            schedule={"cron": "0 3 * * *"},
        )
        db_session.add(rule)
        await db_session.commit()

    monkeypatch.setattr(module, "async_session_factory", test_db, raising=False)

    with pytest.raises(ScrapingFailedException):
        await module._load_runtime_config(
            data_source_id=data_source.id if data_source.id is not None else 0,
            rule_id=rule.id if rule.id is not None else 0,
            execution_id="exec-empty-api-groups",
        )


def test_collect_one_day_runs_fallback_chain_in_declared_order(monkeypatch):
    runtime = ShopDashboardRuntimeConfig(
        shop_id="shop-1",
        cookies={"sessionid": "token"},
        proxy=None,
        timeout=15,
        retry_count=3,
        rate_limit=100,
        granularity="DAY",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=3,
        data_latency="T+1",
        target_type="SHOP_OVERVIEW",
        metrics=[],
        dimensions=[],
        filters={},
        top_n=None,
        include_long_tail=False,
        session_level=False,
        dedupe_key=None,
        rule_id=1,
        execution_id="exec-fallback-order",
        fallback_chain=("browser", "http", "llm"),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
    )
    call_order: list[str] = []

    class _FakeHttpScraper:
        def __init__(self, **_kwargs):
            pass

        def fetch_dashboard_with_context(self, _runtime, _metric_date):
            call_order.append("http")
            raise ScrapingFailedException("http failed")

        def close(self):
            return None

    class _FakeBrowser:
        def retry_http(self, _http_scraper, _runtime, _metric_date):
            call_order.append("browser")
            return {"source": "browser", "total_score": 4.8}

    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)

    payload = module._collect_one_day(runtime, "2026-03-03", _FakeBrowser())

    assert payload["source"] == "browser"
    assert call_order == ["browser"]
