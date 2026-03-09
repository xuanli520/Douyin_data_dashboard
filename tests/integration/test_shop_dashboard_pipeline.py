from types import SimpleNamespace

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
        execution_id="exec-pipeline",
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


def test_pipeline_http_fail_then_browser_then_llm(monkeypatch):
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
        execution_id="exec-pipeline",
    )

    assert result["items"][0]["source"] == "llm"
    assert result["items"][0]["retry_count"] == 2
    assert len(result["items"][0]["fallback_trace"]) == 3
    assert result["items"][0]["fallback_trace"][0]["stage"] == "http"
    assert result["items"][0]["fallback_trace"][0]["status"] == "failed"
    assert result["items"][0]["fallback_trace"][1]["stage"] == "browser"
    assert result["items"][0]["fallback_trace"][1]["status"] == "failed"
    assert result["items"][0]["fallback_trace"][2]["stage"] in {"llm", "agent"}
    assert result["items"][0]["fallback_trace"][2]["status"] == "success"


def test_pipeline_cookie_only_http_success(monkeypatch):
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    monkeypatch.setattr(module, "_load_runtime_config", _fake_runtime_loader)
    monkeypatch.setattr(module, "_persist_result", _fake_persist)
    monkeypatch.setattr(module, "BrowserScraper", lambda: _FakeBrowserScraper())

    class _SuccessHttpScraper:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc_value, _traceback):
            return None

        def fetch_dashboard_with_context(self, runtime, metric_date):
            assert runtime.cookies["sessionid"] == "token"
            return {
                "shop_id": runtime.shop_id,
                "metric_date": metric_date,
                "source": "script",
                "total_score": 4.8,
                "product_score": 4.7,
                "logistics_score": 4.9,
                "service_score": 4.6,
                "reviews": {"summary": {}, "items": []},
                "violations": {"summary": {}, "waiting_list": []},
                "raw": {},
            }

        def close(self):
            return None

    monkeypatch.setattr(module, "HttpScraper", _SuccessHttpScraper)

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=2,
        execution_id="exec-pipeline-cookie-only",
    )

    assert result["items"][0]["source"] == "script"
    assert result["items"][0]["retry_count"] == 0
    assert result["items"][0]["fallback_trace"] == [
        {"stage": "http", "status": "success"}
    ]
