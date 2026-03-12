from src.scrapers.shop_dashboard.browser_scraper import BrowserScraper
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def _runtime(
    *,
    account_id: str = "acct-1",
    cookies: dict[str, str] | None = None,
) -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["shop-1"],
        catalog_stale=False,
        shop_id="shop-1",
        cookies=cookies or {},
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
        token_keys=["sid"],
        api_groups=["overview"],
        account_id=account_id,
    )


async def test_browser_scraper_loads_and_saves_state_without_redis(
    tmp_path, monkeypatch
):
    store = SessionStateStore(base_dir=tmp_path)
    runtime = _runtime(account_id="acct-1", cookies={})
    scraper = BrowserScraper(state_store=store)

    async def fake_refresh(_runtime, date=None):  # noqa: ARG001
        return {
            "cookies": {"sid": "new-token"},
            "common_query": {"msToken": "ms-token"},
            "storage_state": {
                "cookies": [{"name": "sid", "value": "new-token"}],
                "origins": [],
            },
        }

    monkeypatch.setattr(scraper, "_refresh_with_playwright", fake_refresh)

    await scraper.refresh_runtime_context(runtime)

    assert runtime.cookies["sid"] == "new-token"
    assert runtime.common_query["msToken"] == "ms-token"


def test_browser_scraper_retry_http_sets_browser_source():
    runtime = _runtime(account_id="acct-2", cookies={"sid": "old"})

    async def refresher(_runtime: ShopDashboardRuntimeConfig) -> dict:
        return {"cookies": {"sid": "new-token"}}

    class _FakeHttpScraper:
        def __init__(self):
            self.calls = []

        def fetch_dashboard_with_context(self, runtime_config, metric_date):
            self.calls.append((runtime_config, metric_date))
            return {"shop_id": runtime_config.shop_id, "metric_date": metric_date}

    http_scraper = _FakeHttpScraper()
    scraper = BrowserScraper(refresher=refresher)
    result = scraper.retry_http(http_scraper, runtime, "2026-03-03")

    assert result["source"] == "browser"
    assert len(http_scraper.calls) == 1
