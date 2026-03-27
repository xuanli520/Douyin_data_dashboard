from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from datetime import UTC, datetime
from typing import Any

from src import session as session_module
from src.cache import resolve_sync_redis_client
from src.config import get_settings
from src.domains.task.enums import TaskExecutionStatus
from src.domains.task.repository import TaskExecutionRepository

logger = logging.getLogger(__name__)


def resolve_status_redis_client(owner: Any) -> Any:
    consumer = getattr(owner, "consumer", None)
    candidates = (
        getattr(consumer, "redis_db_filter_and_rpc_result", None),
        getattr(consumer, "redis_db_frame", None),
        getattr(owner, "redis_db_filter_and_rpc_result", None),
        getattr(owner, "redis_db_frame", None),
        getattr(getattr(owner, "publisher", None), "redis_db_frame", None),
    )
    for client in candidates:
        if client is not None:
            return resolve_sync_redis_client(client)
    return resolve_sync_redis_client(
        db=get_settings().funboost.filter_and_rpc_result_redis_db
    )


def _write_status_mapping(redis_client: Any, key: str, mapping: dict[str, Any]) -> None:
    normalized_mapping = {str(field): value for field, value in mapping.items()}
    ttl_seconds = get_settings().funboost.status_ttl_seconds
    pipeline_factory = getattr(redis_client, "pipeline", None)
    if callable(pipeline_factory):
        pipeline = pipeline_factory(transaction=True)
        pipeline.hset(key, mapping=normalized_mapping)
        pipeline.expire(key, ttl_seconds)
        pipeline.execute()
        return
    redis_client.hset(key, mapping=normalized_mapping)
    redis_client.expire(key, ttl_seconds)


def write_started_task_status(
    owner: Any,
    task_id: str,
    task_name: str,
    triggered_by: int | None,
    execution_id: int | None = None,
) -> datetime:
    redis_client = resolve_status_redis_client(owner)
    key = f"douyin:task:status:{task_id}"
    started_at = time.time()
    started_at_datetime = _from_timestamp(started_at) or datetime.now(tz=UTC)
    _write_status_mapping(
        redis_client,
        key,
        {
            "status": "STARTED",
            "started_at": started_at,
            "task_name": task_name,
            "triggered_by": triggered_by if triggered_by is not None else "",
            "execution_id": execution_id if execution_id is not None else "",
        },
    )
    _sync_execution_status(
        queue_task_id=task_id,
        status=TaskExecutionStatus.RUNNING,
        started_at=started_at_datetime,
        triggered_by=triggered_by,
    )
    return started_at_datetime


def write_finished_task_status(
    owner: Any,
    task_id: str,
    task_name: str,
    success: bool,
    completed_at: float,
    triggered_by: int | None,
    processed_rows: int | None = None,
    error_message: str | None = None,
) -> None:
    redis_client = resolve_status_redis_client(owner)
    key = f"douyin:task:status:{task_id}"
    _write_status_mapping(
        redis_client,
        key,
        {
            "status": "SUCCESS" if success else "FAILED",
            "completed_at": completed_at,
            "task_name": task_name,
            "triggered_by": triggered_by if triggered_by is not None else "",
            "processed_rows": processed_rows if processed_rows is not None else 0,
            "error_message": error_message or "",
        },
    )
    _sync_execution_status(
        queue_task_id=task_id,
        status=TaskExecutionStatus.SUCCESS if success else TaskExecutionStatus.FAILED,
        completed_at=_from_timestamp(completed_at),
        processed_rows=processed_rows,
        error_message=error_message,
        triggered_by=triggered_by,
    )


def _from_timestamp(timestamp: float | None) -> datetime | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp), tz=UTC)


def _is_shutdown_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc).strip().lower()
    return (
        "cannot schedule new futures after interpreter shutdown" in message
        or "interpreter shutdown" in message
        or "event loop is closed" in message
    )


