from __future__ import annotations

import threading
import time
from typing import Any
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src import session as db_session_module
from src.application.collection.runtime_loader import CollectionRuntimeLoader
from src.application.collection.usecase import CollectionUseCase
from src.config import get_settings
from src.domains.agent_recipe.models import (
    AGENT_RECIPE_STATUS_DEGRADED,
    AGENT_RECIPE_STABILITY_STABLE,
)
from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.data_source.enums import DataSourceStatus
from src.domains.data_source.enums import DataSourceType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.models import TaskExecution
from src.domains.task.exceptions import ScrapingFailedException
from src.domains.task.exceptions import ShopDashboardNoTargetShopsException
from src.scrapers.shop_dashboard.exceptions import DataIncompleteError
from src.scrapers.shop_dashboard.exceptions import LoginExpiredError
from src.tasks.collection import douyin_shop_dashboard as module
from src.tasks.exceptions import ShopDashboardCookieExpiredException


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


class _FakeLoginStateManager:
    def __init__(self, state_store, redis_client=None):
        self.state_store = state_store
        self.redis_client = redis_client

    async def check_and_refresh(self, _account_id: str) -> bool:
        return True

    async def mark_expired(self, _account_id: str, reason: str) -> None:
        _ = reason
        return None


def _collect_mismatch(
    runtime_config,
    metric_date: str,
    *,
    plan_unit=None,
    lock_manager,
    state_store,
    login_state_manager,
) -> dict[str, Any]:
    _ = (plan_unit, lock_manager, state_store, login_state_manager)
    return {
        "status": "success",
        "shop_id": runtime_config.shop_id,
        "actual_shop_id": f"actual-{runtime_config.shop_id}",
        "metric_date": metric_date,
        "rule_id": runtime_config.rule_id,
        "execution_id": runtime_config.execution_id,
        "source": "browser_agent",
        "total_score": 4.8,
        "product_score": 4.7,
        "logistics_score": 4.9,
        "service_score": 4.6,
        "bad_behavior_score": 0.0,
        "reviews": {"summary": {}, "items": []},
        "violations": {"summary": {}, "waiting_list": []},
        "raw": {},
    }


async def _seed_entities(
    test_db,
    *,
    rule_version: int = 1,
    data_source_status: DataSourceStatus = DataSourceStatus.ACTIVE,
    ds_extra_config: dict[str, Any] | None = None,
    rule_filters: dict[str, Any] | None = None,
    rule_time_range: dict[str, str] | None = None,
) -> tuple[int, int]:
    async with test_db() as db_session:
        data_source = DataSource(
            name="task-collection-ds",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=data_source_status,
            extra_config=ds_extra_config,
        )
        db_session.add(data_source)
        await db_session.flush()
        rule = ScrapingRule(
            name="task-collection-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            version=rule_version,
            filters=rule_filters
            if rule_filters is not None
            else {"shop_id": ["shop-1"]},
            time_range=rule_time_range
            if rule_time_range is not None
            else {"start": "2026-03-01", "end": "2026-03-01"},
            backfill_last_n_days=1,
        )
        db_session.add(rule)
        await db_session.commit()
        return (
            data_source.id if data_source.id is not None else 0,
            rule.id if rule.id is not None else 0,
        )


def _recipe_payload() -> dict[str, Any]:
    return {
        "entrypoint": {"url": "https://example.test/dashboard"},
        "steps": [{"id": "open", "action": "goto"}],
        "observations": {
            "total": {
                "id": "total",
                "kind": "text",
                "locator": {"kind": "css", "value": ".total"},
            }
        },
        "assertions": [{"id": "total_exists", "kind": "exists", "source": "total"}],
        "recovery_policy": {"enabled": True, "max_attempts": 1},
        "security_policy": {"allowed_origins": ["https://example.test"]},
    }


