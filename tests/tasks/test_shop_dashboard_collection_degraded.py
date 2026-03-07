from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.collection import douyin_shop_dashboard as module
from src.tasks.exceptions import ScrapingFailedException


def _runtime() -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
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
        execution_id="exec-degraded",
        fallback_chain=("browser",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
        account_id="acct-1",
    )


def test_collect_one_day_returns_degraded_when_shop_lock_unavailable(monkeypatch):
    runtime = _runtime()

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
            return None

        def release_shop_lock(self, _shop_id, _token):
            return None

    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)

    payload = module._collect_one_day(runtime, "2026-03-03", _FakeBrowser())

    assert payload["status"] == "degraded"
    assert payload["reason"] == "shop_locked"


def test_collect_one_day_returns_degraded_when_login_expired(monkeypatch):
    runtime = _runtime()

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
        def __init__(self, state_store):  # noqa: ARG002
            pass

        async def check_and_refresh(self, _account_id):
            return False

    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStore)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)

    payload = module._collect_one_day(runtime, "2026-03-03", _FakeBrowser())

    assert payload["status"] == "degraded"
    assert payload["reason"] == "login_expired"


def test_collect_one_day_returns_degraded_when_browser_reports_login_expired(
    monkeypatch,
):
    runtime = _runtime()
    runtime.fallback_chain = ("browser", "llm")

    class _FakeHttpScraper:
        def __init__(self, **_kwargs):
            pass

        def close(self):
            return None

    class _FakeBrowser:
        def retry_http(self, _http_scraper, _runtime, _metric_date):
            raise ScrapingFailedException("Browser login session expired")

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
        def __init__(self, state_store):  # noqa: ARG002
            pass

        async def check_and_refresh(self, _account_id):
            return True

        async def mark_expired(self, _account_id, reason):  # noqa: ARG002
            return None

    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStore)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)

    payload = module._collect_one_day(runtime, "2026-03-03", _FakeBrowser())

    assert payload["status"] == "degraded"
    assert payload["reason"] == "login_expired"
