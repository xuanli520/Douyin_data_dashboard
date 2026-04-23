from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src import session as session_module
from src.cache import resolve_sync_redis_client
from src.config import get_settings
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.models import TaskExecution
from src.domains.task.repository import TaskExecutionRepository
from src.tasks.status_store import build_task_status_key

_TERMINAL_STATUSES = {
    TaskExecutionStatus.SUCCESS.value: TaskExecutionStatus.SUCCESS,
    TaskExecutionStatus.FAILED.value: TaskExecutionStatus.FAILED,
}


@dataclass(frozen=True)
class StatusRecoveryResult:
    recovered: int = 0
    failed: int = 0
    skipped: int = 0


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _normalize_payload(payload: dict[Any, Any]) -> dict[str, str]:
    return {_to_text(key): _to_text(value) for key, value in payload.items()}


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _parse_int(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _status_from_payload(payload: dict[str, str]) -> TaskExecutionStatus | None:
    return _TERMINAL_STATUSES.get(payload.get("status", "").upper())


def _execution_age(execution: TaskExecution, now: datetime) -> timedelta:
    reference = execution.started_at or execution.updated_at or execution.created_at
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return now - reference.astimezone(UTC)


def _read_status_payload(redis_client: Any, queue_task_id: str) -> dict[str, str]:
    hgetall = getattr(redis_client, "hgetall", None)
    if not callable(hgetall):
        return {}
    payload = hgetall(build_task_status_key(queue_task_id))
    if not isinstance(payload, dict):
        return {}
    return _normalize_payload(payload)


async def recover_stale_running_task_executions_async(
    *,
    redis_client: Any | None = None,
    redis_terminal_after: timedelta = timedelta(minutes=5),
    stale_failed_after: timedelta = timedelta(hours=24),
    limit: int = 100,
) -> StatusRecoveryResult:
    session_factory = session_module.async_session_factory
    if session_factory is None:
        return StatusRecoveryResult()

    now = datetime.now(tz=UTC)
    cutoff = now - min(redis_terminal_after, stale_failed_after)
    resolved_redis = redis_client or resolve_sync_redis_client(
        db=get_settings().funboost.filter_and_rpc_result_redis_db
    )

    recovered = 0
    failed = 0
    skipped = 0
    async with session_factory() as db_session:
        repo = TaskExecutionRepository(db_session)
        executions = await repo.list_running_older_than(cutoff, limit=limit)
        for execution in executions:
            queue_task_id = str(execution.queue_task_id or "").strip()
            if not queue_task_id:
                skipped += 1
                continue

            payload = _read_status_payload(resolved_redis, queue_task_id)
            terminal_status = _status_from_payload(payload)
            if terminal_status is not None:
                update_data: dict[str, Any] = {
                    "status": terminal_status,
                    "completed_at": _parse_timestamp(payload.get("completed_at", ""))
                    or now,
                }
                processed_rows = _parse_int(payload.get("processed_rows", ""))
                if processed_rows is not None:
                    update_data["processed_rows"] = max(processed_rows, 0)
                error_message = payload.get("error_message", "")
                if error_message or terminal_status == TaskExecutionStatus.FAILED:
                    update_data["error_message"] = error_message
                triggered_by = _parse_int(payload.get("triggered_by", ""))
                if triggered_by is not None and execution.triggered_by is None:
                    update_data["triggered_by"] = triggered_by
                await repo.update(execution, update_data)
                recovered += 1
                continue

            if _execution_age(execution, now) >= stale_failed_after:
                await repo.update(
                    execution,
                    {
                        "status": TaskExecutionStatus.FAILED,
                        "completed_at": now,
                        "error_message": (
                            "Task status recovery marked stale RUNNING execution as FAILED"
                        ),
                    },
                )
                failed += 1
                continue

            skipped += 1

        if recovered or failed:
            await db_session.commit()
    return StatusRecoveryResult(recovered=recovered, failed=failed, skipped=skipped)


def recover_stale_running_task_executions(
    *,
    redis_client: Any | None = None,
    redis_terminal_after: timedelta = timedelta(minutes=5),
    stale_failed_after: timedelta = timedelta(hours=24),
    limit: int = 100,
) -> StatusRecoveryResult:
    return session_module.run_coro(
        recover_stale_running_task_executions_async(
            redis_client=redis_client,
            redis_terminal_after=redis_terminal_after,
            stale_failed_after=stale_failed_after,
            limit=limit,
        )
    )