async def _seed_agent_recipe(
    test_db,
    *,
    stability: str = "candidate",
    version: int = 1,
    payload: dict[str, Any] | None = None,
):
    async with test_db() as db_session:
        repo = AgentRecipeRepository(db_session)
        recipe = await repo.create(
            {
                "namespace": "shop_dashboard",
                "key": "overview",
                "version": version,
                "stability": stability,
                **(payload or _recipe_payload()),
            }
        )
        await db_session.commit()
        return recipe


@pytest.mark.asyncio
async def test_collection_runtime_loader_should_capture_rule_version_and_snapshot(
    test_db,
):
    data_source_id, rule_id = await _seed_entities(test_db, rule_version=3)
    loader = CollectionRuntimeLoader()
    async with test_db() as db_session:
        loaded = await loader.load(
            session=db_session,
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id="exec-loader-snapshot",
        )

    assert loaded.rule_version == 3
    assert loaded.runtime.shop_id == "shop-1"
    assert loaded.effective_config_snapshot["rule_version"] == 3
    assert loaded.effective_config_snapshot["rule_id"] == rule_id


def test_collection_runtime_loader_should_inject_redis_client_for_default_catalog_service(
    monkeypatch,
):
    from src.application.collection import runtime_loader as runtime_loader_module

    captured: dict[str, Any] = {}
    fake_redis_client = object()

    class _FakeCatalogService:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        runtime_loader_module,
        "resolve_sync_redis_client",
        lambda _redis_client=None: fake_redis_client,
        raising=True,
    )
    monkeypatch.setattr(
        runtime_loader_module,
        "AccountShopCatalogService",
        _FakeCatalogService,
        raising=True,
    )

    runtime_loader_module.CollectionRuntimeLoader()

    assert captured["redis_client"] is fake_redis_client


@pytest.mark.asyncio
async def test_collection_runtime_loader_should_resolve_all_mode_shop_ids_from_catalog_service(
    test_db,
):
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={"shop_ids": ["shop-a", "shop-b"]},
        rule_filters={},
    )

    class _FakeCatalogService:
        async def get_shop_catalog(self, **_kwargs):
            return SimpleNamespace(
                shop_ids=["shop-a", "shop-b"],
                catalog_stale=False,
                resolve_source="live",
            )

    loader = CollectionRuntimeLoader(account_shop_catalog_service=_FakeCatalogService())
    async with test_db() as db_session:
        loaded = await loader.load(
            session=db_session,
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id="exec-loader-all-mode",
            overrides={"all": True},
        )

    assert loaded.runtime.shop_id == "shop-a"
    assert loaded.runtime.filters["all"] is True
    assert loaded.runtime.filters["shop_id"] == ["shop-a", "shop-b"]
    assert loaded.effective_config_snapshot["filters"]["shop_id"] == [
        "shop-a",
        "shop-b",
    ]


@pytest.mark.asyncio
async def test_collection_runtime_loader_should_resolve_all_mode_shop_ids_from_account_resolver(
    test_db,
):
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={},
        rule_filters={},
    )

    class _FakeCatalogService:
        async def get_shop_catalog(self, **_kwargs):
            return SimpleNamespace(
                shop_ids=["shop-r1", "shop-r2"],
                catalog_stale=True,
                resolve_source="cache_stale",
            )

    loader = CollectionRuntimeLoader(account_shop_catalog_service=_FakeCatalogService())
    async with test_db() as db_session:
        loaded = await loader.load(
            session=db_session,
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id="exec-loader-all-resolver",
            overrides={"all": True},
        )

    assert loaded.runtime.shop_id == "shop-r1"
    assert loaded.runtime.filters["shop_id"] == ["shop-r1", "shop-r2"]
    assert loaded.runtime.catalog_stale is True


@pytest.mark.asyncio
async def test_collection_runtime_loader_should_fail_when_exact_mode_has_no_shop_targets(
    test_db,
):
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={},
        rule_filters={},
    )
    loader = CollectionRuntimeLoader()
    async with test_db() as db_session:
        with pytest.raises(ShopDashboardNoTargetShopsException):
            await loader.load(
                session=db_session,
                data_source_id=data_source_id,
                rule_id=rule_id,
                execution_id="exec-loader-empty-exact",
            )


