from types import SimpleNamespace

import pytest

from src.domains.task.enums import TaskExecutionStatus, TaskTriggerMode, TaskType
from src.domains.task.schemas import TaskDefinitionCreate
from src.domains.task.services import TaskService


@pytest.mark.asyncio
async def test_run_task_dispatches_by_task_type_and_persists_queued_execution(
    test_db, monkeypatch
):
    from src.domains.task import services as module

    called = {"orders": 0, "products": 0, "shop": 0}

    def _orders_push(**kwargs):
        called["orders"] += 1
        assert kwargs["batch_date"] == "2026-03-08"
        return SimpleNamespace(task_id="queue-orders-1")

    def _products_push(**kwargs):
        called["products"] += 1
        assert kwargs["batch_date"] == "2026-03-08"
        return SimpleNamespace(task_id="queue-products-1")

    def _shop_push(**kwargs):
        called["shop"] += 1
        assert kwargs["data_source_id"] == 10
        assert kwargs["rule_id"] == 20
        assert kwargs["shop_id"] == "shop-10"
        assert kwargs["shop_ids"] == ["shop-10", "shop-11"]
        assert kwargs["granularity"] == "HOUR"
        assert kwargs["timezone"] == "Asia/Shanghai"
        assert kwargs["time_range"] == {
            "start": "2026-03-01",
            "end": "2026-03-02",
        }
        assert kwargs["incremental_mode"] == "BY_CURSOR"
        assert kwargs["backfill_last_n_days"] == 14
        assert kwargs["data_latency"] == "T+2"
        assert kwargs["filters"] == {
            "shop_id": ["shop-10", "shop-11"],
            "region": "east",
        }
        assert kwargs["dimensions"] == ["shop", "category"]
        assert kwargs["metrics"] == ["overview", "analysis"]
        assert kwargs["dedupe_key"] == "{shop_id}:{window_start}"
        assert kwargs["rate_limit"] == {"qps": 2, "burst": 4}
        assert kwargs["top_n"] == 50
        assert kwargs["sort_by"] == "-score"
        assert kwargs["include_long_tail"] is True
        assert kwargs["session_level"] is True
        assert kwargs["extra_config"] == {"cursor": "cursor-1"}
        return SimpleNamespace(task_id="queue-shop-1")

    monkeypatch.setattr(module.process_orders, "push", _orders_push, raising=False)
    monkeypatch.setattr(module.process_products, "push", _products_push, raising=False)
    monkeypatch.setattr(module.sync_shop_dashboard, "push", _shop_push, raising=False)

    async with test_db() as session:
        service = TaskService(session)
        task_orders = await service.create_task(
            TaskDefinitionCreate(name="orders", task_type=TaskType.ETL_ORDERS),
            created_by_id=1,
        )
        task_products = await service.create_task(
            TaskDefinitionCreate(name="products", task_type=TaskType.ETL_PRODUCTS),
            created_by_id=1,
        )
        task_shop = await service.create_task(
            TaskDefinitionCreate(
                name="shop",
                task_type=TaskType.SHOP_DASHBOARD_COLLECTION,
            ),
            created_by_id=1,
        )

        orders_execution = await service.run_task(
            task_id=task_orders.id if task_orders.id is not None else 0,
            payload={"batch_date": "2026-03-08"},
            triggered_by=99,
            trigger_mode=TaskTriggerMode.MANUAL,
        )
        products_execution = await service.run_task(
            task_id=task_products.id if task_products.id is not None else 0,
            payload={"batch_date": "2026-03-08"},
            triggered_by=99,
            trigger_mode=TaskTriggerMode.MANUAL,
        )
        shop_execution = await service.run_task(
            task_id=task_shop.id if task_shop.id is not None else 0,
            payload={
                "data_source_id": 10,
                "rule_id": 20,
                "execution_id": "shop-exec-1",
                "shop_id": "shop-10",
                "shop_ids": ["shop-10", "shop-11"],
                "granularity": "HOUR",
                "timezone": "Asia/Shanghai",
                "time_range": {
                    "start": "2026-03-01",
                    "end": "2026-03-02",
                },
                "incremental_mode": "BY_CURSOR",
                "backfill_last_n_days": 14,
                "data_latency": "T+2",
                "filters": {"shop_id": ["shop-10", "shop-11"], "region": "east"},
                "dimensions": ["shop", "category"],
                "metrics": ["overview", "analysis"],
                "dedupe_key": "{shop_id}:{window_start}",
                "rate_limit": {"qps": 2, "burst": 4},
                "top_n": 50,
                "sort_by": "-score",
                "include_long_tail": True,
                "session_level": True,
                "extra_config": {"cursor": "cursor-1"},
            },
            triggered_by=99,
            trigger_mode=TaskTriggerMode.MANUAL,
        )

    assert called == {"orders": 1, "products": 1, "shop": 1}
    assert orders_execution.status == TaskExecutionStatus.QUEUED
    assert products_execution.status == TaskExecutionStatus.QUEUED
    assert shop_execution.status == TaskExecutionStatus.QUEUED
    assert orders_execution.queue_task_id == "queue-orders-1"
    assert products_execution.queue_task_id == "queue-products-1"
    assert shop_execution.queue_task_id == "queue-shop-1"
