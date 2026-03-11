from types import SimpleNamespace

import pytest

from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.collection import douyin_shop_dashboard as module
from src.tasks.exceptions import ScrapingFailedException


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
        return "token-1"

    def cache_result(self, _key, _result, ttl=86400):
        _ = ttl
        return None

    def release_lock(self, _key, _token):
        return None


class _FakeHttpScraper:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        return None

    def fetch_dashboard_with_context(self, _runtime, _metric_date):
        raise ScrapingFailedException("http failed")

    def close(self):
        return None


class _FakeBrowserScraper:
    def retry_http(self, _scraper, _runtime, _metric_date):
        raise ScrapingFailedException("browser failed")


def _build_runtime() -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_id="shop-1",
        cookies={"sessionid": "token"},
        proxy=None,
        timeout=15,
        retry_count=3,
        rate_limit=100,
        granularity="DAY",
        time_range={"start": "2026-03-01", "end": "2026-03-01"},
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
        rule_id=2,
        execution_id="exec-1",
        fallback_chain=("http", "browser", "llm"),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
    )


async def _fake_runtime_loader(**_kwargs):
    return _build_runtime()


async def _fake_persist(*_args, **_kwargs):
    return None


async def _fake_empty_plan_runtime_loader(**_kwargs):
    runtime = _build_runtime()
    runtime.shop_id = ""
    runtime.filters = {"shop_id": []}
    return runtime


def test_sync_shop_dashboard_fails_when_no_target_shop(monkeypatch):
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "_load_runtime_config", _fake_empty_plan_runtime_loader)

    with pytest.raises(ScrapingFailedException, match="No target shops resolved"):
        module.sync_shop_dashboard(
            data_source_id=1,
            rule_id=2,
            execution_id="exec-empty-plan",
        )


def test_sync_shop_dashboard_http_browser_fail_then_llm_patch(monkeypatch):
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
    monkeypatch.setattr(module, "BrowserScraper", _FakeBrowserScraper)
    monkeypatch.setattr(module, "_load_runtime_config", _fake_runtime_loader)
    monkeypatch.setattr(module, "_persist_result", _fake_persist)

    class _FakeAgent:
        def supplement_cold_data(self, result, shop_id, date, reason):
            _ = shop_id
            _ = date
            patched = dict(result)
            raw = dict(patched.get("raw") or {})
            raw["llm_patch"] = {"status": "success", "reason": reason}
            patched["raw"] = raw
            return patched

        def close(self):
            return None

    monkeypatch.setattr(module, "LLMDashboardAgent", lambda: _FakeAgent())

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=2,
        execution_id="exec-1",
    )
    assert result["items"][0]["source"] == "llm"
    assert result["items"][0]["retry_count"] == 2
    assert result["items"][0]["raw"]["llm_patch"]["reason"] == "http_browser_failed"


async def _fake_cookie_health_runtime_loader(**_kwargs):
    runtime = _build_runtime()
    runtime.execution_id = "cron_cookie_health_check_2"
    return runtime


def test_sync_shop_dashboard_cookie_health_check_bypasses_result_cache(monkeypatch):
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )

    calls = {"get_cached_result": 0, "cache_result": 0}

    class _FakeIdempotencyHelper:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_cached_result(self, _key):
            calls["get_cached_result"] += 1
            return {"status": "cached", "source": "cache"}

        def acquire_lock(self, _key, ttl):
            _ = ttl
            return "token-1"

        def cache_result(self, _key, _result, ttl=86400):
            _ = ttl
            calls["cache_result"] += 1
            return None

        def release_lock(self, _key, _token):
            return None

    def _fake_collect_one_day(_runtime, _metric_date, _browser):
        return {"status": "success", "source": "script"}

    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "BrowserScraper", lambda: object())
    monkeypatch.setattr(
        module, "_load_runtime_config", _fake_cookie_health_runtime_loader
    )
    monkeypatch.setattr(module, "_collect_one_day", _fake_collect_one_day)
    monkeypatch.setattr(module, "_persist_result", _fake_persist)

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=2,
        execution_id="cron_cookie_health_check_2",
    )

    assert result["items"][0]["status"] == "success"
    assert calls["get_cached_result"] == 0
    assert calls["cache_result"] == 0


def test_sync_shop_dashboard_applies_rate_limit_policy_before_each_plan_unit(
    monkeypatch,
):
    runtime = _build_runtime()
    runtime.time_range = {"start": "2026-03-01", "end": "2026-03-02"}
    runtime.rate_limit = {"qps": 2, "burst": 1, "concurrency": 1}

    waits = {"count": 0}

    class _FakeRateLimiter:
        def __init__(self, policy):
            assert policy == {"qps": 2, "burst": 1, "concurrency": 1}

        def wait(self):
            waits["count"] += 1

    def _fake_collect_one_day(
        _runtime,
        metric_date,
        _browser,
        *,
        lock_manager,
        state_store,
        login_state_manager,
    ):
        _ = lock_manager
        _ = state_store
        _ = login_state_manager
        return {
            "status": "success",
            "source": "script",
            "metric_date": metric_date,
        }

    async def _fake_load_runtime_config(**_kwargs):
        return runtime

    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "_RateLimiter", _FakeRateLimiter)
    monkeypatch.setattr(module, "BrowserScraper", lambda: object())
    monkeypatch.setattr(module, "_load_runtime_config", _fake_load_runtime_config)
    monkeypatch.setattr(module, "_collect_one_day", _fake_collect_one_day)
    monkeypatch.setattr(module, "_persist_result", _fake_persist)

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=2,
        execution_id="exec-rate-limit-dict",
    )

    assert result["planned_units"] == 2
    assert waits["count"] == 2


def test_sync_shop_dashboard_accepts_integer_rate_limit_policy(monkeypatch):
    runtime = _build_runtime()
    runtime.rate_limit = 3

    observed: dict[str, int] = {}

    class _FakeRateLimiter:
        def __init__(self, policy):
            observed["policy"] = policy

        def wait(self):
            return None

    async def _fake_load_runtime_config(**_kwargs):
        return runtime

    def _fake_collect_one_day(_runtime, _metric_date, _browser):
        return {"status": "success", "source": "script"}

    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "_RateLimiter", _FakeRateLimiter)
    monkeypatch.setattr(module, "BrowserScraper", lambda: object())
    monkeypatch.setattr(module, "_load_runtime_config", _fake_load_runtime_config)
    monkeypatch.setattr(module, "_collect_one_day", _fake_collect_one_day)
    monkeypatch.setattr(module, "_persist_result", _fake_persist)

    module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=2,
        execution_id="exec-rate-limit-int",
    )

    assert observed["policy"] == 3
