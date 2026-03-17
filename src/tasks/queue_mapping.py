from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domains.task.enums import TaskType

TASK_TYPE_QUEUE_NAME_MAPPING: dict[TaskType, str] = {
    TaskType.ETL_ORDERS: "etl_orders",
    TaskType.ETL_PRODUCTS: "etl_products",
    TaskType.SHOP_DASHBOARD_COLLECTION: "collection_shop_dashboard",
}


def validate_task_type_queue_mapping(task_func_mapping: Mapping[TaskType, Any]) -> None:
    for task_type, task_func in task_func_mapping.items():
        assert_task_type_queue_mapping(task_type, task_func)


def assert_task_type_queue_mapping(task_type: TaskType, task_func: Any) -> None:
    expected_queue_name = TASK_TYPE_QUEUE_NAME_MAPPING.get(task_type)
    if not expected_queue_name:
        return
    actual_queue_name = str(
        getattr(getattr(task_func, "boost_params", None), "queue_name", "") or ""
    )
    if actual_queue_name and actual_queue_name != expected_queue_name:
        raise ValueError(
            f"task_type={task_type.value} queue_mismatch expected={expected_queue_name} actual={actual_queue_name}"
        )
