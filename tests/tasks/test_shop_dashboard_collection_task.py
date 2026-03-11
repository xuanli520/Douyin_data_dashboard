from __future__ import annotations

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

    def save(self, _account_id: str, _state: dict[str, Any]) -> None:
        return None

    def load_cookie_mapping(self, _account_id: str) -> dict[str, str]:
        return {}

    def exists(self, _account_id: str) -> bool:
        return True


class _FakeLockManager:
    def __init__(self, redis_client=None):
        self.redis_client = redis_client


class _FakeLoginStateManager:
    def __init__(self, state_store, redis_client=None):
        self.state_store = state_store
        self.redis_client = redis_client


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
async def test_collection_usecase_should_be_idempotent_by_execution_id(
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
    monkeypatch.setattr(module, "collect_one_day", _collect_success)
    monkeypatch.setattr(module, "BrowserScraper", lambda: object())
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "materialize_runtime_storage_state",
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
        queue_task_id="task-2",
        triggered_by=1,
        overrides={},
        redis_client=redis_client,
    )

    assert first["execution_id"] == second["execution_id"]
    assert second["reused"] is True

    async with test_db() as db_session:
        stmt = select(TaskExecution).where(
            TaskExecution.idempotency_key
            == f"shop_dashboard:{data_source_id}:{rule_id}:exec-usecase-idempotent"
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
        "all": False,
        "extra_config": {"cursor": "c1"},
    }
