from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src import session as session_module
from src.config import get_settings
from src.domains.task.enums import (
    TaskDefinitionStatus,
    TaskExecutionStatus,
    TaskTriggerMode,
    TaskType,
)
from src.domains.task.models import TaskDefinition, TaskExecution
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import FunctionResultStatus
from src.tasks.status_store import (
    _sync_execution_status_async,
    _write_status_mapping,
    write_finished_task_status,
)


class FakeRedis:
    def __init__(self):
        self.hset_calls = []
        self.expire_calls = []

    def hset(self, key, mapping):
        self.hset_calls.append((key, mapping))

    def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))


class RecordingPipeline:
    def __init__(self, redis):
        self.redis = redis
        self.commands = []

    def hset(self, key, mapping):
        self.commands.append(("hset", key, mapping))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", key, seconds))
        return self

    def execute(self):
        self.redis.executed_batches.append(list(self.commands))
        for command in self.commands:
            if command[0] == "hset":
                _, key, mapping = command
                self.redis.hset(key, mapping)
            if command[0] == "expire":
                _, key, seconds = command
                self.redis.expire(key, seconds)
        return [True for _ in self.commands]


class FakePipelineRedis(FakeRedis):
    def __init__(self):
        super().__init__()
        self.executed_batches = []
        self.pipeline_transactions = []

    def pipeline(self, transaction=True):
        self.pipeline_transactions.append(transaction)
        return RecordingPipeline(self)


class FailingPipeline:
    def __init__(self, raise_on_execute=False):
        self.raise_on_execute = raise_on_execute
        self.closed = False

    def hset(self, *_args, **_kwargs):
        return None

    def expire(self, *_args, **_kwargs):
        return None

    def execute(self):
        if self.raise_on_execute:
            raise RuntimeError("pipeline execute failed")
        return None

    def close(self):
        self.closed = True


class PipelineRedis:
    def __init__(self, pipeline):
        self._pipeline = pipeline

    def pipeline(self, transaction=True):
        _ = transaction
        return self._pipeline


def test_write_status_mapping_uses_pipeline_transaction():
    fake_redis = FakePipelineRedis()
    ttl = get_settings().funboost.status_ttl_seconds

    _write_status_mapping(fake_redis, "status-key", {"status": "STARTED", 1: "value"})

    assert fake_redis.pipeline_transactions == [True]
    assert fake_redis.executed_batches == [
        [
            ("hset", "status-key", {"status": "STARTED", "1": "value"}),
            ("expire", "status-key", ttl),
        ]
    ]
    assert fake_redis.hset_calls == [
        ("status-key", {"status": "STARTED", "1": "value"})
    ]
    assert fake_redis.expire_calls == [("status-key", ttl)]


def test_task_status_hook_writes_fields_and_ttl():
    mixin = TaskStatusMixin()
    fake_redis = FakeRedis()
    mixin.publisher = SimpleNamespace(redis_db_frame=fake_redis)
    mixin.queue_name = "collection_shop_dashboard"

    status = FunctionResultStatus(
        task_id="task-status-1",
        success=True,
        time_end=1730000000.0,
        function="sync_shop_dashboard",
    )

    mixin._sync_and_aio_frame_custom_record_process_info_func(
        status, {"body": {"triggered_by": 42}}
    )

    assert fake_redis.hset_calls
    key = fake_redis.hset_calls[0][0]
    assert key == "douyin:task:status:task-status-1"
    merged_mapping = {}
    for _, mapping in fake_redis.hset_calls:
        merged_mapping.update(mapping)
    assert merged_mapping["status"] == "SUCCESS"
    assert merged_mapping["task_name"] == "sync_shop_dashboard"
    assert str(merged_mapping["triggered_by"]) == "42"
    assert "completed_at" in merged_mapping

    assert fake_redis.expire_calls
    expire_key, expire_ttl = fake_redis.expire_calls[0]
    assert expire_key == key
    assert expire_ttl == get_settings().funboost.status_ttl_seconds


