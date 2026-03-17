from types import SimpleNamespace

import pytest


class _FakeRedis:
    def __init__(self):
        self.hset_calls = []
        self.expire_calls = []

    def hset(self, key, mapping):
        self.hset_calls.append((key, mapping))

    def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))


def test_etl_orders_task_params():
    from src.tasks.etl.orders import process_orders

    assert process_orders.boost_params.queue_name == "etl_orders"
    assert process_orders.boost_params.concurrent_mode == "SINGLE_THREAD"
    assert process_orders.boost_params.concurrent_num == 1
    assert process_orders.boost_params.is_push_to_dlx_queue_when_retry_max_times is True


def test_etl_products_task_params():
    from src.tasks.etl.products import process_products

    assert process_products.boost_params.queue_name == "etl_products"
    assert process_products.boost_params.concurrent_mode == "SINGLE_THREAD"
    assert process_products.boost_params.concurrent_num == 1
    assert (
        process_products.boost_params.is_push_to_dlx_queue_when_retry_max_times is True
    )


def test_etl_orders_writes_started_status(monkeypatch):
    from src.tasks import base as task_base
    from src.tasks.etl import orders as module

    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        module.process_orders,
        "publisher",
        SimpleNamespace(redis_db_frame=fake_redis),
        raising=False,
    )
    monkeypatch.setattr(task_base.fct, "task_id", "task-etl-1", raising=False)

    with pytest.raises(module.ScrapingFailedException):
        module.process_orders(batch_date="2026-03-03", triggered_by=9)
    key, mapping = fake_redis.hset_calls[0]
    assert key == "douyin:task:status:task-etl-1"
    assert mapping["status"] == "STARTED"
