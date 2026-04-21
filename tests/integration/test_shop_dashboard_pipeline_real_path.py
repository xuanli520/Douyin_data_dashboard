from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from src import session as db_session_module
from src.domains.data_source.enums import DataSourceStatus
from src.domains.data_source.enums import DataSourceType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.shop_dashboard.models import ShopDashboardScore
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.models import TaskExecution
from src.tasks.collection import douyin_shop_dashboard as module
from src.tasks.exceptions import ScrapingFailedException


class _FakeRedis:
    def __init__(self) -> None:
        self._kv: dict[str, Any] = {}
        self._hash: dict[str, dict[str, Any]] = {}

    def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False):
        _ = ex
        if nx and key in self._kv:
            return False
        self._kv[key] = value
        return True

    def get(self, key: str) -> Any | None:
        return self._kv.get(key)

    def delete(self, *keys: str):
        removed = 0
        for key in keys:
            if key in self._kv:
                del self._kv[key]
                removed += 1
        return removed

    def eval(self, script: str, _num_keys: int, *args):
        key = str(args[0])
        token = args[1]
        if "del" in script:
            if self._kv.get(key) == token:
                del self._kv[key]
                return 1
            return 0
        if "expire" in script:
            return 1 if self._kv.get(key) == token else 0
        return 0

    def hset(self, key: str, mapping=None, **kwargs):
        target = self._hash.setdefault(key, {})
        if isinstance(mapping, dict):
            target.update(mapping)
        if kwargs:
            target.update(kwargs)
        return 1

    def hgetall(self, key: str) -> dict[str, Any]:
        return dict(self._hash.get(key, {}))

    def expire(self, _key: str, _seconds: int):
        return True


class _FakeStateStore:
    def __init__(self, base_dir=None):
        _ = base_dir
        self._bundles: dict[tuple[str, str], dict[str, Any]] = {}

    def save(self, _account_id: str, _state: dict[str, Any]) -> None:
        return None

    def load_cookie_mapping(self, _account_id: str) -> dict[str, str]:
        return {}

    def exists(self, _account_id: str) -> bool:
        return True

    def load_bundle(self, account_id: str, shop_id: str) -> dict[str, Any] | None:
        return self._bundles.get((account_id, shop_id))

    def save_bundle(self, account_id: str, shop_id: str, bundle: dict[str, Any]):
        self._bundles[(account_id, shop_id)] = dict(bundle)

    def invalidate_bundle(self, account_id: str, shop_id: str) -> None:
        self._bundles.pop((account_id, shop_id), None)


class _FakeLockManager:
    def __init__(self, redis_client=None):
        self.redis_client = redis_client

    def acquire_shop_lock(self, _shop_id, ttl_seconds=None):
        _ = ttl_seconds
        return "shop-token"

    def release_shop_lock(self, _shop_id, _token):
        return None

    def acquire_account_lock(self, _account_id, ttl_seconds=None):
        _ = ttl_seconds
        return "account-token"

    def release_account_lock(self, _account_id, _token):
        return None


class _FakeLoginStateManager:
    def __init__(self, state_store, redis_client=None):
        self.state_store = state_store
        self.redis_client = redis_client


class _FakeSessionBootstrapper:
    def __init__(self, state_store):
        self.state_store = state_store

    async def bootstrap_shops(
        self,
        *,
        runtime,
        shop_ids,
        verify_metric_date_by_shop=None,
        force_serial=None,
    ):
        _ = verify_metric_date_by_shop
        _ = force_serial
        account_id = str(getattr(runtime, "account_id", "") or "").strip() or "acct-1"
        result = {}
        for shop_id in shop_ids:
            shop_text = str(shop_id)
            self.state_store.save_bundle(
                account_id,
                shop_text,
                {
                    "cookies": dict(getattr(runtime, "cookies", {}) or {}),
                    "common_query": dict(getattr(runtime, "common_query", {}) or {}),
                    "validated_shop_id": shop_text,
                    "verified_actual_shop_id": shop_text,
                    "verify_status": "passed",
                    "verified_at": "2026-03-10T00:00:00+00:00",
                    "session_version": "2",
                },
            )
            result[shop_text] = {
                "shop_id": shop_text,
                "target_shop_id": shop_text,
                "bootstrap_failed": False,
                "bootstrap_verify_status": "passed",
                "bootstrap_verify_actual_shop_id": shop_text,
                "bootstrap_verify_error_code": "",
            }
        return result

    async def bootstrap_shop(self, *, runtime, shop_id, verify_metric_date=None):
        _ = verify_metric_date
        account_id = str(getattr(runtime, "account_id", "") or "").strip() or "acct-1"
        shop_text = str(shop_id)
        self.state_store.save_bundle(
            account_id,
            shop_text,
            {
                "cookies": dict(getattr(runtime, "cookies", {}) or {}),
                "common_query": dict(getattr(runtime, "common_query", {}) or {}),
                "validated_shop_id": shop_text,
                "verified_actual_shop_id": shop_text,
                "verify_status": "passed",
                "verified_at": "2026-03-10T00:00:00+00:00",
                "session_version": "2",
            },
        )
        return {
            "shop_id": shop_text,
            "target_shop_id": shop_text,
            "bootstrap_failed": False,
            "bootstrap_verify_status": "passed",
            "bootstrap_verify_actual_shop_id": shop_text,
            "bootstrap_verify_error_code": "",
        }


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


