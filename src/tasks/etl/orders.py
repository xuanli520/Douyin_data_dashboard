from __future__ import annotations

import logging
from typing import Any

from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import boost, fct
from src.tasks.params import EtlTaskParams
from src.tasks.status_store import write_started_task_status

logger = logging.getLogger(__name__)


def _write_started_status(task_func, task_name: str, triggered_by: int | None) -> None:
    try:
        task_id = str(getattr(fct, "task_id", "unknown"))
        write_started_task_status(
            owner=task_func,
            task_id=task_id,
            task_name=task_name,
            triggered_by=triggered_by,
        )
    except Exception:
        logger.exception("failed to write started task status: %s", task_name)


@boost(
    EtlTaskParams(
        queue_name="etl_orders",
        consumer_override_cls=TaskStatusMixin,
        is_push_to_dlx_queue_when_retry_max_times=True,
    )
)
def process_orders(batch_date: str, triggered_by: int | None = None) -> dict[str, Any]:
    _write_started_status(process_orders, "process_orders", triggered_by)
    return {
        "status": "success",
        "batch_date": batch_date,
        "processed_rows": 0,
        "triggered_by": triggered_by,
    }


@boost(
    EtlTaskParams(
        queue_name="etl_orders_dlx",
        consumer_override_cls=TaskStatusMixin,
    )
)
def handle_etl_orders_dead_letter(**payload) -> dict[str, Any]:
    return {"status": "recorded", "queue": "etl_orders_dlx", "payload": payload}
