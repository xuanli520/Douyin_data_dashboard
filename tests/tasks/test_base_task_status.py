import pytest
from unittest.mock import MagicMock, patch
import fakeredis


class TestBaseTaskStatus:
    @pytest.fixture
    def mock_redis(self):
        return fakeredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def base_task_instance(self, mock_redis):
        from src.tasks.base import BaseTask

        task = MagicMock(spec=BaseTask)
        task.name = "test.task"
        task._redis = mock_redis
        task.sync_redis = mock_redis
        task.get_state_key = BaseTask.get_state_key.__get__(task, BaseTask)
        task._safe_update_status = lambda *a, **kw: BaseTask._safe_update_status(
            task, *a, **kw
        )
        task._normalize_redis_hash = BaseTask._normalize_redis_hash.__get__(
            task, BaseTask
        )
        return task

    @patch("src.tasks.base.logger")
    def test_before_start_writes_started_status(
        self, mock_logger, base_task_instance, mock_redis
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id-123"
        task.request.delivery_info = {"routing_key": "default"}

        BaseTask.before_start(task, "test-task-id-123", (1, 2), {"triggered_by": 1})

        key = task.get_state_key("test-task-id-123")
        data = mock_redis.hgetall(key)

        assert data["status"] == "STARTED"
        assert "started_at" in data
        assert data["task_name"] == "test.task"
        assert data["triggered_by"] == "1"

    @patch("src.tasks.base.logger")
    def test_before_start_truncates_args_kwargs(
        self, mock_logger, base_task_instance, mock_redis
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id-456"
        task.request.delivery_info = {}

        long_args = tuple(range(100))
        long_kwargs = {f"key_{i}": f"value_{i}" for i in range(100)}

        BaseTask.before_start(task, "test-task-id-456", long_args, long_kwargs)

        key = task.get_state_key("test-task-id-456")
        data = mock_redis.hgetall(key)

        assert len(data["args"]) <= 200
        assert len(data["kwargs"]) <= 200

    @patch("src.tasks.base.logger")
    def test_after_return_success_writes_status(
        self, mock_logger, base_task_instance, mock_redis
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id-789"

        BaseTask.after_return(
            task, "SUCCESS", {"result": "ok"}, "test-task-id-789", (), {}, None
        )

        key = task.get_state_key("test-task-id-789")
        data = mock_redis.hgetall(key)

        assert data["status"] == "SUCCESS"
        assert "completed_at" in data

    @patch("src.tasks.base.logger")
    def test_after_return_success_truncates_result(
        self, mock_logger, base_task_instance, mock_redis
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id-999"

        long_result = {"data": "x" * 3000}
        BaseTask.after_return(
            task, "SUCCESS", long_result, "test-task-id-999", (), {}, None
        )

        key = task.get_state_key("test-task-id-999")
        data = mock_redis.hgetall(key)

        assert data["result"] is not None
        assert len(data["result"]) <= 2000

    @patch("src.tasks.base.logger")
    def test_after_return_failure_writes_status(
        self, mock_logger, base_task_instance, mock_redis
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id-fail"

        BaseTask.after_return(
            task, "FAILURE", None, "test-task-id-fail", (), {}, "Error: test error"
        )

        key = task.get_state_key("test-task-id-fail")
        data = mock_redis.hgetall(key)

        assert data["status"] == "FAILURE"
        assert "Error: test error" in data["error"]

    @patch("src.tasks.base.logger")
    def test_after_return_retry_writes_status(
        self, mock_logger, base_task_instance, mock_redis
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id-retry"

        BaseTask.after_return(
            task, "RETRY", None, "test-task-id-retry", (), {}, "Retry error"
        )

        key = task.get_state_key("test-task-id-retry")
        data = mock_redis.hgetall(key)

        assert data["status"] == "RETRY"

    @patch("src.tasks.base.logger")
    def test_status_ttl_is_60_seconds(
        self, mock_logger, base_task_instance, mock_redis
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id-ttl"

        BaseTask.before_start(task, "test-task-id-ttl", (), {})

        key = task.get_state_key("test-task-id-ttl")
        ttl = mock_redis.ttl(key)

        assert ttl <= 60
        assert ttl > 0

    @patch("src.tasks.base.logger")
    def test_redis_exception_does_not_raise(self, mock_logger, base_task_instance):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.sync_redis = MagicMock()
        task.sync_redis.pipeline.side_effect = Exception("Redis connection failed")

        task.request = MagicMock()
        task.request.id = "test-task-id-exc"
        task.request.delivery_info = {}

        BaseTask.before_start(task, "test-task-id-exc", (), {})

    def test_normalize_redis_hash_handles_none_values(self):
        from src.tasks.base import BaseTask

        task = MagicMock(spec=BaseTask)
        task._normalize_redis_hash = BaseTask._normalize_redis_hash.__get__(
            task, BaseTask
        )

        result = task._normalize_redis_hash({"a": None, "b": 1})
        assert "a" not in result
        assert result["b"] == "1"

    def test_normalize_redis_hash_truncates_long_strings(self):
        from src.tasks.base import BaseTask

        task = MagicMock(spec=BaseTask)
        task._normalize_redis_hash = BaseTask._normalize_redis_hash.__get__(
            task, BaseTask
        )

        long_string = "x" * 3000
        result = task._normalize_redis_hash({"a": long_string})

        assert len(result["a"]) <= 2000

    def test_normalize_redis_hash_handles_bool(self):
        from src.tasks.base import BaseTask

        task = MagicMock(spec=BaseTask)
        task._normalize_redis_hash = BaseTask._normalize_redis_hash.__get__(
            task, BaseTask
        )

        result = task._normalize_redis_hash({"a": True, "b": False})

        assert result["a"] == "true"
        assert result["b"] == "false"