def _handle_status_sync_task_done(
    task: asyncio.Task[None],
    *,
    queue_task_id: str,
    status: TaskExecutionStatus,
    started_at: datetime | None,
    completed_at: datetime | None,
    processed_rows: int | None,
    error_message: str | None,
    triggered_by: int | None,
) -> None:
    if task.cancelled():
        return
    try:
        task_exception = task.exception()
    except asyncio.CancelledError:
        return
    if task_exception is None:
        return
    logger.error(
        "async status sync failed queue_task_id=%s status=%s triggered_by=%s started_at=%s completed_at=%s",
        queue_task_id,
        status.value,
        triggered_by,
        started_at,
        completed_at,
        exc_info=(
            type(task_exception),
            task_exception,
            task_exception.__traceback__,
        ),
    )
    _start_status_sync_fallback(
        queue_task_id=queue_task_id,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        processed_rows=processed_rows,
        error_message=error_message,
        triggered_by=triggered_by,
    )


def _start_status_sync_fallback(
    *,
    queue_task_id: str,
    status: TaskExecutionStatus,
    started_at: datetime | None,
    completed_at: datetime | None,
    processed_rows: int | None,
    error_message: str | None,
    triggered_by: int | None,
) -> None:
    if sys.is_finalizing():
        return
    thread = threading.Thread(
        target=_run_status_sync_fallback,
        kwargs={
            "queue_task_id": queue_task_id,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "processed_rows": processed_rows,
            "error_message": error_message,
            "triggered_by": triggered_by,
        },
        name=f"task-status-sync-{queue_task_id[:32]}",
        daemon=True,
    )
    thread.start()


def _run_status_sync_fallback(
    *,
    queue_task_id: str,
    status: TaskExecutionStatus,
    started_at: datetime | None,
    completed_at: datetime | None,
    processed_rows: int | None,
    error_message: str | None,
    triggered_by: int | None,
) -> None:
    try:
        asyncio.run(
            _sync_execution_status_async(
                queue_task_id=queue_task_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                processed_rows=processed_rows,
                error_message=error_message,
                triggered_by=triggered_by,
            )
        )
    except RuntimeError as exc:
        if _is_shutdown_runtime_error(exc):
            return
        logger.exception(
            "status sync fallback failed queue_task_id=%s status=%s",
            queue_task_id,
            status.value,
        )
    except Exception:
        logger.exception(
            "status sync fallback failed queue_task_id=%s status=%s",
            queue_task_id,
            status.value,
        )


def _sync_execution_status(
    *,
    queue_task_id: str,
    status: TaskExecutionStatus,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    processed_rows: int | None = None,
    error_message: str | None = None,
    triggered_by: int | None = None,
) -> None:
    if sys.is_finalizing():
        return

    coro = _sync_execution_status_async(
        queue_task_id=queue_task_id,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        processed_rows=processed_rows,
        error_message=error_message,
        triggered_by=triggered_by,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            session_module.run_coro(coro)
        except RuntimeError as exc:
            coro.close()
            if _is_shutdown_runtime_error(exc):
                return
            raise
        return
    try:
        task = loop.create_task(coro)
    except RuntimeError as exc:
        coro.close()
        if _is_shutdown_runtime_error(exc):
            return
        raise
    task.add_done_callback(
        lambda done_task: _handle_status_sync_task_done(
            done_task,
            queue_task_id=queue_task_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            processed_rows=processed_rows,
            error_message=error_message,
            triggered_by=triggered_by,
        )
    )


async def _sync_execution_status_async(
    *,
    queue_task_id: str,
    status: TaskExecutionStatus,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    processed_rows: int | None = None,
    error_message: str | None = None,
    triggered_by: int | None = None,
) -> None:
    session_factory = session_module.async_session_factory
    if session_factory is None:
        return
    async with session_factory() as db_session:
        repo = TaskExecutionRepository(db_session)
        execution = await repo.get_by_queue_task_id(queue_task_id)
        if execution is None:
            return
        update_data: dict[str, Any] = {"status": status}
        if started_at is not None:
            update_data["started_at"] = started_at
        if completed_at is not None:
            update_data["completed_at"] = completed_at
        if processed_rows is not None:
            update_data["processed_rows"] = processed_rows
        if error_message is not None:
            update_data["error_message"] = error_message
        if triggered_by is not None and execution.triggered_by is None:
            update_data["triggered_by"] = triggered_by
        await repo.update(execution, update_data)
        await db_session.commit()
