import asyncio
from types import SimpleNamespace
from datetime import datetime, timezone

from src.config import get_settings
from src.domains.task.enums import (
    TaskDefinitionStatus,
    TaskExecutionStatus,
    TaskTriggerMode,
    TaskType,
)
from src.domains.task.models import TaskDefinition, TaskExecution
from src import session as session_module
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import FunctionResultStatus
from src.tasks.status_store import write_finished_task_status, write_started_task_status


class FakeRedis:
    def __init__(self):
        self.hset_calls = []
        self.expire_calls = []

    def hset(self, key, mapping):
        self.hset_calls.append((key, mapping))

    def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))


def test_task_status_hook_writes_fields_and_ttl():
    mixin = TaskStatusMixin()
    fake_redis = FakeRedis()
    mixin.publisher = SimpleNamespace(redis_db_frame=fake_redis)

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


async def test_status_store_syncs_execution_record_fields(test_db):
    original_factory = session_module.async_session_factory
    session_module.async_session_factory = test_db
    try:
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

        owner = SimpleNamespace(publisher=SimpleNamespace(redis_db_frame=FakeRedis()))
        write_started_task_status(
            owner=owner,
            task_id="queue-status-1",
            task_name="process_orders",
            triggered_by=7,
        )
        write_finished_task_status(
            owner=owner,
            task_id="queue-status-1",
            task_name="process_orders",
            success=True,
            completed_at=1730000000.0,
            triggered_by=7,
            processed_rows=12,
            error_message=None,
        )
        await asyncio.sleep(0.1)

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

        write_started_task_status(
            owner=owner,
            task_id="queue-status-2",
            task_name="process_orders",
            triggered_by=7,
        )
        write_finished_task_status(
            owner=owner,
            task_id="queue-status-2",
            task_name="process_orders",
            success=False,
            completed_at=datetime.now(timezone.utc).timestamp(),
            triggered_by=7,
            processed_rows=0,
            error_message="boom",
        )
        await asyncio.sleep(0.1)

        async with test_db() as db_session:
            failed = await db_session.get(TaskExecution, failure.id)

        assert failed is not None
        assert failed.status == TaskExecutionStatus.FAILED
        assert failed.error_message == "boom"
        assert failed.completed_at is not None
    finally:
        session_module.async_session_factory = original_factory
