from __future__ import annotations

from datetime import date as date_type
from typing import Any

from src.domains.task.dispatch import TaskDispatcherRegistry
from src.domains.task.enums import TaskType
from src.tasks.queue_mapping import validate_task_type_queue_mapping
from src.tasks.registry import get_task_func, get_task_type_task_func_mapping
from src.scrapers.shop_dashboard.shop_selection_validator import (
    normalize_shop_selection_payload,
)

SHOP_DASHBOARD_OVERRIDE_KEYS: tuple[str, ...] = (
    "shop_id",
    "shop_ids",
    "all",
    "granularity",
    "timezone",
    "time_range",
    "incremental_mode",
    "backfill_last_n_days",
    "data_latency",
    "filters",
    "dimensions",
    "metrics",
    "dedupe_key",
    "rate_limit",
    "top_n",
    "sort_by",
    "include_long_tail",
    "session_level",
    "extra_config",
)


def build_task_dispatcher_registry() -> TaskDispatcherRegistry:
    validate_task_type_queue_mapping(get_task_type_task_func_mapping())
    registry = TaskDispatcherRegistry()
    registry.register(TaskType.ETL_ORDERS, _dispatch_orders)
    registry.register(TaskType.ETL_PRODUCTS, _dispatch_products)
    registry.register(TaskType.SHOP_DASHBOARD_COLLECTION, _dispatch_shop_dashboard)
    return registry


def _dispatch_orders(
    payload: dict[str, Any],
    triggered_by: int | None,
    execution_id: int,
) -> Any:
    task_func = _require_task_func(TaskType.ETL_ORDERS)
    return task_func.push(
        batch_date=_resolve_batch_date(payload),
        triggered_by=triggered_by,
        execution_id=execution_id,
    )


def _dispatch_products(
    payload: dict[str, Any],
    triggered_by: int | None,
    execution_id: int,
) -> Any:
    task_func = _require_task_func(TaskType.ETL_PRODUCTS)
    return task_func.push(
        batch_date=_resolve_batch_date(payload),
        triggered_by=triggered_by,
        execution_id=execution_id,
    )


def _dispatch_shop_dashboard(
    payload: dict[str, Any],
    triggered_by: int | None,
    execution_id: int,
) -> Any:
    task_func = _require_task_func(TaskType.SHOP_DASHBOARD_COLLECTION)
    normalized_payload = normalize_shop_selection_payload(payload)
    dispatch_kwargs: dict[str, Any] = {
        "data_source_id": normalized_payload["data_source_id"],
        "rule_id": normalized_payload["rule_id"],
        "execution_id": str(
            normalized_payload.get("execution_id") or f"task-execution-{execution_id}"
        ),
        "triggered_by": triggered_by,
    }
    for key in SHOP_DASHBOARD_OVERRIDE_KEYS:
        if key in normalized_payload:
            dispatch_kwargs[key] = normalized_payload[key]
    return task_func.push(**dispatch_kwargs)


def _require_task_func(task_type: TaskType) -> Any:
    task_func = get_task_func(task_type)
    if task_func is None:
        raise RuntimeError(f"task function not found for task_type={task_type.value}")
    return task_func


def _resolve_batch_date(payload: dict[str, Any]) -> str:
    raw = payload.get("batch_date")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return date_type.today().isoformat()
