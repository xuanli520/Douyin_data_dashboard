from __future__ import annotations

from typing import Any
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src import session as db_session_module
from src.application.collection.runtime_loader import CollectionRuntimeLoader
from src.application.collection.usecase import CollectionUseCase
from src.domains.data_source.enums import DataSourceStatus
from src.domains.data_source.enums import DataSourceType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.models import TaskExecution
from src.domains.task.exceptions import ShopDashboardNoTargetShopsException
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


class _RecordingLoginStateManager(_FakeLoginStateManager):
    marked_expired: list[tuple[str, str]] = []

    async def mark_expired(self, account_id: str, reason: str) -> None:
        type(self).marked_expired.append((account_id, reason))


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
        results: dict[str, dict[str, Any]] = {}
        account_id = str(getattr(runtime, "account_id", "") or "").strip() or "acct-1"
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
            results[shop_text] = {
                "shop_id": shop_text,
                "target_shop_id": shop_text,
                "bootstrap_failed": False,
                "bootstrap_verify_status": "passed",
                "bootstrap_verify_actual_shop_id": shop_text,
                "bootstrap_verify_error_code": "",
            }
        return results

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


class _BootstrapVerifyRequestFailed:
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
        _ = (runtime, verify_metric_date_by_shop, force_serial)
        return {
            str(shop_id): {
                "shop_id": str(shop_id),
                "target_shop_id": str(shop_id),
                "bootstrap_failed": True,
                "error_code": "verify_request_failed",
                "error": "verify_request_failed",
                "bootstrap_choose_status": "passed",
                "bootstrap_verify_status": "failed",
                "bootstrap_verify_actual_shop_id": "",
                "bootstrap_verify_error_code": "verify_request_failed",
            }
            for shop_id in shop_ids
        }

    async def bootstrap_shop(self, *, runtime, shop_id, verify_metric_date=None):
        _ = (runtime, shop_id, verify_metric_date)
        return {
            "shop_id": str(shop_id),
            "target_shop_id": str(shop_id),
            "bootstrap_failed": True,
            "error_code": "verify_request_failed",
            "error": "verify_request_failed",
            "bootstrap_choose_status": "passed",
            "bootstrap_verify_status": "failed",
            "bootstrap_verify_actual_shop_id": "",
            "bootstrap_verify_error_code": "verify_request_failed",
        }


class _BootstrapVerifyLoginExpired:
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
        _ = (runtime, verify_metric_date_by_shop, force_serial)
        return {
            str(shop_id): {
                "shop_id": str(shop_id),
                "target_shop_id": str(shop_id),
                "bootstrap_failed": True,
                "error_code": "verify_login_expired",
                "error": "http_401",
                "bootstrap_choose_status": "passed",
                "bootstrap_verify_status": "failed",
                "bootstrap_verify_actual_shop_id": "",
                "bootstrap_verify_error_code": "verify_login_expired",
            }
            for shop_id in shop_ids
        }

    async def bootstrap_shop(self, *, runtime, shop_id, verify_metric_date=None):
        _ = (runtime, shop_id, verify_metric_date)
        return {
            "shop_id": str(shop_id),
            "target_shop_id": str(shop_id),
            "bootstrap_failed": True,
            "error_code": "verify_login_expired",
            "error": "http_401",
            "bootstrap_choose_status": "passed",
            "bootstrap_verify_status": "failed",
            "bootstrap_verify_actual_shop_id": "",
            "bootstrap_verify_error_code": "verify_login_expired",
        }


