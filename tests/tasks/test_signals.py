import pytest
from unittest.mock import MagicMock, patch


class TestTaskSignals:
    @pytest.fixture
    def base_task_instance(self):
        from src.tasks.base import BaseTask

        task = MagicMock(spec=BaseTask)
        task.name = "test.task"
        task._redis = None
        return task

    @patch("src.tasks.base.logger")
    def test_on_failure_logs_error(self, mock_logger, base_task_instance):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id"

        BaseTask.on_failure(task, Exception("Test error"), "test-task-id", (), {}, None)

        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        assert "Test error" in str(args[0])

    def test_on_failure_does_not_update_status(self, base_task_instance):
        from src.tasks.base import BaseTask

        task = base_task_instance

        with patch.object(task, "_safe_update_status") as mock_update:
            BaseTask.on_failure(
                task, Exception("Test error"), "test-task-id", (), {}, None
            )
            mock_update.assert_not_called()

    @patch("src.tasks.base.logger")
    def test_on_timeout_logs_warning_on_soft_timeout(
        self, mock_logger, base_task_instance
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id"

        BaseTask.on_timeout(task, soft=True, timeout=300)

        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        assert "soft time limit" in str(args[0])

    @patch("src.tasks.base.logger")
    def test_on_timeout_logs_error_on_hard_timeout(
        self, mock_logger, base_task_instance
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id"

        BaseTask.on_timeout(task, soft=False, timeout=3600)

        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        assert "hard time limit" in str(args[0])

    def test_on_timeout_does_not_update_status(self, base_task_instance):
        from src.tasks.base import BaseTask

        task = base_task_instance

        with patch.object(task, "_safe_update_status") as mock_update:
            BaseTask.on_timeout(task, soft=True, timeout=300)
            mock_update.assert_not_called()

    @patch("src.tasks.base.logger")
    def test_on_failure_handles_soft_time_limit_exceeded(
        self, mock_logger, base_task_instance
    ):
        from src.tasks.base import BaseTask
        from celery.exceptions import SoftTimeLimitExceeded

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id"

        BaseTask.on_failure(task, SoftTimeLimitExceeded(), "test-task-id", (), {}, None)

        mock_logger.warning.assert_called_once()
        mock_logger.error.assert_not_called()

    @patch("src.tasks.base.logger")
    def test_on_retry_logs_warning(self, mock_logger, base_task_instance):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id"

        BaseTask.on_retry(task, Exception("Retry error"), "test-task-id", (), {}, None)

        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        assert "retrying" in str(args[0])

    @patch("src.tasks.base.logger")
    def test_on_failure_timeout_error_logs_warning(
        self, mock_logger, base_task_instance
    ):
        from src.tasks.base import BaseTask

        task = base_task_instance
        task.request = MagicMock()
        task.request.id = "test-task-id"

        BaseTask.on_failure(task, TimeoutError(), "test-task-id", (), {}, None)

        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        assert "timeout" in str(args[0]).lower()


class TestWorkerProcessInit:
    @patch("src.tasks.base.create_redis_connection")
    def test_worker_process_init_resets_redis_connection(self, mock_create):
        from src.tasks.base import BaseTask
        from celery.signals import worker_process_init

        original_redis = MagicMock()
        BaseTask._redis = original_redis
        mock_create.return_value = MagicMock()

        sender = None
        worker_process_init.send(sender)

        assert BaseTask._redis is not original_redis
        BaseTask._redis = None
