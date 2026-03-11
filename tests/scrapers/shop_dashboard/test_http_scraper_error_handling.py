import httpx
import pytest

from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError


def _build_runtime(*, retry_count: int = 0) -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_id="shop-1",
        cookies={"sid": "token"},
        proxy=None,
        timeout=15,
        retry_count=retry_count,
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
        execution_id="exec-error",
        fallback_chain=("http",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
    )


def _overview_success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 0,
            "data": {
                "experience_score": {"value": "4.8"},
                "goods_score": {"value": 4.7},
                "logistics_score": {"value": 4.9},
                "service_score": {"value": 4.6},
            },
        },
    )


def test_request_timeout_maps_to_scraping_failed_exception():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    runtime = _build_runtime()
    with httpx.Client(
        transport=transport,
        base_url="https://fxg.jinritemai.com",
        timeout=15.0,
    ) as client:
        scraper = HttpScraper(client=client)
        with pytest.raises(ShopDashboardScraperError) as exc_info:
            scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert str(exc_info.value) == "HTTP request timeout"
    assert exc_info.value.error_data["method"] == "GET"
    assert (
        exc_info.value.error_data["path"]
        == "/governance/shop/experiencescore/getOverviewByVersion"
    )
    assert exc_info.value.error_data["timeout"] == 15.0


def test_http_status_error_contains_status_and_response_body_snippet():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    body = "x" * 512

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=body)

    transport = httpx.MockTransport(handler)
    runtime = _build_runtime()
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        with pytest.raises(ShopDashboardScraperError) as exc_info:
            scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert str(exc_info.value) == "HTTP status error"
    assert exc_info.value.error_data["status_code"] == 503
    assert len(exc_info.value.error_data["response_body_snippet"]) == 300


def test_request_error_contains_url_and_path():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connect failed", request=request)

    transport = httpx.MockTransport(handler)
    runtime = _build_runtime()
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        with pytest.raises(ShopDashboardScraperError) as exc_info:
            scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert str(exc_info.value) == "HTTP request failed"
    assert exc_info.value.error_data["method"] == "GET"
    assert (
        exc_info.value.error_data["path"]
        == "/governance/shop/experiencescore/getOverviewByVersion"
    )
    assert "shop_id=shop-1" in exc_info.value.error_data["url"]
    assert "date=2026-03-03" in exc_info.value.error_data["url"]
    assert exc_info.value.error_data["url"].startswith(
        "https://fxg.jinritemai.com/governance/shop/experiencescore/getOverviewByVersion?"
    )


def test_request_retries_on_transient_status_then_recovers(monkeypatch):
    from src.scrapers.shop_dashboard import http_scraper as scraper_module
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, text="busy")
        return _overview_success_response()

    monkeypatch.setattr(scraper_module.time, "sleep", lambda _seconds: None)
    transport = httpx.MockTransport(handler)
    runtime = _build_runtime(retry_count=1)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["total_score"] == 4.8
    assert calls["count"] == 2


def test_request_retries_on_timeout_then_recovers(monkeypatch):
    from src.scrapers.shop_dashboard import http_scraper as scraper_module
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return _overview_success_response()

    monkeypatch.setattr(scraper_module.time, "sleep", lambda _seconds: None)
    transport = httpx.MockTransport(handler)
    runtime = _build_runtime(retry_count=1)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["total_score"] == 4.8
    assert calls["count"] == 2


def test_request_does_not_retry_on_4xx(monkeypatch):
    from src.scrapers.shop_dashboard import http_scraper as scraper_module
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(401, text="unauthorized")

    monkeypatch.setattr(scraper_module.time, "sleep", lambda _seconds: None)
    transport = httpx.MockTransport(handler)
    runtime = _build_runtime(retry_count=3)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        with pytest.raises(ShopDashboardScraperError) as exc_info:
            scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert exc_info.value.error_data["status_code"] == 401
    assert calls["count"] == 1
