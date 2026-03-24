from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from src import session
from src.application.collection import usecase as collection_usecase_module
from src.application.collection.executor import _supports_shared_helpers
from src.application.collection.runtime_loader import LoadedCollectionRuntime
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.collection import douyin_shop_dashboard as module
from src.tasks.collection.shop_dashboard_plan_builder import build_collection_plan
from src.tasks.exceptions import ScrapingFailedException


class _FakeRedis:
    def hset(self, _key, mapping=None, **_kwargs):
        _ = mapping
        return None

    def expire(self, _key, _seconds):
        return None


class _FakeStateStore:
    def __init__(self, *args, **kwargs):
        _ = (args, kwargs)

    def save(self, *_args, **_kwargs):
        return None

    def load_cookie_mapping(self, _account_id):
        return {}


class _FakeLockManager:
    def acquire_shop_lock(self, _shop_lock_id, ttl_seconds):
        _ = ttl_seconds
        return "shop-token"

    def release_shop_lock(self, _shop_lock_id, _token):
        return None

    def acquire_account_lock(self, _account_id, ttl_seconds):
        _ = ttl_seconds
        return "account-token"

    def release_account_lock(self, _account_id, _token):
        return None


class _FakeLoginStateManager:
    def __init__(self, *args, **kwargs):
        _ = (args, kwargs)

    async def check_and_refresh(self, _account_id):
        return True

    async def mark_expired(self, _account_id, reason):
        _ = reason
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


def _build_loaded_runtime(
    runtime: ShopDashboardRuntimeConfig,
) -> LoadedCollectionRuntime:
    return LoadedCollectionRuntime(
        runtime=runtime,
        rule_version=1,
        effective_config_snapshot={},
    )


def _install_fake_runtime_loader(
    monkeypatch,
    runtime: ShopDashboardRuntimeConfig | None = None,
):
    loaded_runtime = _build_loaded_runtime(runtime or _build_runtime())

    class _FakeRuntimeLoader:
        async def load(self, **_kwargs):
            return loaded_runtime

    monkeypatch.setattr(
        collection_usecase_module,
        "CollectionRuntimeLoader",
        _FakeRuntimeLoader,
    )


def _install_fake_collection_usecase(monkeypatch):
    class _FakeCollectionUseCase:
        def execute(
            self,
            *,
            data_source_id: int,
            rule_id: int,
            execution_id: str,
            queue_task_id: str,
            started_at=None,
            triggered_by: int | None = None,
            overrides: dict | None = None,
            redis_client=None,
        ) -> dict:
            _ = (data_source_id, rule_id, queue_task_id, started_at, triggered_by)
            loaded_runtime = session.run_coro(
                collection_usecase_module.CollectionRuntimeLoader().load(
                    session=None,
                    data_source_id=data_source_id,
                    rule_id=rule_id,
                    execution_id=execution_id,
                    overrides=overrides or {},
                )
            )
            runtime = loaded_runtime.runtime
            state_store = _FakeStateStore(
                base_dir=Path(".runtime") / "shop_dashboard_state"
            )
            runtime = module._materialize_runtime_storage_state(runtime, state_store)
            plan_units = build_collection_plan(runtime)
            helper = _FakeIdempotencyHelper(
                redis_client=redis_client,
                task_name="sync_shop_dashboard",
            )
            lock_manager = _FakeLockManager()
            login_state_manager = _FakeLoginStateManager(
                state_store=state_store,
                redis_client=redis_client,
            )
            items = []
            for plan_unit in plan_units:
                unit_runtime = (
                    runtime
                    if plan_unit.shop_id == runtime.shop_id
                    else replace(runtime, shop_id=plan_unit.shop_id)
                )
                business_key = module._build_business_key(
                    unit_runtime,
                    plan_unit.metric_date,
                    plan_unit=plan_unit,
                    queue_task_id=queue_task_id,
                )
                cached = helper.get_cached_result(business_key)
                if cached:
                    items.append(cached)
                    continue
                token = helper.acquire_lock(business_key, ttl=300)
                if not token:
                    items.append(
                        {
                            "status": "skipped",
                            "reason": "running",
                            "metric_date": plan_unit.metric_date,
                            "shop_id": unit_runtime.shop_id,
                            "rule_id": unit_runtime.rule_id,
                            "execution_id": unit_runtime.execution_id,
                            "retry_count": 0,
                            "fallback_trace": [],
                        }
                    )
                    continue
                try:
                    if _supports_shared_helpers(module._collect_one_day):
                        collected = module._collect_one_day(
                            unit_runtime,
                            plan_unit.metric_date,
                            lock_manager=lock_manager,
                            state_store=state_store,
                            login_state_manager=login_state_manager,
                        )
                    else:
                        collected = module._collect_one_day(
                            unit_runtime,
                            plan_unit.metric_date,
                        )
                    session.run_coro(
                        module._persist_result(
                            unit_runtime,
                            plan_unit.metric_date,
                            collected,
                        )
                    )
                    helper.cache_result(business_key, collected)
                    items.append(collected)
                finally:
                    helper.release_lock(business_key, token)
            return {
                "status": "success",
                "data_source_id": data_source_id,
                "rule_id": rule_id,
                "execution_id": execution_id,
                "shop_count": len({plan_unit.shop_id for plan_unit in plan_units}),
                "planned_units": len(plan_units),
                "completed_units": sum(
                    1
                    for item in items
                    if str(item.get("status", "success")) == "success"
                ),
                "failed_units": sum(
                    1
                    for item in items
                    if str(item.get("status", "success")) != "success"
                ),
                "items": items,
            }

    monkeypatch.setattr(
        collection_usecase_module,
        "CollectionUseCase",
        _FakeCollectionUseCase,
    )


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


