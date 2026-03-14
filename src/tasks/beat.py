from __future__ import annotations

import asyncio
import time
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
from src.tasks.bootstrap import (
    SHOP_DASHBOARD_OVERRIDE_KEYS,
    TASK_TYPE_QUEUE_NAME_MAPPING,
    TASK_TYPE_TASK_FUNC_MAPPING,
)
from src.tasks.funboost_compat import ApsJobAdder
from src.scrapers.shop_dashboard.shop_selection_validator import (
    normalize_shop_selection_payload,
)


def register_jobs() -> None:
    collection_jobs = _load_enabled_collection_jobs()
    jobs_by_task_type: dict[TaskType, list[CollectionJob]] = defaultdict(list)
    for collection_job in collection_jobs:
        jobs_by_task_type[collection_job.task_type].append(collection_job)

    for task_type, jobs in jobs_by_task_type.items():
        task_func = TASK_TYPE_TASK_FUNC_MAPPING.get(task_type)
        if task_func is None:
            continue
        _assert_task_type_queue_mapping(task_type, task_func)
        job_adder = ApsJobAdder(task_func, job_store_kind="redis")
        for collection_job in jobs:
            schedule = ScheduleConfig.model_validate(collection_job.schedule or {})
            job_adder.add_push_job(
                **schedule.to_aps_job_kwargs(),
                kwargs=_build_dispatch_kwargs(collection_job, schedule),
                id=f"collection_job_{collection_job.id}",
                replace_existing=True,
            )


def _assert_task_type_queue_mapping(task_type: TaskType, task_func: Any) -> None:
    expected_queue_name = TASK_TYPE_QUEUE_NAME_MAPPING.get(task_type)
    if not expected_queue_name:
        return
    actual_queue_name = str(
        getattr(getattr(task_func, "boost_params", None), "queue_name", "") or ""
    )
    if actual_queue_name and actual_queue_name != expected_queue_name:
        raise ValueError(
            f"task_type {task_type.value} queue mismatch: {actual_queue_name}"
        )


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


def _load_enabled_collection_jobs() -> list[CollectionJob]:
    return asyncio.run(_load_enabled_collection_jobs_async())


async def _load_enabled_collection_jobs_async() -> list[CollectionJob]:
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


def _init_scheduler_db() -> None:
    settings = get_settings()
    asyncio.run(session.init_db(settings.db.url, settings.db.echo))


def main() -> None:
    _init_scheduler_db()
    register_jobs()
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