async def _seed_runtime_entities(
    test_db,
    *,
    data_source_extra_config: dict[str, Any] | None = None,
    rule_filters: dict[str, Any] | None = None,
    rule_time_range: dict[str, str] | None = None,
    rule_metrics: list[str] | None = None,
    rule_dimensions: list[str] | None = None,
    rule_rate_limit: dict[str, Any] | None = None,
    rule_top_n: int | None = None,
    rule_sort_by: str | None = None,
    include_long_tail: bool = False,
    session_level: bool = False,
    rule_dedupe_key: str | None = None,
    rule_extra_config: dict[str, Any] | None = None,
) -> tuple[int, int]:
    async with test_db() as db_session:
        data_source = DataSource(
            name="pipeline-real-path-ds",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
            extra_config=data_source_extra_config
            or {"cookies": {"sessionid": "token"}},
        )
        db_session.add(data_source)
        await db_session.flush()
        rule = ScrapingRule(
            name="pipeline-real-path-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            filters=rule_filters
            if rule_filters is not None
            else {"shop_id": ["shop-1"]},
            time_range=(
                rule_time_range
                if rule_time_range is not None
                else {"start": "2026-03-01", "end": "2026-03-01"}
            ),
            backfill_last_n_days=1,
            metrics=rule_metrics,
            dimensions=rule_dimensions,
            rate_limit=rule_rate_limit,
            top_n=rule_top_n,
            sort_by=rule_sort_by,
            include_long_tail=include_long_tail,
            session_level=session_level,
            dedupe_key=rule_dedupe_key,
            extra_config=rule_extra_config,
        )
        db_session.add(rule)
        await db_session.commit()
        return (
            data_source.id if data_source.id is not None else 0,
            rule.id if rule.id is not None else 0,
        )


def _install_real_pipeline_env(monkeypatch, test_db, redis_client: _FakeRedis) -> None:
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=redis_client),
        raising=False,
    )
    monkeypatch.setattr(module, "resolve_sync_redis_client", lambda: redis_client)
    monkeypatch.setattr(
        module,
        "FunboostIdempotencyHelper",
        _FakeIdempotencyHelper,
        raising=False,
    )
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(
        module,
        "SessionBootstrapper",
        _FakeSessionBootstrapper,
        raising=False,
    )
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)