def _build_runtime() -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["shop-1"],
        catalog_stale=False,
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
        fallback_chain=("http", "agent"),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
    )


async def _fake_persist(*_args, **_kwargs):
    return None


def test_pipeline_http_fail_then_llm(monkeypatch):
    _install_fake_collection_usecase(monkeypatch)
    _install_fake_runtime_loader(monkeypatch)
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
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
    assert result["items"][0]["retry_count"] == 1
    assert len(result["items"][0]["fallback_trace"]) == 2
    assert result["items"][0]["fallback_trace"][0]["stage"] == "http"
    assert result["items"][0]["fallback_trace"][0]["status"] == "failed"
    assert result["items"][0]["fallback_trace"][1]["stage"] in {"llm", "agent"}
    assert result["items"][0]["fallback_trace"][1]["status"] == "success"


def test_pipeline_cookie_only_http_success(monkeypatch):
    _install_fake_collection_usecase(monkeypatch)
    _install_fake_runtime_loader(monkeypatch)
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "_persist_result", _fake_persist)

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


def test_pipeline_rule_config_fields_flow_into_plan_and_query_context(monkeypatch):
    _install_fake_collection_usecase(monkeypatch)
    from src.scrapers.shop_dashboard.query_builder import build_endpoint_query_context

    runtime = ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["shop-1", "shop-2"],
        catalog_stale=False,
        shop_id="shop-1",
        cookies={"sessionid": "token"},
        proxy=None,
        timeout=15,
        retry_count=3,
        rate_limit={"qps": 2, "burst": 2, "concurrency": 1},
        granularity="DAY",
        time_range={"start": "2026-03-01", "end": "2026-03-02"},
        incremental_mode="BY_DATE",
        backfill_last_n_days=5,
        data_latency="T+2",
        target_type="SHOP_OVERVIEW",
        timezone="Asia/Shanghai",
        metrics=["overview", "analysis"],
        dimensions=["shop", "category"],
        filters={"shop_id": ["shop-1", "shop-2"], "region": "east"},
        top_n=50,
        sort_by="-total_score",
        include_long_tail=True,
        session_level=True,
        dedupe_key="{shop_id}:{window_start}:{window_end}:{rule_id}:{execution_id}",
        rule_id=2,
        execution_id="exec-pipeline-full-fields",
        fallback_chain=("http",),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=["overview"],
        extra_config={"cursor": "cursor-1"},
    )
    _install_fake_runtime_loader(monkeypatch, runtime)

    async def _fake_persist(*_args, **_kwargs):
        return None

    def _fake_collect_one_day(
        runtime_config,
        metric_date,
        *,
        lock_manager,
        state_store,
        login_state_manager,
    ):
        _ = lock_manager
        _ = state_store
        _ = login_state_manager
        context = build_endpoint_query_context(runtime_config, metric_date=metric_date)
        assert context.params["filters"]["region"] == "east"
        assert context.params["dimensions"] == ["shop", "category"]
        assert context.params["metrics"] == ["overview", "analysis"]
        assert context.params["top_n"] == 50
        assert context.params["sort_by"] == "-total_score"
        assert context.params["include_long_tail"] is True
        assert context.params["session_level"] is True
        return {
            "status": "success",
            "shop_id": runtime_config.shop_id,
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

    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "_collect_one_day", _fake_collect_one_day)
    monkeypatch.setattr(module, "_persist_result", _fake_persist)

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=2,
        execution_id="exec-pipeline-full-fields",
    )

    assert result["shop_count"] == 2
    assert result["planned_units"] == 4
    assert result["completed_units"] == 4


def test_pipeline_shop_id_fanout_for_rule_8_like_config(monkeypatch):
    _install_fake_collection_usecase(monkeypatch)
    runtime = _build_runtime()
    runtime.rule_id = 8
    runtime.shop_id = ""
    runtime.filters = {"shop_id": [f"shop-{idx}" for idx in range(13)]}
    runtime.resolved_shop_ids = [f"shop-{idx}" for idx in range(13)]
    runtime.time_range = {"start": "2026-03-01", "end": "2026-03-01"}
    runtime.backfill_last_n_days = 1
    _install_fake_runtime_loader(monkeypatch, runtime)

    async def _fake_persist(*_args, **_kwargs):
        return None

    def _fake_collect_one_day(
        runtime_config,
        metric_date,
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
            "shop_id": runtime_config.shop_id,
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

    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )
    monkeypatch.setattr(module, "_collect_one_day", _fake_collect_one_day)
    monkeypatch.setattr(module, "_persist_result", _fake_persist)

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=8,
        execution_id="exec-pipeline-shop-id-fanout",
    )

    assert result["shop_count"] == 13
    assert result["planned_units"] >= 13


def test_pipeline_sets_recommended_collection_mode_for_account_unsupported(monkeypatch):
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )

    class _FakeUseCase:
        def execute(self, **kwargs):
            _ = kwargs
            return {
                "status": "success",
                "items": [
                    {
                        "status": "failed",
                        "reason": "account_shop_switch_unsupported",
                    }
                ],
            }

    monkeypatch.setattr(
        "src.application.collection.usecase.CollectionUseCase",
        _FakeUseCase,
    )

    result = module.sync_shop_dashboard(
        data_source_id=1,
        rule_id=2,
        execution_id="exec-pipeline-route-unsupported",
    )

    assert result["recommended_collection_mode"] == "per_shop_account"