def test_task_status_hook_skips_dead_letter_queue():
    mixin = TaskStatusMixin()
    fake_redis = FakeRedis()
    mixin.publisher = SimpleNamespace(redis_db_frame=fake_redis)
    mixin.queue_name = "collection_shop_dashboard_dlx"

    status = FunctionResultStatus(
        task_id="task-status-dlx-1",
        success=True,
        time_end=1730000000.0,
        function="handle_collection_shop_dashboard_dead_letter",
    )

    mixin._sync_and_aio_frame_custom_record_process_info_func(
        status, {"body": {"triggered_by": 42}}
    )

    assert fake_redis.hset_calls == []
    assert fake_redis.expire_calls == []


def test_write_finished_task_status_ignores_interpreter_shutdown(monkeypatch):
    owner = SimpleNamespace(publisher=SimpleNamespace(redis_db_frame=FakeRedis()))

    def _raise_shutdown(_coro):
        raise RuntimeError("cannot schedule new futures after interpreter shutdown")

    monkeypatch.setattr(session_module, "run_coro", _raise_shutdown)

    write_finished_task_status(
        owner=owner,
        task_id="queue-status-shutdown",
        task_name="process_orders",
        success=False,
        completed_at=1730000000.0,
        triggered_by=7,
        processed_rows=0,
        error_message="boom",
    )


def test_write_status_mapping_closes_pipeline_on_error():
    pipeline = FailingPipeline(raise_on_execute=True)

    with pytest.raises(RuntimeError, match="pipeline execute failed"):
        _write_status_mapping(
            PipelineRedis(pipeline),
            "douyin:task:status:task-status-pipeline",
            {"status": "STARTED"},
        )

    assert pipeline.closed is True


async def test_status_store_syncs_execution_record_fields(test_db, monkeypatch):
    monkeypatch.setattr(session_module, "async_session_factory", test_db)
    async with test_db() as db_session:
        task = TaskDefinition(
            name="status-sync",
            task_type=TaskType.ETL_ORDERS,
            status=TaskDefinitionStatus.ACTIVE,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        execution = TaskExecution(
            task_id=task.id if task.id is not None else 0,
            queue_task_id="queue-status-1",
            status=TaskExecutionStatus.QUEUED,
            trigger_mode=TaskTriggerMode.MANUAL,
            payload={"batch_date": "2026-03-08"},
            triggered_by=7,
        )
        db_session.add(execution)
        await db_session.commit()

    started_at = datetime.now(timezone.utc)
    await _sync_execution_status_async(
        queue_task_id="queue-status-1",
        status=TaskExecutionStatus.RUNNING,
        started_at=started_at,
        triggered_by=7,
    )
    await _sync_execution_status_async(
        queue_task_id="queue-status-1",
        status=TaskExecutionStatus.SUCCESS,
        completed_at=datetime.fromtimestamp(1730000000.0, tz=timezone.utc),
        processed_rows=12,
        error_message=None,
        triggered_by=7,
    )
    async with test_db() as db_session:
        stored = await db_session.get(TaskExecution, execution.id)

    assert stored is not None
    assert stored.status == TaskExecutionStatus.SUCCESS
    assert stored.started_at is not None
    assert stored.completed_at is not None
    assert stored.processed_rows == 12
    assert stored.error_message is None

    async with test_db() as db_session:
        failure = TaskExecution(
            task_id=task.id if task.id is not None else 0,
            queue_task_id="queue-status-2",
            status=TaskExecutionStatus.QUEUED,
            trigger_mode=TaskTriggerMode.MANUAL,
            payload={"batch_date": "2026-03-08"},
            triggered_by=7,
        )
        db_session.add(failure)
        await db_session.commit()
        await db_session.refresh(failure)

    failure_started_at = datetime.now(timezone.utc)
    await _sync_execution_status_async(
        queue_task_id="queue-status-2",
        status=TaskExecutionStatus.RUNNING,
        started_at=failure_started_at,
        triggered_by=7,
    )
    await _sync_execution_status_async(
        queue_task_id="queue-status-2",
        status=TaskExecutionStatus.FAILED,
        completed_at=datetime.now(timezone.utc),
        processed_rows=0,
        error_message="boom",
        triggered_by=7,
    )
    async with test_db() as db_session:
        failed = await db_session.get(TaskExecution, failure.id)

    assert failed is not None
    assert failed.status == TaskExecutionStatus.FAILED
    assert failed.error_message == "boom"
    assert failed.completed_at is not None