@pytest.mark.asyncio
async def test_pipeline_http_fail_then_llm_runs_real_collection_usecase(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_runtime_entities(test_db)
    redis_client = _FakeRedis()
    _install_real_pipeline_env(monkeypatch, test_db, redis_client)
    monkeypatch.setattr(module.fct, "task_id", "queue-real-pipeline-llm", raising=False)

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

    class _FakeAgent:
        def supplement_cold_data(self, result, shop_id, metric_date, reason):
            _ = (shop_id, metric_date)
            patched = dict(result)
            raw = dict(patched.get("raw") or {})
            raw["llm_patch"] = {"status": "success", "reason": reason}
            patched["raw"] = raw
            return patched

        def close(self):
            return None

    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
    monkeypatch.setattr(module, "LLMDashboardAgent", lambda: _FakeAgent())

    result = await asyncio.to_thread(
        module.sync_shop_dashboard,
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-real-pipeline-llm",
    )

    assert result["items"][0]["source"] == "llm"
    assert result["items"][0]["retry_count"] == 1
    assert result["items"][0]["fallback_trace"] == [
        {"stage": "http", "status": "failed", "error": "http failed"},
        {"stage": "agent", "status": "success"},
    ]

    async with test_db() as db_session:
        execution = (
            await db_session.execute(
                select(TaskExecution).where(
                    TaskExecution.queue_task_id == "queue-real-pipeline-llm"
                )
            )
        ).scalar_one()
        score = (
            await db_session.execute(
                select(ShopDashboardScore).where(
                    ShopDashboardScore.shop_id == "shop-1",
                    ShopDashboardScore.metric_date == date(2026, 3, 1),
                )
            )
        ).scalar_one_or_none()

    assert execution.status == TaskExecutionStatus.SUCCESS
    assert execution.processed_rows == 1
    assert score is not None
    assert score.source == "llm"


@pytest.mark.asyncio
async def test_pipeline_cookie_only_http_success_persists_real_usecase_path(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_runtime_entities(test_db)
    redis_client = _FakeRedis()
    _install_real_pipeline_env(monkeypatch, test_db, redis_client)
    monkeypatch.setattr(
        module.fct,
        "task_id",
        "queue-real-pipeline-cookie-success",
        raising=False,
    )

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

    result = await asyncio.to_thread(
        module.sync_shop_dashboard,
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-real-pipeline-cookie-success",
    )

    assert result["items"][0]["source"] == "script"
    assert result["items"][0]["retry_count"] == 0
    assert result["items"][0]["fallback_trace"] == [
        {"stage": "http", "status": "success"}
    ]

    async with test_db() as db_session:
        execution = (
            await db_session.execute(
                select(TaskExecution).where(
                    TaskExecution.queue_task_id == "queue-real-pipeline-cookie-success"
                )
            )
        ).scalar_one()
        score = (
            await db_session.execute(
                select(ShopDashboardScore).where(
                    ShopDashboardScore.shop_id == "shop-1",
                    ShopDashboardScore.metric_date == date(2026, 3, 1),
                )
            )
        ).scalar_one()

    assert execution.status == TaskExecutionStatus.SUCCESS
    assert score.total_score == pytest.approx(4.8)
    assert score.source == "script"


@pytest.mark.asyncio
async def test_pipeline_rule_config_fields_flow_into_real_usecase_plan_and_query_context(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_runtime_entities(
        test_db,
        rule_filters={"shop_id": ["shop-1", "shop-2"], "region": "east"},
        rule_time_range={"start": "2026-03-01", "end": "2026-03-02"},
        rule_metrics=["overview", "analysis"],
        rule_dimensions=["shop", "category"],
        rule_rate_limit={"qps": 2, "burst": 2, "concurrency": 1},
        rule_top_n=50,
        rule_sort_by="-total_score",
        include_long_tail=True,
        session_level=True,
        rule_dedupe_key="{shop_id}:{window_start}:{window_end}:{rule_id}:{execution_id}",
        rule_extra_config={"cursor": "cursor-1"},
    )
    redis_client = _FakeRedis()
    _install_real_pipeline_env(monkeypatch, test_db, redis_client)
    monkeypatch.setattr(
        module.fct,
        "task_id",
        "queue-real-pipeline-config-fields",
        raising=False,
    )

    from src.scrapers.shop_dashboard.query_builder import build_endpoint_query_context

    seen_contexts: list[dict[str, Any]] = []

    def _collect_one_day(
        runtime_config,
        metric_date,
        *,
        lock_manager,
        state_store,
        login_state_manager,
    ):
        _ = (lock_manager, state_store, login_state_manager)
        context = build_endpoint_query_context(runtime_config, metric_date=metric_date)
        seen_contexts.append(
            {
                "shop_id": runtime_config.shop_id,
                "metric_date": metric_date,
                "params": context.params,
            }
        )
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

    monkeypatch.setattr(module, "_collect_one_day", _collect_one_day)

    result = await asyncio.to_thread(
        module.sync_shop_dashboard,
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-real-pipeline-config-fields",
    )

    assert result["shop_count"] == 2
    assert result["planned_units"] == 4
    assert result["completed_units"] == 4
    assert len(seen_contexts) == 4
    assert {item["shop_id"] for item in seen_contexts} == {"shop-1", "shop-2"}
    for item in seen_contexts:
        params = item["params"]
        assert params["filters"]["region"] == "east"
        assert params["dimensions"] == ["shop", "category"]
        assert params["metrics"] == ["overview", "analysis"]
        assert params["top_n"] == 50
        assert params["sort_by"] == "-total_score"
        assert params["include_long_tail"] is True
        assert params["session_level"] is True
