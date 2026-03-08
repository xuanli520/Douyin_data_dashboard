from datetime import date

import pytest
from sqlalchemy import select

from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
    ScrapingRuleStatus,
    TargetType,
)
from src.domains.data_source.models import DataSource, ScrapingRule
from src.domains.shop_dashboard.models import ShopDashboardViolation
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

    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)

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

    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)

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

    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)

    with pytest.raises(ScrapingFailedException):
        await module._load_runtime_config(
            data_source_id=data_source.id if data_source.id is not None else 0,
            rule_id=rule.id if rule.id is not None else 0,
            execution_id="exec-empty-api-groups",
        )


async def test_load_runtime_config_reads_storage_state_from_extra_config(
    test_db, monkeypatch
):
    storage_state = {
        "cookies": [{"name": "sid", "value": "token-from-db"}],
        "origins": [],
    }
    async with test_db() as db_session:
        data_source = DataSource(
            name="runtime-storage-data-source",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
            extra_config={
                "shop_dashboard_login_state": {
                    "storage_state": storage_state,
                    "credentials": {
                        "api_key": "test_key",
                        "api_key_password": "test_password",
                    },
                }
            },
        )
        db_session.add(data_source)
        await db_session.flush()

        rule = ScrapingRule(
            name="runtime-storage-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            status=ScrapingRuleStatus.ACTIVE,
            schedule={"cron": "0 3 * * *"},
        )
        db_session.add(rule)
        await db_session.commit()

    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)

    runtime = await module._load_runtime_config(
        data_source_id=data_source.id if data_source.id is not None else 0,
        rule_id=rule.id if rule.id is not None else 0,
        execution_id="exec-storage-state",
    )

    assert runtime.storage_state == storage_state
    assert runtime.cookies["sid"] == "token-from-db"