@pytest.mark.asyncio
async def test_collection_usecase_should_map_login_expired_to_task_exception(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_entities(test_db)
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "_collect_one_day",
        _raise_login_expired,
    )
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )
    monkeypatch.setattr(
        CollectionUseCase,
        "_raise_when_all_units_failed",
        lambda self, result: None,
    )

    usecase = CollectionUseCase()
    with pytest.raises(ShopDashboardCookieExpiredException):
        await usecase._execute_async(
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id="exec-login-expired",
            queue_task_id="queue-login-expired",
            triggered_by=1,
            overrides={},
            redis_client=_FakeRedis(),
        )

    async with test_db() as db_session:
        stmt = select(TaskExecution).where(
            TaskExecution.idempotency_key
            == f"shop_dashboard:{data_source_id}:{rule_id}:queue-login-expired"
        )
        execution = (await db_session.execute(stmt)).scalar_one()
        assert execution.status == TaskExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_failed_collection_should_backfill_rule_last_execution_fields(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_entities(test_db)
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )
    monkeypatch.setattr(module, "_collect_one_day", _raise_login_expired)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )
    monkeypatch.setattr(
        CollectionUseCase,
        "_raise_when_all_units_failed",
        lambda self, result: None,
    )

    usecase = CollectionUseCase()
    with pytest.raises(ShopDashboardCookieExpiredException):
        await usecase._execute_async(
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id="exec-failed-last-run",
            queue_task_id="queue-failed-last-run",
            triggered_by=1,
            overrides={},
            redis_client=_FakeRedis(),
        )

    async with test_db() as db_session:
        rule = await ScrapingRuleRepository(db_session).get_by_id(rule_id)
        assert rule is not None
        assert rule.last_executed_at is not None
        assert rule.last_execution_id == "exec-failed-last-run"


def _raise_login_expired(*_args, **_kwargs):
    raise LoginExpiredError("session expired")


@pytest.mark.asyncio
async def test_collect_mismatch_reaches_threshold_then_hits_circuit_break(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_entities(
        test_db,
        rule_filters={"shop_id": ["shop-1"]},
        rule_time_range={"start": "2026-03-01", "end": "2026-03-04"},
    )
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )
    monkeypatch.setattr(module, "_collect_one_day", _collect_mismatch)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )
    monkeypatch.setattr(
        CollectionUseCase,
        "_raise_when_all_units_failed",
        lambda self, result: None,
    )

    usecase = CollectionUseCase()
    result = await usecase._execute_async(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-mismatch-circuit",
        queue_task_id="queue-mismatch-circuit",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    reasons = [str(item.get("reason", "")) for item in result["items"]]
    assert reasons.count("shop_mismatch") >= 3
    assert "shop_circuit_break" in reasons


@pytest.mark.asyncio
async def test_batch_collection_rejects_candidate_agent_recipe(test_db, monkeypatch):
    await _seed_agent_recipe(test_db)
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={
            "agent_recipe": {"namespace": "shop_dashboard", "key": "overview"}
        },
        rule_filters={"shop_id": ["shop-1", "shop-2"]},
    )
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )

    with pytest.raises(ScrapingFailedException) as exc_info:
        await CollectionUseCase()._execute_async(
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id="exec-batch-candidate",
            queue_task_id="queue-batch-candidate",
            triggered_by=1,
            overrides={},
            redis_client=_FakeRedis(),
        )

    assert exc_info.value.error_data["reason"] == "agent_recipe_not_stable_for_batch"


