import pytest
import fakeredis
from unittest.mock import patch
import time


class TestIdempotency:
    @pytest.fixture
    def mock_redis(self):
        return fakeredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def clean_redis(self, mock_redis):
        from src.tasks.base import BaseTask

        BaseTask._redis = None
        with patch("src.tasks.base.create_redis_connection", return_value=mock_redis):
            yield mock_redis
        BaseTask._redis = None

    def test_acquire_lock_success(self, clean_redis):
        from src.tasks.base import acquire_lock, BaseTask

        BaseTask._redis = clean_redis

        token = acquire_lock("test_key_1", ttl=60)

        assert token is not None
        assert len(token) == 32

    def test_acquire_lock_already_held(self, clean_redis):
        from src.tasks.base import acquire_lock, BaseTask

        BaseTask._redis = clean_redis

        token1 = acquire_lock("test_key_2", ttl=60)
        token2 = acquire_lock("test_key_2", ttl=60)

        assert token1 is not None
        assert token2 is None

    def test_acquire_lock_different_keys(self, clean_redis):
        from src.tasks.base import acquire_lock, BaseTask

        BaseTask._redis = clean_redis

        token1 = acquire_lock("key_a", ttl=60)
        token2 = acquire_lock("key_b", ttl=60)

        assert token1 is not None
        assert token2 is not None
        assert token1 != token2

    def test_release_lock_success(self, clean_redis):
        from src.tasks.base import acquire_lock, release_lock, BaseTask

        BaseTask._redis = clean_redis

        token = acquire_lock("test_key_release", ttl=60)
        result = release_lock("test_key_release", token)

        assert result is True

    def test_release_lock_wrong_token(self, clean_redis):
        from src.tasks.base import acquire_lock, release_lock, BaseTask

        BaseTask._redis = clean_redis

        acquire_lock("test_key_wrong", ttl=60)
        result = release_lock("test_key_wrong", "wrong_token")

        assert result is False

    def test_release_lock_nonexistent_key(self, clean_redis):
        from src.tasks.base import release_lock, BaseTask

        BaseTask._redis = clean_redis

        result = release_lock("nonexistent_key", "some_token")

        assert result is False

    def test_cache_result_success(self, clean_redis):
        from src.tasks.base import cache_result, BaseTask

        BaseTask._redis = clean_redis

        result = cache_result("test_cache", {"status": "ok", "count": 10}, ttl=60)

        assert result is True

    def test_get_cached_result_exists(self, clean_redis):
        from src.tasks.base import cache_result, get_cached_result, BaseTask

        BaseTask._redis = clean_redis

        cache_result("test_cache_get", {"status": "ok", "data": [1, 2, 3]}, ttl=60)
        cached = get_cached_result("test_cache_get")

        assert cached is not None
        assert cached["status"] == "ok"
        assert cached["data"] == [1, 2, 3]

    def test_get_cached_result_not_exists(self, clean_redis):
        from src.tasks.base import get_cached_result, BaseTask

        BaseTask._redis = clean_redis

        cached = get_cached_result("nonexistent_cache")

        assert cached is None

    def test_cache_result_deserialization(self, clean_redis):
        from src.tasks.base import cache_result, get_cached_result, BaseTask

        BaseTask._redis = clean_redis

        complex_data = {
            "nested": {"a": 1, "b": 2},
            "list": [1, 2, 3],
            "string": "test",
            "number": 42,
            "bool": True,
        }
        cache_result("complex_cache", complex_data, ttl=60)
        cached = get_cached_result("complex_cache")

        assert cached == complex_data
        assert cached["nested"]["a"] == 1
        assert cached["list"] == [1, 2, 3]

    def test_lock_ttl_expires(self, clean_redis):
        from src.tasks.base import acquire_lock, BaseTask

        BaseTask._redis = clean_redis

        token1 = acquire_lock("ttl_test_key", ttl=1)
        time.sleep(1.1)
        token2 = acquire_lock("ttl_test_key", ttl=60)

        assert token1 is not None
        assert token2 is not None
        assert token1 != token2


class TestIdempotencyIntegration:
    @pytest.fixture
    def mock_redis(self):
        return fakeredis.FakeRedis(decode_responses=True)

    def test_full_idempotency_flow(self, mock_redis):
        from src.tasks.base import (
            acquire_lock,
            release_lock,
            cache_result,
            get_cached_result,
            BaseTask,
        )

        BaseTask._redis = mock_redis

        task_key = "order_sync_2024_01_01"

        token = acquire_lock(task_key, ttl=300)
        assert token is not None

        result = cache_result(task_key, {"orders_processed": 100}, ttl=3600)
        assert result is True

        cached = get_cached_result(task_key)
        assert cached is not None
        assert cached["orders_processed"] == 100

        released = release_lock(task_key, token)
        assert released is True
