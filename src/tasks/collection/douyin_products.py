from __future__ import annotations

import time
from typing import Any

from src.config import get_settings
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import boost, fct
from src.tasks.params import CollectionTaskParams


def _write_started_status(task_func, task_name: str, triggered_by: int | None) -> None:
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


@boost(
    CollectionTaskParams(
        queue_name="collection_products",
        consumer_override_cls=TaskStatusMixin,
        is_push_to_dlx_queue_when_retry_max_times=True,
    )
)
def sync_products(
    shop_id: str, date: str, triggered_by: int | None = None
) -> dict[str, Any]:
    _write_started_status(sync_products, "sync_products", triggered_by)
    return {
        "status": "success",
        "shop_id": shop_id,
        "date": date,
        "synced_products": 0,
        "triggered_by": triggered_by,
    }


@boost(
    CollectionTaskParams(
        queue_name="collection_products_dlx",
        consumer_override_cls=TaskStatusMixin,
    )
)
def handle_collection_products_dead_letter(**payload) -> dict[str, Any]:
    return {
        "status": "recorded",
        "queue": "collection_products_dlx",
        "payload": payload,
    }
