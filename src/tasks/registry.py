from __future__ import annotations

from typing import Any

from src.domains.task.enums import TaskType


def get_task_func(task_type: TaskType) -> Any | None:
    if task_type == TaskType.ETL_ORDERS:
        from src.tasks.etl.orders import process_orders

        return process_orders
    if task_type == TaskType.ETL_PRODUCTS:
        from src.tasks.etl.products import process_products

        return process_products
    if task_type == TaskType.SHOP_DASHBOARD_COLLECTION:
        from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard

        return sync_shop_dashboard
    return None


def get_task_type_task_func_mapping() -> dict[TaskType, Any]:
    task_func_mapping: dict[TaskType, Any] = {}
    for task_type in (
        TaskType.ETL_ORDERS,
        TaskType.ETL_PRODUCTS,
        TaskType.SHOP_DASHBOARD_COLLECTION,
    ):
        task_func = get_task_func(task_type)
        if task_func is not None:
            task_func_mapping[task_type] = task_func
    return task_func_mapping
