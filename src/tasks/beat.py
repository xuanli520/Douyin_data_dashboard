from __future__ import annotations

import asyncio
import logging
import signal
from collections import defaultdict
from datetime import date as date_type
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from src import session
from src.config import get_settings
from src.domains.collection_job.models import CollectionJob
from src.domains.collection_job.schemas import ScheduleConfig
from src.domains.collection_job.services import CollectionJobService
from src.domains.task.enums import TaskType
from src.scrapers.shop_dashboard.shop_selection_validator import (
    normalize_shop_selection_payload,
)
from src.tasks.bootstrap import SHOP_DASHBOARD_OVERRIDE_KEYS
from src.tasks.funboost_compat import ApsJobAdder
from src.tasks.queue_mapping import assert_task_type_queue_mapping
from src.tasks.registry import get_task_type_task_func_mapping

logger = logging.getLogger(__name__)


async def register_jobs() -> Any | None:
    collection_jobs = await _load_enabled_collection_jobs()
    jobs_by_task_type: dict[TaskType, list[CollectionJob]] = defaultdict(list)
    for collection_job in collection_jobs:
        jobs_by_task_type[collection_job.task_type].append(collection_job)

    task_func_mapping = get_task_type_task_func_mapping()
    job_adders: dict[TaskType, Any] = {}
    scheduler_aps_obj: Any | None = None
    for task_type in jobs_by_task_type:
        task_func = task_func_mapping.get(task_type)
        if task_func is None:
            continue
        assert_task_type_queue_mapping(task_type, task_func)
        job_adder = ApsJobAdder(task_func, job_store_kind="redis")
        job_adders[task_type] = job_adder
        if scheduler_aps_obj is None:
            scheduler_aps_obj = getattr(job_adder, "aps_obj", None)

    active_job_ids = {
        f"collection_job_{collection_job.id}" for collection_job in collection_jobs
    }
    if scheduler_aps_obj is None and not job_adders:
        scheduler_aps_obj = _resolve_scheduler_aps_obj(task_func_mapping)
    _remove_stale_collection_jobs(active_job_ids, scheduler_aps_obj=scheduler_aps_obj)

    for task_type, jobs in jobs_by_task_type.items():
        job_adder = job_adders.get(task_type)
        if job_adder is None:
            continue
        for collection_job in jobs:
            schedule = ScheduleConfig.model_validate(collection_job.schedule or {})
            job_adder.add_push_job(
                **schedule.to_aps_job_kwargs(),
                kwargs=_build_dispatch_kwargs(collection_job, schedule),
                id=f"collection_job_{collection_job.id}",
                replace_existing=True,
            )
    return scheduler_aps_obj


def _remove_stale_collection_jobs(
    active_job_ids: set[str],
    *,
    scheduler_aps_obj: Any | None = None,
) -> None:
    aps_obj = scheduler_aps_obj
    if aps_obj is None:
        return
    get_jobs = getattr(aps_obj, "get_jobs", None)
    remove_job = getattr(aps_obj, "remove_job", None)
    if not callable(get_jobs) or not callable(remove_job):
        return
    for job in get_jobs():
        job_id = _resolve_job_id(job)
        if not job_id.startswith("collection_job_"):
            continue
        if job_id in active_job_ids:
            continue
        remove_job(job_id)


def _resolve_scheduler_aps_obj(task_func_mapping: dict[TaskType, Any]) -> Any | None:
    for task_func in task_func_mapping.values():
        if task_func is None:
            continue
        return getattr(
            ApsJobAdder(task_func, job_store_kind="redis"),
            "aps_obj",
            None,
        )
    return None


def _resolve_job_id(job: Any) -> str:
    if isinstance(job, dict):
        return str(job.get("id", "") or "")
    return str(getattr(job, "id", "") or "")


def _build_dispatch_kwargs(
    collection_job: CollectionJob,
    schedule: ScheduleConfig,
) -> dict[str, Any]:
    schedule_kwargs = dict(schedule.kwargs)
    execution_id = str(schedule_kwargs.pop("execution_id", "") or "").strip()
    if not execution_id:
        execution_id = f"cron_collection_job_{collection_job.id}"

    if collection_job.task_type == TaskType.SHOP_DASHBOARD_COLLECTION:
        kwargs: dict[str, Any] = {
            "data_source_id": collection_job.data_source_id,
            "rule_id": collection_job.rule_id,
            "execution_id": execution_id,
            "triggered_by": None,
        }
        for key in SHOP_DASHBOARD_OVERRIDE_KEYS:
            if key in schedule_kwargs:
                kwargs[key] = schedule_kwargs[key]
        return normalize_shop_selection_payload(kwargs)

    if collection_job.task_type in {TaskType.ETL_ORDERS, TaskType.ETL_PRODUCTS}:
        raw_batch_date = schedule_kwargs.get("batch_date")
        batch_date = str(raw_batch_date).strip() if raw_batch_date is not None else ""
        if not batch_date:
            batch_date = date_type.today().isoformat()
        schedule_kwargs["batch_date"] = batch_date

    return {
        "triggered_by": None,
        "execution_id": execution_id,
        **schedule_kwargs,
    }


async def _load_enabled_collection_jobs() -> list[CollectionJob]:
    session_factory = session.async_session_factory
    if session_factory is None:
        return []
    async with session_factory() as db_session:
        await _ensure_collection_jobs_table_ready(db_session)
        service = CollectionJobService(session=db_session)
        return await service.list_enabled_jobs()


async def _ensure_collection_jobs_table_ready(db_session: AsyncSession) -> None:
    has_table = await db_session.run_sync(
        lambda sync_session: inspect(sync_session.connection()).has_table(
            "collection_jobs"
        )
    )
    if not has_table:
        raise RuntimeError(
            "collection_jobs table is missing; run alembic upgrade f4d5c6b7a8e9 before starting beat"
        )


def _configure_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        if not stop_event.is_set():
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except (NotImplementedError, RuntimeError):
            try:
                signal.signal(sig, lambda _signo, _frame: _request_shutdown())
            except ValueError:
                continue


def _shutdown_scheduler(scheduler_aps_obj: Any | None) -> None:
    if scheduler_aps_obj is None:
        return
    for method_name in ("shutdown", "stop", "close"):
        method = getattr(scheduler_aps_obj, method_name, None)
        if not callable(method):
            continue
        try:
            method(wait=False)
        except TypeError:
            method()
        except Exception:
            logger.exception("failed to stop beat scheduler method=%s", method_name)
        return


async def main_async() -> None:
    settings = get_settings()
    stop_event = asyncio.Event()
    scheduler_aps_obj: Any | None = None
    await session.init_db(settings.db.url, settings.db.echo)
    _configure_signal_handlers(stop_event)
    try:
        scheduler_aps_obj = await register_jobs()
        await stop_event.wait()
    finally:
        _shutdown_scheduler(scheduler_aps_obj)
        await session.close_db()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
