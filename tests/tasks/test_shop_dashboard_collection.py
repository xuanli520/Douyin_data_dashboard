from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from src import session as db_session_module
from src.application.collection.runtime_loader import CollectionRuntimeLoader
from src.application.collection.usecase import CollectionUseCase
from src.domains.data_source.enums import DataSourceStatus
from src.domains.data_source.enums import DataSourceType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.models import TaskExecution
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


async def _seed_entities(
    test_db,
    *,
    rule_version: int = 1,
    data_source_status: DataSourceStatus = DataSourceStatus.ACTIVE,
) -> tuple[int, int]:
    async with test_db() as db_session:
        data_source = DataSource(
            name="task-collection-ds",
            source_type=DataSourceType.DOUYIN_SHOP,
            status=data_source_status,
        )
        db_session.add(data_source)
        await db_session.flush()
        rule = ScrapingRule(
            name="task-collection-rule",
            data_source_id=data_source.id if data_source.id is not None else 0,
            version=rule_version,
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
    monkeypatch.setattr(module, "BrowserScraper", lambda: object())
    monkeypatch.setattr(module, "SessionStateStore", _FakeStateStore)
    monkeypatch.setattr(module, "LockManager", _FakeLockManager)
    monkeypatch.setattr(module, "LoginStateManager", _FakeLoginStateManager)
    monkeypatch.setattr(
        module,
        "_materialize_runtime_storage_state",
        lambda runtime, _store: runtime,
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
            == f"shop_dashboard:{data_source_id}:{rule_id}:exec-login-expired"
        )
        execution = (await db_session.execute(stmt)).scalar_one()
        assert execution.status == TaskExecutionStatus.FAILED


def _raise_login_expired(*_args, **_kwargs):
    raise LoginExpiredError("session expired")
