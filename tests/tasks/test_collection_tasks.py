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


def test_sync_orders_queue_and_retry_params():
    from src.tasks.collection.douyin_orders import sync_orders

    assert sync_orders.boost_params.queue_name == "collection_orders"
    assert sync_orders.boost_params.is_push_to_dlx_queue_when_retry_max_times is True


def test_sync_products_queue_and_retry_params():
    from src.tasks.collection.douyin_products import sync_products

    assert sync_products.boost_params.queue_name == "collection_products"
    assert sync_products.boost_params.is_push_to_dlx_queue_when_retry_max_times is True


def test_sync_shop_dashboard_queue_and_retry_params():
    from src.tasks.collection.douyin_shop_dashboard import sync_shop_dashboard

    assert sync_shop_dashboard.boost_params.queue_name == "collection_shop_dashboard"
    assert (
        sync_shop_dashboard.boost_params.is_push_to_dlx_queue_when_retry_max_times
        is True
    )


def test_sync_orders_writes_started_status(monkeypatch):
    from src.tasks.collection import douyin_orders as module

    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        module.sync_orders,
        "publisher",
        SimpleNamespace(redis_db_frame=fake_redis),
        raising=False,
    )
    monkeypatch.setattr(module.fct, "task_id", "task-1", raising=False)

    class _FakeIdempotencyHelper:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_cached_result(self, _key):
            return None

        def acquire_lock(self, _key, ttl):
            assert ttl > 0
            return "token-1"

        def refresh_lock(self, _key, _token, _ttl):
            return True

        def cache_result(self, _key, _result, ttl=86400):
            assert ttl > 0

        def release_lock(self, _key, _token):
            return None

    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    result = module.sync_orders("shop-1", "2026-03-03", triggered_by=7)

    assert result["status"] == "success"
    assert fake_redis.hset_calls
    key, mapping = fake_redis.hset_calls[0]
    assert key == "douyin:task:status:task-1"
    assert mapping["status"] == "STARTED"
    assert str(mapping["triggered_by"]) == "7"


def test_retry_backoff_decorator_rethrows_rate_limit():
    from src.tasks.collection.douyin_orders import retry_with_backoff
    from src.tasks.exceptions import ScrapingRateLimitException

    calls = {"count": 0}

    @retry_with_backoff
    def _target():
        calls["count"] += 1
        raise ScrapingRateLimitException(error_data={"retry_after": 0})

    with pytest.raises(ScrapingRateLimitException):
        _target()
    assert calls["count"] == 1


def test_retry_backoff_decorator_handles_invalid_retry_after(monkeypatch):
    from src.tasks.collection import douyin_orders as module
    from src.tasks.exceptions import ScrapingRateLimitException

    sleep_calls = []
    monkeypatch.setattr(
        module.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    @module.retry_with_backoff
    def _target():
        raise ScrapingRateLimitException(error_data={"retry_after": "abc"})

    with pytest.raises(ScrapingRateLimitException):
        _target()

    assert sleep_calls == [1]


def test_sync_orders_started_status_write_failure_does_not_break_task(monkeypatch):
    from src.tasks.collection import douyin_orders as module

    class _BrokenRedis:
        def hset(self, _key, *args, **kwargs):
            _ = args
            _ = kwargs
            raise RuntimeError("redis unavailable")

        def expire(self, _key, _seconds):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        module.sync_orders,
        "publisher",
        SimpleNamespace(redis_db_frame=_BrokenRedis()),
        raising=False,
    )
    monkeypatch.setattr(module.fct, "task_id", "task-2", raising=False)

    class _FakeIdempotencyHelper:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_cached_result(self, _key):
            return None

        def acquire_lock(self, _key, ttl):
            assert ttl > 0
            return "token-1"

        def refresh_lock(self, _key, _token, _ttl):
            return True

        def cache_result(self, _key, _result, _ttl=86400):
            return None

        def release_lock(self, _key, _token):
            return None

    monkeypatch.setattr(module, "FunboostIdempotencyHelper", _FakeIdempotencyHelper)
    result = module.sync_orders("shop-1", "2026-03-03", triggered_by=7)

    assert result["status"] == "success"
