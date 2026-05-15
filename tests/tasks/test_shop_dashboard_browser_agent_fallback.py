from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.collection import douyin_shop_dashboard as module


def _runtime():
    return ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["1001"],
        catalog_stale=False,
        shop_id="1001",
        cookies={},
        proxy=None,
        timeout=30,
        retry_count=0,
        rate_limit=None,
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
        rule_id=9,
        execution_id="exec-1",
        fallback_chain=("browser_agent",),
        common_query={},
        agent_recipe_ref={"namespace": "generic", "key": "overview"},
        account_id="acct-1",
    )


class _LockManager:
    def acquire_shop_lock(self, _shop_id, ttl_seconds):
        _ = ttl_seconds
        return "token"

    def release_shop_lock(self, _shop_id, _token):
        return None


class _LoginStateManager:
    async def check_and_refresh(self, _account_id):
        return True


def test_collect_one_day_runs_browser_agent_stage(monkeypatch):
    class _Adapter:
        def __init__(self, settings):
            self.settings = settings

        def collect(self, *, runtime, metric_date, state_store, plan_unit=None):
            _ = (state_store, plan_unit)
            return {
                "status": "success",
                "source": "browser_agent",
                "actual_shop_id": runtime.shop_id,
                "metric_date": metric_date,
                "total_score": 88,
                "reviews": {"summary": {}, "items": []},
                "violations": {"summary": {}, "waiting_list": []},
                "raw": {},
            }

    monkeypatch.setattr(module, "BrowserAgentAdapter", _Adapter)

    result = module._collect_one_day(
        _runtime(),
        "2026-03-01",
        lock_manager=_LockManager(),
        state_store=object(),
        login_state_manager=_LoginStateManager(),
    )

    assert result["source"] == "browser_agent"
    assert result["total_score"] == 88
    assert result["fallback_trace"] == [
        {"stage": "browser_agent", "status": "success"}
    ]