async def test_persist_result_reads_violations_from_raw_waiting_list(
    test_db, monkeypatch
):
    monkeypatch.setattr(module.session, "async_session_factory", test_db, raising=False)

    runtime = ShopDashboardRuntimeConfig(
        shop_id="shop-raw-violation",
        cookies={},
        proxy=None,
        timeout=15,
        retry_count=3,
        rate_limit=100,
        granularity="DAY",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=1,
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
        execution_id="exec-raw-violation",
        fallback_chain=("http",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
    )

    payload = {
        "source": "script",
        "total_score": 4.9,
        "product_score": 4.8,
        "logistics_score": 4.7,
        "service_score": 4.6,
        "reviews": {"summary": {}, "items": []},
        "violations": {"summary": {}, "waiting_list": []},
        "raw": {
            "violations": {
                "waiting_list": {
                    "code": 0,
                    "data": {
                        "waiting_list": [
                            {
                                "ticketId": "ticket-raw-1",
                                "penalty_type": "bad_behavior",
                                "reason": "raw violation",
                                "deductScore": "6",
                            }
                        ]
                    },
                }
            }
        },
    }

    await module._persist_result(runtime, "2026-03-03", payload)

    async with test_db() as db_session:
        stmt = select(ShopDashboardViolation).where(
            ShopDashboardViolation.shop_id == "shop-raw-violation",
            ShopDashboardViolation.metric_date == date(2026, 3, 3),
        )
        rows = (await db_session.execute(stmt)).scalars().all()

    assert len(rows) == 1
    assert rows[0].violation_id == "ticket-raw-1"
    assert rows[0].violation_type == "bad_behavior"
    assert rows[0].score == 6


def test_sync_shop_dashboard_materializes_storage_state_before_collection(monkeypatch):
    runtime = ShopDashboardRuntimeConfig(
        shop_id="shop-1",
        cookies={},
        proxy=None,
        timeout=15,
        retry_count=3,
        rate_limit=100,
        granularity="DAY",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=1,
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
        execution_id="exec-materialize",
        fallback_chain=("http",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
        account_id="acct-1",
        storage_state={
            "cookies": [{"name": "sid", "value": "token-from-db"}],
            "origins": [],
        },
    )

    class _FakeRedis:
        def hset(self, _key, mapping=None, **_kwargs):
            _ = mapping
            return None

        def expire(self, _key, _seconds):
            return None

    class _FakeIdempotencyHelper:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_cached_result(self, _key):
            return None

        def acquire_lock(self, _key, ttl):
            _ = ttl
            return "token"

        def cache_result(self, _key, _result, ttl=86400):
            _ = ttl
            return None

        def release_lock(self, _key, _token):
            return None

    calls = {"save": 0, "collect": 0}

    class _FakeStateStore:
        def __init__(self, base_dir=None):
            _ = base_dir
            self._state = {}

        def save(self, account_id, state):
            calls["save"] += 1
            self._state[account_id] = state
            return None

        def load_cookie_mapping(self, account_id):
            state = self._state.get(account_id, {})
            cookies = state.get("cookies", [])
            mapping = {}
            for item in cookies:
                mapping[item["name"]] = item["value"]
            return mapping

    class _FakeLockManager:
        def __init__(self, redis_client=None):
            self.redis_client = redis_client

    class _FakeLoginStateManager:
        def __init__(self, state_store, redis_client=None):
            self.state_store = state_store
            self.redis_client = redis_client

    async def _fake_load_runtime_config(**_kwargs):
        return runtime

    async def _fake_persist_result(_runtime, _metric_date, _payload):
        return None

    def _fake_collect_one_day(
        runtime_config,
        metric_date,
        _browser,
        *,
        lock_manager,
        state_store,
        login_state_manager,
    ):
        _ = metric_date
        _ = lock_manager
        _ = state_store
        _ = login_state_manager
        calls["collect"] += 1
        assert runtime_config.cookies["sid"] == "token-from-db"
        return {
            "status": "success",
            "shop_id": runtime.shop_id,
            "metric_date": "2026-03-03",
            "rule_id": runtime.rule_id,
            "execution_id": runtime.execution_id,
            "source": "script",
            "total_score": 0.0,
            "product_score": 0.0,
            "logistics_score": 0.0,
            "service_score": 0.0,
            "reviews": {"summary": {}, "items": []},
            "violations": {"summary": {}, "waiting_list": []},
            "raw": {},
        }

    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        type("_Publisher", (), {"redis_db_frame": _FakeRedis()})(),
        raising=False,
    )
    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(module, "BrowserScraper", lambda: object())
    monkeypatch.setattr(module, "_load_runtime_config", _fake_load_runtime_config)
    monkeypatch.setattr(module, "_collect_one_day", _fake_collect_one_day)
    monkeypatch.setattr(module, "_persist_result", _fake_persist_result)
    monkeypatch.setattr(
        module, "_resolve_metric_dates", lambda _runtime: ["2026-03-03"]
    )

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=1,
        execution_id="exec-materialize",
    )

    assert result["status"] == "success"
    assert calls["save"] == 1
    assert calls["collect"] == 1


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

    class _FakeLockManager:
        def acquire_shop_lock(self, _shop_id, ttl_seconds=None):  # noqa: ARG002
            return "shop-token"

        def release_shop_lock(self, _shop_id, _token):
            return None

        def acquire_account_lock(self, _account_id, ttl_seconds=None):  # noqa: ARG002
            return "account-token"

        def release_account_lock(self, _account_id, _token):
            return None

    class _FakeStore:
        def __init__(self, base_dir=None):  # noqa: ARG002
            pass

        def load_cookie_mapping(self, _account_id):
            return {}

    class _FakeLoginStateManager:
        def __init__(self, state_store):
            self._state_store = state_store

        async def check_and_refresh(self, _account_id):
            return True

    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStore)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)

    payload = module._collect_one_day(runtime, "2026-03-03", _FakeBrowser())

    assert payload["source"] == "browser"
    assert call_order == ["browser"]


