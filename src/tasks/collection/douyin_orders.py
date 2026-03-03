from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any

from src.config import get_settings
from src.tasks.base import TaskStatusMixin
from src.tasks.exceptions import ScrapingRateLimitException
from src.tasks.funboost_compat import boost, fct
from src.tasks.idempotency import FunboostIdempotencyHelper
from src.tasks.params import CollectionTaskParams

logger = logging.getLogger(__name__)


def _parse_retry_after(value: Any) -> int:
    try:
        retry_after = int(float(value))
    except (TypeError, ValueError):
        return 1
    return retry_after if retry_after > 0 else 0


def retry_with_backoff(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ScrapingRateLimitException as exc:
            retry_after = _parse_retry_after(exc.error_data.get("retry_after", 1))
            if retry_after > 0:
                time.sleep(retry_after)
            raise

    return wrapper


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
    CollectionTaskParams(
        queue_name="collection_orders",
        consumer_override_cls=TaskStatusMixin,
        consuming_function_decorator=retry_with_backoff,
        is_push_to_dlx_queue_when_retry_max_times=True,
    )
)
def sync_orders(
    shop_id: str, date: str, triggered_by: int | None = None
) -> dict[str, Any]:
    _write_started_status(sync_orders, "sync_orders", triggered_by)
    redis_client = sync_orders.publisher.redis_db_frame
    helper = FunboostIdempotencyHelper(
        redis_client=redis_client, task_name="sync_orders"
    )
    business_key = f"{shop_id}:{date}"

    cached = helper.get_cached_result(business_key)
    if cached:
        return cached

    token = helper.acquire_lock(business_key, ttl=3600)
    if not token:
        return {"status": "skipped", "reason": "running"}

    try:
        helper.refresh_lock(business_key, token, 3600)
        result = {
            "status": "success",
            "shop_id": shop_id,
            "date": date,
            "synced_orders": 0,
            "triggered_by": triggered_by,
        }
        helper.cache_result(business_key, result)
        return result
    finally:
        helper.release_lock(business_key, token)


@boost(
    CollectionTaskParams(
        queue_name="collection_orders_dlx",
        consumer_override_cls=TaskStatusMixin,
    )
)
def handle_collection_orders_dead_letter(**payload) -> dict[str, Any]:
    return {
        "status": "recorded",
        "queue": "collection_orders_dlx",
        "payload": payload,
    }
