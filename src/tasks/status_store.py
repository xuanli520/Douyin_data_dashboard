from __future__ import annotations

import time
from typing import Any

from src.config import get_settings


def resolve_status_redis_client(owner: Any) -> Any | None:
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
            return client
    return None


def _hset_field_compat(redis_client: Any, key: str, field: str, value: Any) -> None:
    try:
        redis_client.hset(key, field, value)
    except TypeError:
        redis_client.hset(key, {field: value})


def _hset_mapping_compat(redis_client: Any, key: str, mapping: dict[str, Any]) -> None:
    for field, value in mapping.items():
        _hset_field_compat(redis_client, key, str(field), value)


def write_started_task_status(
    owner: Any,
    task_id: str,
    task_name: str,
    triggered_by: int | None,
) -> None:
    redis_client = resolve_status_redis_client(owner)
    if redis_client is None:
        raise RuntimeError("status redis client is unavailable")
    key = f"douyin:task:status:{task_id}"
    _hset_mapping_compat(
        redis_client,
        key,
        {
            "status": "STARTED",
            "started_at": time.time(),
            "task_name": task_name,
            "triggered_by": triggered_by if triggered_by is not None else "",
        },
    )
    redis_client.expire(key, get_settings().funboost.status_ttl_seconds)


def write_finished_task_status(
    owner: Any,
    task_id: str,
    task_name: str,
    success: bool,
    completed_at: float,
    triggered_by: int | None,
) -> None:
    redis_client = resolve_status_redis_client(owner)
    if redis_client is None:
        raise RuntimeError("status redis client is unavailable")
    key = f"douyin:task:status:{task_id}"
    _hset_mapping_compat(
        redis_client,
        key,
        {
            "status": "SUCCESS" if success else "FAILURE",
            "completed_at": completed_at,
            "task_name": task_name,
            "triggered_by": triggered_by if triggered_by is not None else "",
        },
    )
    redis_client.expire(key, get_settings().funboost.status_ttl_seconds)