class _BootstrapVerifyMismatch:
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
        _ = (runtime, verify_metric_date_by_shop, force_serial)
        return {
            str(shop_id): {
                "shop_id": str(shop_id),
                "target_shop_id": str(shop_id),
                "bootstrap_failed": True,
                "error_code": "verify_shop_mismatch",
                "error": "verify_shop_mismatch",
                "actual_shop_id": "shop-fixed",
                "bootstrap_choose_status": "passed",
                "bootstrap_verify_status": "failed",
                "bootstrap_verify_actual_shop_id": "shop-fixed",
                "bootstrap_verify_error_code": "verify_shop_mismatch",
            }
            for shop_id in shop_ids
        }

    async def bootstrap_shop(self, *, runtime, shop_id, verify_metric_date=None):
        _ = (runtime, shop_id, verify_metric_date)
        return {
            "shop_id": str(shop_id),
            "target_shop_id": str(shop_id),
            "bootstrap_failed": True,
            "error_code": "verify_shop_mismatch",
            "error": "verify_shop_mismatch",
            "actual_shop_id": "shop-fixed",
            "bootstrap_choose_status": "passed",
            "bootstrap_verify_status": "failed",
            "bootstrap_verify_actual_shop_id": "shop-fixed",
            "bootstrap_verify_error_code": "verify_shop_mismatch",
        }


def _collect_mismatch(
    runtime_config,
    metric_date: str,
    *,
    lock_manager,
    state_store,
    login_state_manager,
) -> dict[str, Any]:
    _ = (lock_manager, state_store, login_state_manager)
    return {
        "status": "success",
        "shop_id": runtime_config.shop_id,
        "actual_shop_id": f"actual-{runtime_config.shop_id}",
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
async def test_bootstrap_verify_request_failed_not_counted_as_shop_mismatch(
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
    monkeypatch.setattr(
        module,
        "SessionBootstrapper",
        _BootstrapVerifyRequestFailed,
        raising=False,
    )
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
        execution_id="exec-bootstrap-request-failed",
        queue_task_id="queue-bootstrap-request-failed",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    assert result["bootstrap_verify_failed_count"] == 1
    assert result["shop_mismatch_count"] == 0
    assert result["items"][0]["reason"] == "bootstrap_verify_failed"
    assert result["items"][0]["error_code"] == "verify_request_failed"


@pytest.mark.asyncio
async def test_bootstrap_verify_login_expired_marks_login_state_expired(
    test_db,
    monkeypatch,
):
    _RecordingLoginStateManager.marked_expired = []
    data_source_id, rule_id = await _seed_entities(test_db)
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(
        module,
        "SessionBootstrapper",
        _BootstrapVerifyLoginExpired,
        raising=False,
    )
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _RecordingLoginStateManager)
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
        execution_id="exec-bootstrap-login-expired",
        queue_task_id="queue-bootstrap-login-expired",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    assert result["bootstrap_verify_failed_count"] == 1
    assert result["items"][0]["error_code"] == "verify_login_expired"
    assert _RecordingLoginStateManager.marked_expired == [
        (f"rule_{rule_id}", "verify_login_expired")
    ]


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
async def test_account_shop_switch_unsupported_short_circuit(
    test_db,
    monkeypatch,
):
    data_source_id, rule_id = await _seed_entities(
        test_db,
        rule_filters={"shop_id": ["shop-1", "shop-2", "shop-3", "shop-4"]},
    )
    monkeypatch.setattr(
        db_session_module,
        "async_session_factory",
        test_db,
        raising=False,
    )
    monkeypatch.setattr(module, "_collect_one_day", _collect_mismatch)
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(
        module,
        "SessionBootstrapper",
        _BootstrapVerifyMismatch,
        raising=False,
    )
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
        execution_id="exec-account-unsupported",
        queue_task_id="queue-account-unsupported",
        triggered_by=1,
        overrides={},
        redis_client=_FakeRedis(),
    )

    assert result["account_switch_unsupported_count"] >= 1
    assert any(
        str(item.get("reason", "")) == "account_shop_switch_unsupported"
        for item in result["items"]
    )


def test_raise_when_all_units_failed_skips_exception_for_account_switch_unsupported():
    usecase = CollectionUseCase()
    result = {
        "planned_units": 2,
        "completed_units": 0,
        "failed_units": 2,
        "items": [
            {
                "status": "failed",
                "reason": "account_shop_switch_unsupported",
            },
            {
                "status": "failed",
                "reason": "account_shop_switch_unsupported",
            },
        ],
    }

    usecase._raise_when_all_units_failed(result)

    assert result["recommended_collection_mode"] == "per_shop_account"
