import asyncio

import fakeredis

from src.scrapers.shop_dashboard.browser_scraper import BrowserScraper
from src.scrapers.shop_dashboard.cookie_manager import CookieManager
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


def _build_runtime() -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_id="shop-1",
        cookies={"sessionid": "old"},
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
        execution_id="exec-1",
        fallback_chain=("http", "browser", "llm"),
        graphql_query=None,
        common_query={"_bid": "old-bid"},
        token_keys=["x_tt_token"],
        api_groups=["overview"],
    )


async def test_browser_scraper_refreshes_cookie_and_query_via_cookie_manager():
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    cookie_manager = CookieManager(redis_client=redis_client, ttl_seconds=60)
    runtime = _build_runtime()

    async def refresher(_runtime: ShopDashboardRuntimeConfig) -> dict:
        return {
            "cookies": {"x_tt_token": "new-token"},
            "common_query": {"msToken": "ms-token"},
        }

    scraper = BrowserScraper(refresher=refresher, cookie_manager=cookie_manager)
    result = await scraper.refresh_runtime_context(runtime)

    assert result.cookies["x_tt_token"] == "new-token"
    assert result.common_query["msToken"] == "ms-token"
    cached = await cookie_manager.get("shop-1")
    assert cached["x_tt_token"] == "new-token"


def test_browser_scraper_retry_http_sets_browser_source():
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    cookie_manager = CookieManager(redis_client=redis_client, ttl_seconds=60)
    runtime = _build_runtime()

    async def refresher(_runtime: ShopDashboardRuntimeConfig) -> dict:
        return {"cookies": {"x_tt_token": "new-token"}}

    class _FakeHttpScraper:
        def __init__(self):
            self.calls = []

        def fetch_dashboard_with_context(self, runtime_config, metric_date):
            self.calls.append((runtime_config, metric_date))
            return {"shop_id": runtime_config.shop_id, "metric_date": metric_date}

    http_scraper = _FakeHttpScraper()
    scraper = BrowserScraper(refresher=refresher, cookie_manager=cookie_manager)
    result = scraper.retry_http(http_scraper, runtime, "2026-03-03")

    assert result["source"] == "browser"
    assert len(http_scraper.calls) == 1


async def test_browser_scraper_concurrent_waiters_share_refreshed_query_tokens():
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    cookie_manager = CookieManager(redis_client=redis_client, ttl_seconds=60)
    runtime_1 = _build_runtime()
    runtime_2 = _build_runtime()

    async def refresher(_runtime: ShopDashboardRuntimeConfig) -> dict:
        await asyncio.sleep(0.05)
        return {
            "cookies": {"x_tt_token": "new-token"},
            "common_query": {"msToken": "ms-token"},
        }

    scraper = BrowserScraper(refresher=refresher, cookie_manager=cookie_manager)
    refreshed_1, refreshed_2 = await asyncio.gather(
        scraper.refresh_runtime_context(runtime_1),
        scraper.refresh_runtime_context(runtime_2),
    )

    assert refreshed_1.common_query["msToken"] == "ms-token"
    assert refreshed_2.common_query["msToken"] == "ms-token"
