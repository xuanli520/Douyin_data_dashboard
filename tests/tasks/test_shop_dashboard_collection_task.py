from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from src import session as db_session_module
from src.application.collection.usecase import CollectionUseCase
from src.domains.data_source.enums import DataSourceStatus
from src.domains.data_source.enums import DataSourceType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.shop_dashboard.models import ShopDashboardScore
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.models import TaskExecution
from src.tasks.collection import douyin_shop_dashboard as module


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
    def __init__(self, state_store, browser_scraper=None):
        self.state_store = state_store
        self.browser_scraper = browser_scraper

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


def _collect_success(
    runtime_config,
    metric_date: str,
    _browser,
    *,
    lock_manager,
    state_store,
    login_state_manager,
) -> dict[str, Any]:
    _ = lock_manager
    _ = state_store
    _ = login_state_manager
    return {
        "status": "success",
        "shop_id": runtime_config.shop_id,
        "metric_date": metric_date,
        "rule_id": runtime_config.rule_id,
        "execution_id": runtime_config.execution_id,
        "source": "script",
        "total_score": 4.8,
        "product_score": 4.7,
        "logistics_score": 4.9,
        "service_score": 4.6,
        "bad_behavior_score": 0.0,
        "reviews": {"summary": {}, "items": []},
        "violations": {"summary": {}, "waiting_list": []},
        "raw": {},
    }


async def _seed_runtime_entities(test_db) -> tuple[int, int]:
    async with test_db() as db_session:
        data_source = DataSource(
            name="task-usecase-ds",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=DataSourceStatus.ACTIVE,
        )
        db_session.add(data_source)
        await db_session.flush()
        rule = ScrapingRule(
            name="task-usecase-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            filters={"shop_id": ["shop-1"]},
            time_range={"start": "2026-03-01", "end": "2026-03-01"},
            backfill_last_n_days=1,
        )
        db_session.add(rule)
        await db_session.commit()
        return (
            data_source.id if data_source.id is not None else 0,
            rule.id if rule.id is not None else 0,
        )


@pytest.mark.asyncio
async def test_collection_usecase_should_be_idempotent_by_queue_task_id(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_runtime_entities(test_db)
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )
    monkeypatch.setattr(module, "_collect_one_day", _collect_success)
    monkeypatch.setattr(module, "BrowserScraper", lambda: object())
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(
        module,
        "SessionBootstrapper",
        _FakeSessionBootstrapper,
        raising=False,
    )
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )

    usecase = CollectionUseCase()
    redis_client = _FakeRedis()
    first = await usecase._execute_async(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-usecase-idempotent",
        queue_task_id="task-1",
        triggered_by=1,
        overrides={},
        redis_client=redis_client,
    )
    second = await usecase._execute_async(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-usecase-idempotent",
        queue_task_id="task-1",
        triggered_by=1,
        overrides={},
        redis_client=redis_client,
    )

    assert first["execution_id"] == second["execution_id"]
    assert second["reused"] is True

    async with test_db() as db_session:
        stmt = select(TaskExecution).where(
            TaskExecution.idempotency_key
            == f"shop_dashboard:{data_source_id}:{rule_id}:task-1"
        )
        execution = (await db_session.execute(stmt)).scalar_one()
        assert execution.status == TaskExecutionStatus.SUCCESS
        assert execution.rule_version == 1
        assert isinstance(execution.effective_config_snapshot, dict)


def test_sync_shop_dashboard_should_forward_queue_task_id_and_overrides(monkeypatch):
    monkeypatch.setattr(module.fct, "task_id", 98765, raising=False)
    monkeypatch.setattr(
        module.sync_shop_dashboard,
        "publisher",
        SimpleNamespace(redis_db_frame=_FakeRedis()),
        raising=False,
    )

    captured: dict[str, Any] = {}

    class _FakeUseCase:
        def execute(self, **kwargs):
            captured.update(kwargs)
            return {"status": "ok"}

    monkeypatch.setattr(
        "src.application.collection.usecase.CollectionUseCase",
        _FakeUseCase,
    )

    result = module.sync_shop_dashboard(
        data_source_id=11,
        rule_id=22,
        execution_id="exec-forward",
        triggered_by=5,
        shop_id="shop-x",
        all=False,
        extra_config={"cursor": "c1"},
    )

    assert result["status"] == "ok"
    assert captured["queue_task_id"] == "98765"
    assert captured["data_source_id"] == 11
    assert captured["rule_id"] == 22
    assert captured["execution_id"] == "exec-forward"
    assert captured["triggered_by"] == 5
    assert captured["overrides"] == {
        "shop_id": "shop-x",
        "shop_ids": ["shop-x"],
        "all": False,
        "extra_config": {"cursor": "c1"},
    }


def test_sync_shop_dashboard_sets_recommended_mode_for_unsupported(monkeypatch):
    monkeypatch.setattr(module.fct, "task_id", 123, raising=False)
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
        data_source_id=11,
        rule_id=22,
        execution_id="exec-forward",
    )

    assert result["recommended_collection_mode"] == "per_shop_account"


@pytest.mark.asyncio
async def test_collection_usecase_should_persist_shop_name_from_http_chain(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_runtime_entities(test_db)
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )

    class _FakeHttpScraper:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc_val, _exc_tb):
            return None

        def close(self):
            return None

        def fetch_dashboard_with_context(self, runtime_config, metric_date):
            return {
                "status": "success",
                "shop_id": runtime_config.shop_id,
                "actual_shop_id": runtime_config.shop_id,
                "shop_name": "demo-shop",
                "metric_date": metric_date,
                "rule_id": runtime_config.rule_id,
                "execution_id": runtime_config.execution_id,
                "source": "script",
                "total_score": 4.8,
                "product_score": 4.7,
                "logistics_score": 4.9,
                "service_score": 4.6,
                "bad_behavior_score": 0.0,
                "reviews": {"summary": {}, "items": []},
                "violations": {"summary": {}, "waiting_list": []},
                "raw": {},
            }

    monkeypatch.setattr(module, "HttpScraper", _FakeHttpScraper)
    monkeypatch.setattr(module, "BrowserScraper", lambda: object())
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(
        module,
        "SessionBootstrapper",
        _FakeSessionBootstrapper,
        raising=False,
    )
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )

    usecase = CollectionUseCase()
    result = await usecase._execute_async(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-usecase-shop-name",
        queue_task_id="task-shop-name",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    assert result["items"][0]["shop_name"] == "demo-shop"

    async with test_db() as db_session:
        score = (
            await db_session.execute(
                select(ShopDashboardScore).where(
                    ShopDashboardScore.shop_id == "shop-1",
                    ShopDashboardScore.metric_date == date(2026, 3, 1),
                )
            )
        ).scalar_one_or_none()

    assert score is not None
    assert score.shop_name == "demo-shop"
