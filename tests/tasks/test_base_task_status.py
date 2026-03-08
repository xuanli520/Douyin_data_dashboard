from types import SimpleNamespace

from src.config import get_settings
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import FunctionResultStatus


class FakeRedis:
    def __init__(self):
        self.hset_calls = []
        self.expire_calls = []

    def hset(self, key, mapping):
        self.hset_calls.append((key, mapping))

    def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))


def test_task_status_hook_writes_fields_and_ttl():
    mixin = TaskStatusMixin()
    fake_redis = FakeRedis()
    mixin.publisher = SimpleNamespace(redis_db_frame=fake_redis)

    status = FunctionResultStatus(
        task_id="task-status-1",
        success=True,
        time_end=1730000000.0,
        function="sync_shop_dashboard",
    )

    mixin._sync_and_aio_frame_custom_record_process_info_func(
        status, {"body": {"triggered_by": 42}}
    )

    assert fake_redis.hset_calls
    key = fake_redis.hset_calls[0][0]
    assert key == "douyin:task:status:task-status-1"
    merged_mapping = {}
    for _, mapping in fake_redis.hset_calls:
        merged_mapping.update(mapping)
    assert merged_mapping["status"] == "SUCCESS"
    assert merged_mapping["task_name"] == "sync_shop_dashboard"
    assert str(merged_mapping["triggered_by"]) == "42"
    assert "completed_at" in merged_mapping

    assert fake_redis.expire_calls
    expire_key, expire_ttl = fake_redis.expire_calls[0]
    assert expire_key == key
    assert expire_ttl == get_settings().funboost.status_ttl_seconds
