from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.collection import douyin_shop_dashboard as module


def _runtime() -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["shop-1"],
        catalog_stale=False,
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
        fallback_chain=("browser_agent",),
        common_query={},
        account_id="acct-1",
    )


def test_collect_one_day_returns_degraded_when_shop_lock_unavailable(monkeypatch):
    runtime = _runtime()

    class _FakeLockManager:
        def acquire_shop_lock(self, _shop_id, ttl_seconds=None):  # noqa: ARG002
            return None

        def release_shop_lock(self, _shop_id, _token):
            return None

    monkeypatch.setattr(module, "LockManager", _FakeLockManager)

    payload = module._collect_one_day(runtime, "2026-03-03")

    assert payload["status"] == "degraded"
    assert payload["reason"] == "shop_locked"


def test_collect_one_day_uses_account_fallback_shop_lock_when_shop_id_empty(
    monkeypatch,
):
    runtime = _runtime()
    runtime.shop_id = ""
    runtime.account_id = "acct-fallback"
    runtime.fallback_chain = ("browser_agent",)

    seen_shop_ids: list[str] = []

    class _FakeBrowserAgentAdapter:
        def __init__(self, settings):
            self.settings = settings

        def collect(self, *, runtime, metric_date, state_store, plan_unit=None):
            _ = (runtime, metric_date, state_store, plan_unit)
            return {
                "source": "browser_agent",
                "total_score": 4.8,
                "product_score": 4.7,
                "logistics_score": 4.9,
                "service_score": 4.6,
                "reviews": {"summary": {}, "items": []},
                "violations": {"summary": {}, "waiting_list": []},
                "raw": {},
            }

    class _FakeLockManager:
        def acquire_shop_lock(self, shop_id, ttl_seconds=None):  # noqa: ARG002
            seen_shop_ids.append(shop_id)
            if not shop_id:
                return None
            return "shop-token"

        def release_shop_lock(self, _shop_id, _token):
            return None

    monkeypatch.setattr(module, "BrowserAgentAdapter", _FakeBrowserAgentAdapter)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)

    payload = module._collect_one_day(runtime, "2026-03-03")

    assert payload["status"] == "success"
    assert payload["source"] == "browser_agent"
    assert seen_shop_ids == ["account:acct-fallback"]
