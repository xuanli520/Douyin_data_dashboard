import pytest


def test_collection_orders_retry_and_dlx_params():
    from src.tasks.collection.douyin_orders import (
        handle_collection_orders_dead_letter,
        sync_orders,
    )

    assert sync_orders.boost_params.max_retry_times == 3
    assert sync_orders.boost_params.retry_interval == 60
    assert sync_orders.boost_params.is_push_to_dlx_queue_when_retry_max_times is True
    assert handle_collection_orders_dead_letter.boost_params.queue_name.endswith("_dlx")


def test_retry_with_backoff_uses_retry_after(monkeypatch):
    from src.tasks.collection import douyin_orders as module
    from src.tasks.exceptions import ScrapingRateLimitException

    sleep_calls = []
    monkeypatch.setattr(
        module.time,
        "sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    @module.retry_with_backoff
    def _target():
        raise ScrapingRateLimitException(error_data={"retry_after": "2"})

    with pytest.raises(ScrapingRateLimitException):
        _target()

    assert sleep_calls == [2]
