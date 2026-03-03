def test_tasks_package_imports_task_modules():
    import src.tasks as tasks

    assert hasattr(tasks, "douyin_orders")
    assert hasattr(tasks, "douyin_products")
    assert hasattr(tasks, "etl_orders")
    assert hasattr(tasks, "etl_products")


def test_worker_run_all_dispatches_consumers(monkeypatch):
    from src.tasks import worker as module

    calls = []
    monkeypatch.setattr(
        module.douyin_orders.sync_orders,
        "consume",
        lambda: calls.append("collection_orders"),
        raising=False,
    )
    monkeypatch.setattr(
        module.douyin_products.sync_products,
        "consume",
        lambda: calls.append("collection_products"),
        raising=False,
    )
    monkeypatch.setattr(
        module.etl_orders.process_orders,
        "multi_process_consume",
        lambda n: calls.append(("etl_orders", n)),
        raising=False,
    )
    monkeypatch.setattr(
        module.etl_products.process_products,
        "multi_process_consume",
        lambda n: calls.append(("etl_products", n)),
        raising=False,
    )

    module.run_all(etl_processes=2)
    assert calls == [
        "collection_orders",
        "collection_products",
        ("etl_orders", 2),
        ("etl_products", 2),
    ]
