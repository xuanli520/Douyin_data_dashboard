from __future__ import annotations

import logging
import time
from typing import Any

from src.agents import LLMDashboardAgent
from src.config import get_settings
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import boost, fct
from src.tasks.idempotency import FunboostIdempotencyHelper
from src.tasks.params import CollectionTaskParams

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
    CollectionTaskParams(
        queue_name="collection_shop_dashboard_agent",
        consumer_override_cls=TaskStatusMixin,
        is_push_to_dlx_queue_when_retry_max_times=True,
    )
)
def sync_shop_dashboard_agent(
    shop_id: str,
    date: str,
    reason: str,
    triggered_by: int | None = None,
) -> dict[str, Any]:
    _write_started_status(
        sync_shop_dashboard_agent,
        "sync_shop_dashboard_agent",
        triggered_by,
    )
    redis_client = sync_shop_dashboard_agent.publisher.redis_db_frame
    helper = FunboostIdempotencyHelper(
        redis_client=redis_client,
        task_name="sync_shop_dashboard_agent",
    )
    business_key = f"{shop_id}:{date}:{reason}"

    cached = helper.get_cached_result(business_key)
    if cached:
        return cached

    token = helper.acquire_lock(
        business_key,
        ttl=get_settings().shop_dashboard.lock_ttl_seconds,
    )
    if not token:
        return {
            "status": "skipped",
            "reason": "running",
            "shop_id": shop_id,
            "metric_date": date,
            "source": "llm",
        }

    try:
        patch = LLMDashboardAgent().supplement_cold_data(
            {}, shop_id, date, reason=reason
        )
        result: dict[str, Any] = {
            "status": "success",
            "shop_id": shop_id,
            "metric_date": date,
            "reason": reason,
            "source": "llm",
        }
        for key, value in patch.items():
            if key in {"status", "source", "shop_id", "metric_date", "reason"}:
                continue
            result[key] = value

        helper.cache_result(business_key, result)
        return result
    finally:
        helper.release_lock(business_key, token)
