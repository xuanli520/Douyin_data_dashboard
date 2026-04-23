from datetime import datetime, timedelta, timezone

from src import session as session_module
from src.domains.task.enums import (
    TaskDefinitionStatus,
    TaskExecutionStatus,
    TaskTriggerMode,
    TaskType,
)
from src.domains.task.models import TaskDefinition, TaskExecution
from src.tasks.status_recovery import recover_stale_running_task_executions_async


class FakeStatusRedis:
    def __init__(self, payloads):
        self.payloads = payloads

    def hgetall(self, key):
        return self.payloads.get(key, {})


async def _create_running_execution(test_db, *, queue_task_id: str, started_at):
    async with test_db() as db_session:
        task = TaskDefinition(
            name=f"status-recovery-{queue_task_id}",
            task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
            status=TaskDefinitionStatus.ACTIVE,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)
        execution = TaskExecution(
            task_id=task.id if task.id is not None else 0,
            queue_task_id=queue_task_id,
            status=TaskExecutionStatus.RUNNING,
            trigger_mode=TaskTriggerMode.MANUAL,
            payload={"queue_task_id": queue_task_id},
            started_at=started_at,
        )
        db_session.add(execution)
        await db_session.commit()
        await db_session.refresh(execution)
        return execution.id


async def test_status_recovery_backfills_running_execution_from_redis_terminal_status(
    test_db,
    monkeypatch,
):
    monkeypatch.setattr(session_module, "async_session_factory", test_db)
    started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    execution_id = await _create_running_execution(
        test_db,
        queue_task_id="queue-recovery-success",
        started_at=started_at,
    )
    redis_client = FakeStatusRedis(
        {
            "douyin:task:status:queue-recovery-success": {
                "status": "SUCCESS",
                "completed_at": "1730000000",
                "processed_rows": "12",
                "triggered_by": "7",
            }
        }
    )

    result = await recover_stale_running_task_executions_async(
        redis_client=redis_client,
        redis_terminal_after=timedelta(minutes=5),
        stale_failed_after=timedelta(hours=24),
    )

    async with test_db() as db_session:
        stored = await db_session.get(TaskExecution, execution_id)

    assert result.recovered == 1
    assert result.failed == 0
    assert stored.status == TaskExecutionStatus.SUCCESS
    assert stored.completed_at is not None
    assert stored.processed_rows == 12
    assert stored.triggered_by == 7


async def test_status_recovery_marks_very_old_running_execution_failed_idempotently(
    test_db,
    monkeypatch,
):
    monkeypatch.setattr(session_module, "async_session_factory", test_db)
    started_at = datetime.now(timezone.utc) - timedelta(days=2)
    execution_id = await _create_running_execution(
        test_db,
        queue_task_id="queue-recovery-stale",
        started_at=started_at,
    )
    redis_client = FakeStatusRedis({})

    first = await recover_stale_running_task_executions_async(
        redis_client=redis_client,
        redis_terminal_after=timedelta(minutes=5),
        stale_failed_after=timedelta(hours=24),
    )
    second = await recover_stale_running_task_executions_async(
        redis_client=redis_client,
        redis_terminal_after=timedelta(minutes=5),
        stale_failed_after=timedelta(hours=24),
    )

    async with test_db() as db_session:
        stored = await db_session.get(TaskExecution, execution_id)

    assert first.recovered == 0
    assert first.failed == 1
    assert second.recovered == 0
    assert second.failed == 0
    assert stored.status == TaskExecutionStatus.FAILED
    assert stored.error_message