def test_collection_uses_shop_lock_refresh_uses_account_lock(monkeypatch):
    runtime = ShopDashboardRuntimeConfig(
        shop_id="shop-1",
        cookies={"sid": "old"},
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
        execution_id="exec-locks",
        fallback_chain=("browser",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
        account_id="acct-1",
    )

    calls = {"shop": 0, "account": 0}

    class _FakeHttpScraper:
        def __init__(self, **_kwargs):
            pass

        def close(self):
            return None

    class _FakeBrowser:
        def retry_http(self, _http_scraper, _runtime, _metric_date):
            return {"source": "browser", "total_score": 4.8}

    class _FakeLockManager:
        def acquire_shop_lock(self, _shop_id, ttl_seconds=None):  # noqa: ARG002
            calls["shop"] += 1
            return "shop-token"

        def release_shop_lock(self, _shop_id, _token):
            return None

        def acquire_account_lock(self, _account_id, ttl_seconds=None):  # noqa: ARG002
            calls["account"] += 1
            return "account-token"

        def release_account_lock(self, _account_id, _token):
            return None

    class _FakeStore:
        def __init__(self, base_dir=None):  # noqa: ARG002
            pass

        def load_cookie_mapping(self, _account_id):
            return {"sid": "from_state"}

    class _FakeLoginStateManager:
        def __init__(self, state_store):
            self._state_store = state_store

        async def check_and_refresh(self, _account_id):
            return True

    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStore)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)

    payload = module._collect_one_day(runtime, "2026-03-03", _FakeBrowser())

    assert payload["source"] == "browser"
    assert calls["shop"] == 1
    assert calls["account"] == 1
    assert runtime.cookies["sid"] == "from_state"


def test_sync_shop_dashboard_reuses_shared_helpers_across_metric_dates(monkeypatch):
    runtime = ShopDashboardRuntimeConfig(
        shop_id="shop-1",
        cookies={"sid": "v"},
        proxy=None,
        timeout=15,
        retry_count=3,
        rate_limit=100,
        granularity="DAY",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=2,
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
        execution_id="exec-shared-helpers",
        fallback_chain=("http",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
        account_id="acct-1",
    )
    helper_ids: list[tuple[int, int, int]] = []

    class _FakeLockManager:
        def __init__(self, redis_client=None):  # noqa: ARG002
            self.redis_client = redis_client

    class _FakeStateStore:
        def __init__(self, base_dir=None):  # noqa: ARG002
            self.base_dir = base_dir

    class _FakeLoginStateManager:
        def __init__(self, state_store, redis_client=None):  # noqa: ARG002
            self.state_store = state_store
            self.redis_client = redis_client

    async def _fake_load_runtime_config(**_kwargs):
        return runtime

    async def _fake_persist_result(_runtime, _metric_date, _payload):
        return None

    def _fake_collect_one_day(
        _runtime,
        metric_date,
        _browser,
        *,
        lock_manager,
        state_store,
        login_state_manager,
    ):
        helper_ids.append((id(lock_manager), id(state_store), id(login_state_manager)))
        return {
            "status": "success",
            "shop_id": runtime.shop_id,
            "metric_date": metric_date,
            "rule_id": runtime.rule_id,
            "execution_id": runtime.execution_id,
            "source": "script",
            "total_score": 0.0,
            "product_score": 0.0,
            "logistics_score": 0.0,
            "service_score": 0.0,
            "reviews": {"summary": {}, "items": []},
            "violations": {"summary": {}, "waiting_list": []},
            "raw": {},
        }

    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(module, "_load_runtime_config", _fake_load_runtime_config)
    monkeypatch.setattr(
        module,
        "_resolve_metric_dates",
        lambda _runtime: ["2026-03-03", "2026-03-04"],
    )
    monkeypatch.setattr(module, "_collect_one_day", _fake_collect_one_day)
    monkeypatch.setattr(module, "_persist_result", _fake_persist_result)

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=1,
        execution_id="exec-shared-helpers",
    )

    assert result["status"] == "success"
    assert len(helper_ids) == 2
    assert helper_ids[0] == helper_ids[1]
