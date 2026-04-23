import pytest
from types import SimpleNamespace


def test_tasks_package_imports_task_modules():
    import src.tasks as tasks

    assert hasattr(tasks, "douyin_shop_dashboard")
    assert hasattr(tasks, "douyin_shop_agent")
    assert hasattr(tasks, "etl_orders")
    assert hasattr(tasks, "etl_products")


def test_worker_run_all_dispatches_consumers(monkeypatch):
    from src.tasks import worker as module

    calls = []
    waited_runtimes = []

    def _fake_wait_forever(*_args, **kwargs):
        waited_runtimes.extend(kwargs.get("runtimes") or [])

    monkeypatch.setattr(module, "_wait_forever", _fake_wait_forever)
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
        module.douyin_shop_dashboard.handle_collection_shop_dashboard_dead_letter,
        "consume",
        lambda: calls.append("collection_shop_dashboard_dlx"),
        raising=False,
    )
    monkeypatch.setattr(
        module.douyin_shop_agent.handle_collection_shop_dashboard_agent_dead_letter,
        "consume",
        lambda: calls.append("collection_shop_dashboard_agent_dlx"),
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
        def __init__(self, target, name, daemon=False):
            self._target = target
            self.name = name
            self._started = False

        def start(self):
            self._started = True
            self._target()

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return False

    monkeypatch.setattr(module, "Thread", _FakeThread)

    module.run_all(etl_processes=2)
    assert len(calls) == 8
    assert len(waited_runtimes) == 6
    assert {runtime.queue_name for runtime in waited_runtimes} == {
        "collection_shop_dashboard",
        "collection_shop_dashboard_agent",
        "collection_shop_dashboard_dlx",
        "collection_shop_dashboard_agent_dlx",
        "etl_orders_dlx",
        "etl_products_dlx",
    }
    assert {
        "collection_shop_dashboard",
        "collection_shop_dashboard_agent",
        ("etl_orders", 2),
        ("etl_products", 2),
        "collection_shop_dashboard_dlx",
        "collection_shop_dashboard_agent_dlx",
        "etl_orders_dlx",
        "etl_products_dlx",
    } == set(calls)


def test_worker_run_all_waits_for_non_blocking_consumers(monkeypatch):
    from src.tasks import worker as module

    calls = []

    monkeypatch.setattr(
        module,
        "_queue_runners",
        lambda _etl_processes: {
            "collection_shop_dashboard": lambda: calls.append("consume_started")
        },
    )

    class _FakeThread:
        def __init__(self, target, name, daemon=False):
            self._target = target
            self.name = name

        def start(self):
            self._target()

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return False

    monkeypatch.setattr(module, "Thread", _FakeThread)
    monkeypatch.setattr(
        module, "_wait_forever", lambda *_args, **_kwargs: calls.append("wait_forever")
    )

    module.run_all(etl_processes=2)

    assert calls == ["consume_started", "wait_forever"]


def test_worker_run_all_keeps_parent_alive_when_multiprocess_runner_returns(
    monkeypatch,
):
    from src.tasks import worker as module

    calls = []

    monkeypatch.setattr(
        module,
        "_queue_runners",
        lambda _etl_processes: {"etl_orders": lambda: calls.append("etl_orders")},
    )

    class _FakeThread:
        def __init__(self, target, name, daemon=False):
            self._target = target
            self.name = name

        def start(self):
            self._target()

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return False

    monkeypatch.setattr(module, "Thread", _FakeThread)
    monkeypatch.setattr(
        module, "_wait_forever", lambda *_args, **_kwargs: calls.append("wait_forever")
    )

    module.run_all(etl_processes=2)

    assert calls == ["etl_orders", "wait_forever"]


def test_worker_run_all_raises_when_multiprocess_runner_fails_to_start(monkeypatch):
    from src.tasks import worker as module

    calls = []

    def _raise() -> None:
        calls.append("runner")
        raise RuntimeError("startup failed")

    monkeypatch.setattr(
        module,
        "_queue_runners",
        lambda _etl_processes: {"etl_orders": _raise},
    )
    monkeypatch.setattr(
        module, "_wait_forever", lambda *_args, **_kwargs: calls.append("wait_forever")
    )

    with pytest.raises(RuntimeError, match="startup failed"):
        module.run_all(etl_processes=2)

    assert calls == ["runner"]


def test_worker_run_all_raises_when_threaded_runner_fails_to_start(monkeypatch):
    from src.tasks import worker as module

    calls = []

    def _raise() -> None:
        calls.append("runner")
        raise RuntimeError("startup failed")

    monkeypatch.setattr(
        module,
        "_queue_runners",
        lambda _etl_processes: {"collection_shop_dashboard": _raise},
    )
    monkeypatch.setattr(
        module, "_wait_forever", lambda *_args, **_kwargs: calls.append("wait_forever")
    )

    class _FakeThread:
        def __init__(self, target, name, daemon=False):
            self._target = target
            self.name = name

        def start(self):
            self._target()

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return False

    monkeypatch.setattr(module, "Thread", _FakeThread)

    with pytest.raises(RuntimeError, match="worker queue failed to start"):
        module.run_all(etl_processes=2)

    assert calls == ["runner"]


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


def test_worker_main_keeps_etl_queue_alive_when_multiprocess_runner_returns(
    monkeypatch,
):
    from src.tasks import worker as module

    calls = []

    monkeypatch.setattr(
        module,
        "_parse_args",
        lambda: SimpleNamespace(queue="etl_orders", etl_processes=2),
    )
    monkeypatch.setattr(
        module,
        "_queue_runners",
        lambda _etl_processes: {"etl_orders": lambda: calls.append("runner")},
    )
    monkeypatch.setattr(module, "_init_worker_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(
        module,
        "_reconcile_worker_task_statuses",
        lambda: calls.append("reconcile"),
    )
    monkeypatch.setattr(module, "_close_worker_db", lambda: calls.append("close_db"))
    monkeypatch.setattr(
        module,
        "_start_worker_loop",
        lambda: (SimpleNamespace(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        module,
        "_stop_worker_loop",
        lambda _loop, _thread: calls.append("stop_loop"),
    )
    monkeypatch.setattr(module.signal, "signal", lambda *_args: None)

    class _FakeThread:
        def __init__(self, target, name, daemon=False):
            self._target = target
            self.name = name

        def start(self):
            self._target()

        def is_alive(self):
            return False

    def _fake_wait(stop_event, thread=None):
        calls.append(("wait", thread))
        stop_event.set()

    monkeypatch.setattr(module, "Thread", _FakeThread)
    monkeypatch.setattr(module, "_wait_forever", _fake_wait)

    module.main()

    assert calls[0:3] == ["init_db", "reconcile", "runner"]
    assert ("wait", None) in calls
    assert calls[-2:] == ["close_db", "stop_loop"]


def test_worker_main_raises_when_etl_queue_startup_fails(monkeypatch):
    from src.tasks import worker as module

    calls = []

    def _raise() -> None:
        calls.append("runner")
        raise RuntimeError("startup failed")

    monkeypatch.setattr(
        module,
        "_parse_args",
        lambda: SimpleNamespace(queue="etl_orders", etl_processes=2),
    )
    monkeypatch.setattr(
        module,
        "_queue_runners",
        lambda _etl_processes: {"etl_orders": _raise},
    )
    monkeypatch.setattr(module, "_init_worker_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(
        module,
        "_reconcile_worker_task_statuses",
        lambda: calls.append("reconcile"),
    )
    monkeypatch.setattr(module, "_close_worker_db", lambda: calls.append("close_db"))
    monkeypatch.setattr(
        module,
        "_start_worker_loop",
        lambda: (SimpleNamespace(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        module,
        "_stop_worker_loop",
        lambda _loop, _thread: calls.append("stop_loop"),
    )
    monkeypatch.setattr(module.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        module, "_wait_forever", lambda *_args, **_kwargs: calls.append("wait_forever")
    )

    with pytest.raises(RuntimeError, match="startup failed"):
        module.main()

    assert calls == ["init_db", "reconcile", "runner", "close_db", "stop_loop"]