@pytest.mark.asyncio
async def test_all_mode_batch_collection_rejects_candidate_agent_recipe(
    test_db,
    monkeypatch,
):
    await _seed_agent_recipe(test_db)
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={
            "agent_recipe": {"namespace": "shop_dashboard", "key": "overview"}
        },
        rule_filters={},
    )
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )

    class _CatalogService:
        async def get_shop_catalog(self, **_kwargs):
            return SimpleNamespace(
                shop_ids=["shop-1", "shop-2"],
                catalog_stale=False,
                resolve_source="live",
            )

    usecase = CollectionUseCase(
        runtime_loader=CollectionRuntimeLoader(
            account_shop_catalog_service=_CatalogService()
        )
    )
    with pytest.raises(ScrapingFailedException) as exc_info:
        await usecase._execute_async(
            data_source_id=data_source_id,
            rule_id=rule_id,
            execution_id="exec-all-candidate",
            queue_task_id="queue-all-candidate",
            triggered_by=1,
            overrides={"all": True},
            redis_client=_FakeRedis(),
        )

    assert exc_info.value.error_data["reason"] == "agent_recipe_not_stable_for_batch"


@pytest.mark.asyncio
async def test_batch_collection_allows_stable_recipe_and_disables_recovery(
    test_db,
    monkeypatch,
):
    await _seed_agent_recipe(test_db, stability=AGENT_RECIPE_STABILITY_STABLE)
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={
            "agent_recipe": {"namespace": "shop_dashboard", "key": "overview"}
        },
        rule_filters={"shop_id": ["shop-1", "shop-2"]},
    )
    seen_extra_config = []
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )

    def _collect_success(runtime_config, metric_date, **kwargs):
        _ = kwargs
        seen_extra_config.append(dict(runtime_config.extra_config or {}))
        return {
            "status": "success",
            "shop_id": runtime_config.shop_id,
            "actual_shop_id": runtime_config.shop_id,
            "metric_date": metric_date,
            "rule_id": runtime_config.rule_id,
            "execution_id": runtime_config.execution_id,
            "source": "browser_agent",
            "total_score": 4.8,
            "product_score": 4.7,
            "logistics_score": 4.9,
            "service_score": 4.6,
            "bad_behavior_score": 0.0,
            "reviews": {"summary": {}, "items": []},
            "violations": {"summary": {}, "waiting_list": []},
            "raw": {},
        }

    monkeypatch.setattr(module, "_collect_one_day", _collect_success)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )

    result = await CollectionUseCase()._execute_async(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-batch-stable",
        queue_task_id="queue-batch-stable",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    assert result["completed_units"] == 2
    assert len(seen_extra_config) == 2
    assert seen_extra_config[0]["agent_batch_mode"] is True
    assert seen_extra_config[0]["agent_recovery_enabled"] is False
    assert seen_extra_config[0]["agent_recipe_inline"]["stability"] == "stable"


@pytest.mark.asyncio
async def test_batch_collection_falls_back_to_older_valid_stable_recipe(
    test_db,
    monkeypatch,
):
    await _seed_agent_recipe(
        test_db,
        stability=AGENT_RECIPE_STABILITY_STABLE,
        version=1,
    )
    await _seed_agent_recipe(
        test_db,
        stability=AGENT_RECIPE_STABILITY_STABLE,
        version=2,
        payload={
            "entrypoint": {"url": "https://example.test/dashboard"},
            "steps": [{"id": "open", "action": "goto"}],
            "observations": {},
            "assertions": [],
            "recovery_policy": {"enabled": True, "max_attempts": 1},
            "security_policy": {"allowed_origins": ["https://example.test"]},
        },
    )
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={
            "agent_recipe": {"namespace": "shop_dashboard", "key": "overview"}
        },
        rule_filters={"shop_id": ["shop-1", "shop-2"]},
    )
    seen_extra_config = []
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )

    def _collect_success(runtime_config, metric_date, **kwargs):
        _ = kwargs
        seen_extra_config.append(dict(runtime_config.extra_config or {}))
        return {
            "status": "success",
            "shop_id": runtime_config.shop_id,
            "actual_shop_id": runtime_config.shop_id,
            "metric_date": metric_date,
            "rule_id": runtime_config.rule_id,
            "execution_id": runtime_config.execution_id,
            "source": "browser_agent",
            "total_score": 4.8,
            "product_score": 4.7,
            "logistics_score": 4.9,
            "service_score": 4.6,
            "bad_behavior_score": 0.0,
            "reviews": {"summary": {}, "items": []},
            "violations": {"summary": {}, "waiting_list": []},
            "raw": {},
        }

    monkeypatch.setattr(module, "_collect_one_day", _collect_success)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )

    result = await CollectionUseCase()._execute_async(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-batch-stable-fallback",
        queue_task_id="queue-batch-stable-fallback",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    assert result["completed_units"] == 2
    assert len(seen_extra_config) == 2
    assert seen_extra_config[0]["agent_recipe_inline"]["version"] == 1


@pytest.mark.asyncio
async def test_batch_agent_recipe_failure_marks_stable_recipe_degraded(
    test_db,
    monkeypatch,
):
    recipe = await _seed_agent_recipe(test_db, stability=AGENT_RECIPE_STABILITY_STABLE)
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={
            "agent_recipe": {"namespace": "shop_dashboard", "key": "overview"}
        },
        rule_filters={"shop_id": ["shop-1", "shop-2"]},
    )
    calls = []
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )

    def _collect_failed(runtime_config, *_args, **_kwargs):
        calls.append(runtime_config.shop_id)
        raise DataIncompleteError(
            "missing total",
            error_data={"failure_kind": "observation_empty"},
        )

    monkeypatch.setattr(module, "_collect_one_day", _collect_failed)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )
    monkeypatch.setattr(
        CollectionUseCase,
        "_raise_when_all_units_failed",
        lambda self, result: None,
    )

    result = await CollectionUseCase()._execute_async(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-batch-degraded",
        queue_task_id="queue-batch-degraded",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    assert calls == ["shop-1"]
    assert result["failed_units"] == 2
    assert result["items"][0]["reason"] == "agent_recipe_failed"
    assert result["items"][0]["error_code"] == "observation_empty"
    assert "raw" not in result["items"][0]
    async with test_db() as db_session:
        repo = AgentRecipeRepository(db_session)
        stored = await repo.get_by_id(recipe.id if recipe.id is not None else 0)
        versions = await repo.list_versions("shop_dashboard", "overview")

    assert stored is not None
    assert stored.status == AGENT_RECIPE_STATUS_DEGRADED
    assert stored.stability == "candidate"
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_stable_batch_collection_runs_parallel_when_enabled(test_db, monkeypatch):
    await _seed_agent_recipe(test_db, stability=AGENT_RECIPE_STABILITY_STABLE)
    data_source_id, rule_id = await _seed_entities(
        test_db,
        ds_extra_config={
            "agent_recipe": {"namespace": "shop_dashboard", "key": "overview"}
        },
        rule_filters={"shop_id": ["shop-1", "shop-2"]},
    )
    settings = get_settings()
    monkeypatch.setattr(
        settings.shop_dashboard,
        "agent_batch_concurrency_limit",
        2,
        raising=False,
    )
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )
    active = 0
    max_active = 0
    lock = threading.Lock()

    def _collect_success(runtime_config, metric_date, **kwargs):
        nonlocal active, max_active
        _ = kwargs
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return {
            "status": "success",
            "shop_id": runtime_config.shop_id,
            "actual_shop_id": runtime_config.shop_id,
            "metric_date": metric_date,
            "rule_id": runtime_config.rule_id,
            "execution_id": runtime_config.execution_id,
            "source": "browser_agent",
            "total_score": 4.8,
            "product_score": 4.7,
            "logistics_score": 4.9,
            "service_score": 4.6,
            "bad_behavior_score": 0.0,
            "reviews": {"summary": {}, "items": []},
            "violations": {"summary": {}, "waiting_list": []},
            "raw": {},
        }

    monkeypatch.setattr(module, "_collect_one_day", _collect_success)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
    )

    result = await CollectionUseCase()._execute_async(
        data_source_id=data_source_id,
        rule_id=rule_id,
        execution_id="exec-batch-parallel",
        queue_task_id="queue-batch-parallel",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    assert result["completed_units"] == 2
    assert max_active == 2
