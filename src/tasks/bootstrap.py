from __future__ import annotations

from datetime import date as date_type
from typing import Any

from src.domains.task.dispatch import TaskDispatcherRegistry
from src.domains.task.enums import TaskType
from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard
from src.tasks.etl.orders import process_orders
from src.tasks.etl.products import process_products
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

TASK_TYPE_QUEUE_NAME_MAPPING: dict[TaskType, str] = {
    TaskType.ETL_ORDERS: "etl_orders",
    TaskType.ETL_PRODUCTS: "etl_products",
    TaskType.SHOP_DASHBOARD_COLLECTION: "collection_shop_dashboard",
}

TASK_TYPE_TASK_FUNC_MAPPING: dict[TaskType, Any] = {
    TaskType.ETL_ORDERS: process_orders,
    TaskType.ETL_PRODUCTS: process_products,
    TaskType.SHOP_DASHBOARD_COLLECTION: sync_shop_dashboard,
}


def build_task_dispatcher_registry() -> TaskDispatcherRegistry:
    _ensure_task_type_queue_mapping()
    registry = TaskDispatcherRegistry()
    registry.register(TaskType.ETL_ORDERS, _dispatch_orders)
    registry.register(TaskType.ETL_PRODUCTS, _dispatch_products)
    registry.register(TaskType.SHOP_DASHBOARD_COLLECTION, _dispatch_shop_dashboard)
    return registry


def _ensure_task_type_queue_mapping() -> None:
    for task_type, expected_queue_name in TASK_TYPE_QUEUE_NAME_MAPPING.items():
        task_func = TASK_TYPE_TASK_FUNC_MAPPING[task_type]
        actual_queue_name = str(
            getattr(getattr(task_func, "boost_params", None), "queue_name", "") or ""
        )
        if actual_queue_name and actual_queue_name != expected_queue_name:
            raise ValueError(
                f"task_type {task_type.value} queue mismatch: {actual_queue_name}"
            )


def _dispatch_orders(
    payload: dict[str, Any],
    triggered_by: int | None,
    execution_id: int,
) -> Any:
    return process_orders.push(
        batch_date=_resolve_batch_date(payload),
        triggered_by=triggered_by,
        execution_id=execution_id,
    )


def _dispatch_products(
    payload: dict[str, Any],
    triggered_by: int | None,
    execution_id: int,
) -> Any:
    return process_products.push(
        batch_date=_resolve_batch_date(payload),
        triggered_by=triggered_by,
        execution_id=execution_id,
    )


def _dispatch_shop_dashboard(
    payload: dict[str, Any],
    triggered_by: int | None,
    execution_id: int,
) -> Any:
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
    return sync_shop_dashboard.push(**dispatch_kwargs)


def _resolve_batch_date(payload: dict[str, Any]) -> str:
    raw = payload.get("batch_date")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return date_type.today().isoformat()
