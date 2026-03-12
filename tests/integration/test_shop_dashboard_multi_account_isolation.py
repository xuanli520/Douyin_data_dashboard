from src.scrapers.shop_dashboard.browser_scraper import BrowserScraper
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


def _runtime(account_id: str) -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["shop-1"],
        catalog_stale=False,
        shop_id="shop-1",
        cookies={},
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
        common_query={},
        token_keys=["sid"],
        api_groups=["overview"],
        account_id=account_id,
    )


async def test_multi_account_isolation(tmp_path):
    store = SessionStateStore(base_dir=tmp_path)

    async def refresher(runtime: ShopDashboardRuntimeConfig) -> dict:
        sid = f"{runtime.account_id}-token"
        return {
            "cookies": {"sid": sid},
            "storage_state": {
                "cookies": [{"name": "sid", "value": sid}],
                "origins": [],
            },
        }

    scraper = BrowserScraper(state_store=store, refresher=refresher)
    runtime_a = _runtime("acct-a")
    runtime_b = _runtime("acct-b")

    await scraper.refresh_runtime_context(runtime_a)
    await scraper.refresh_runtime_context(runtime_b)

    assert runtime_a.cookies["sid"] == "acct-a-token"
    assert runtime_b.cookies["sid"] == "acct-b-token"
