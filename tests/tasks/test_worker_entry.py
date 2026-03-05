def test_tasks_package_imports_task_modules():
    import src.tasks as tasks

    assert hasattr(tasks, "douyin_orders")
    assert hasattr(tasks, "douyin_products")
    assert hasattr(tasks, "douyin_shop_dashboard")
    assert hasattr(tasks, "douyin_shop_agent")
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
        module.douyin_shop_dashboard.sync_shop_dashboard,
        "consume",
        lambda: calls.append("collection_shop_dashboard"),
        raising=False,
    )
    monkeypatch.setattr(
        module.douyin_shop_agent.sync_shop_dashboard_agent,
        "consume",
        lambda: calls.append("collection_shop_dashboard_agent"),
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
    monkeypatch.setattr(
        module.douyin_orders.handle_collection_orders_dead_letter,
        "consume",
        lambda: calls.append("collection_orders_dlx"),
        raising=False,
    )
    monkeypatch.setattr(
        module.douyin_products.handle_collection_products_dead_letter,
        "consume",
        lambda: calls.append("collection_products_dlx"),
        raising=False,
    )
    monkeypatch.setattr(
        module.douyin_shop_dashboard.handle_collection_shop_dashboard_dead_letter,
        "consume",
        lambda: calls.append("collection_shop_dashboard_dlx"),
        raising=False,
    )
    monkeypatch.setattr(
        module.etl_orders.handle_etl_orders_dead_letter,
        "consume",
        lambda: calls.append("etl_orders_dlx"),
        raising=False,
    )
    monkeypatch.setattr(
        module.etl_products.handle_etl_products_dead_letter,
        "consume",
        lambda: calls.append("etl_products_dlx"),
        raising=False,
    )

    class _FakeThread:
        def __init__(self, target, name):
            self._target = target
            self.name = name

        def start(self):
            self._target()

        def join(self):
            return None

    monkeypatch.setattr(module, "Thread", _FakeThread)

    module.run_all(etl_processes=2)
    assert len(calls) == 11
    assert {
        "collection_orders",
        "collection_products",
        "collection_shop_dashboard",
        "collection_shop_dashboard_agent",
        ("etl_orders", 2),
        ("etl_products", 2),
        "collection_orders_dlx",
        "collection_products_dlx",
        "collection_shop_dashboard_dlx",
        "etl_orders_dlx",
        "etl_products_dlx",
    } == set(calls)


def test_worker_run_queue_supports_dead_letter_queue(monkeypatch):
    from src.tasks import worker as module

    calls = []
    monkeypatch.setattr(
        module.etl_orders.handle_etl_orders_dead_letter,
        "consume",
        lambda: calls.append("etl_orders_dlx"),
        raising=False,
    )

    module.run_queue("etl_orders_dlx", etl_processes=2)
    assert calls == ["etl_orders_dlx"]
