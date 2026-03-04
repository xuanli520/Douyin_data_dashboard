from types import SimpleNamespace

from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import FunctionResultStatus


def test_task_status_hook_redis_failure_degrades_gracefully(monkeypatch):
    mixin = TaskStatusMixin()

    class BrokenRedis:
        def hset(self, *_args, **_kwargs):
            raise RuntimeError("redis down")

        def expire(self, *_args, **_kwargs):
            raise RuntimeError("redis down")

    logger_calls = []
    monkeypatch.setattr(
        mixin,
        "publisher",
        SimpleNamespace(redis_db_frame=BrokenRedis()),
        raising=False,
    )
    monkeypatch.setattr(
        mixin.logger,
        "exception",
        lambda *args, **kwargs: logger_calls.append((args, kwargs)),
    )

    status = FunctionResultStatus(
        task_id="task-hook-1",
        success=True,
        time_end=123.0,
        function="sync_orders",
    )

    mixin._sync_and_aio_frame_custom_record_process_info_func(
        status, {"body": {"triggered_by": 9}}
    )
    assert logger_calls
