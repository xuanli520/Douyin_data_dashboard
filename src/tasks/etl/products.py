from __future__ import annotations

import logging
import time
from typing import Any

from src.config import get_settings
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import boost, fct
from src.tasks.params import EtlTaskParams

logger = logging.getLogger(__name__)


def _write_started_status(task_func, task_name: str, triggered_by: int | None) -> None:
    try:
        redis_client = task_func.publisher.redis_db_frame
        task_id = str(getattr(fct, "task_id", "unknown"))
        key = f"douyin:task:status:{task_id}"
        redis_client.hset(
            key,
            mapping={
                "status": "STARTED",
                "started_at": time.time(),
                "task_name": task_name,
                "triggered_by": triggered_by if triggered_by is not None else "",
            },
        )
        redis_client.expire(key, get_settings().funboost.status_ttl_seconds)
    except Exception:
        logger.exception("failed to write started task status: %s", task_name)


@boost(
    EtlTaskParams(
        queue_name="etl_products",
        consumer_override_cls=TaskStatusMixin,
        is_push_to_dlx_queue_when_retry_max_times=True,
    )
)
def process_products(
    batch_date: str, triggered_by: int | None = None
) -> dict[str, Any]:
    _write_started_status(process_products, "process_products", triggered_by)
    return {
        "status": "success",
        "batch_date": batch_date,
        "processed_rows": 0,
        "triggered_by": triggered_by,
    }


@boost(
    EtlTaskParams(
        queue_name="etl_products_dlx",
        consumer_override_cls=TaskStatusMixin,
    )
)
def handle_etl_products_dead_letter(**payload) -> dict[str, Any]:
    return {"status": "recorded", "queue": "etl_products_dlx", "payload": payload}
