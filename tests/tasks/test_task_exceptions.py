from src.shared.errors import ErrorCode
from src.tasks.exceptions import (
    TaskNotFoundException,
    TaskAlreadyRunningException,
    ScrapingFailedException,
    ScrapingRateLimitException,
    ETLTransformException,
)


class TestTaskExceptions:
    def test_task_not_found_exception(self):
        exc = TaskNotFoundException(task_id="task-123")

        assert exc.code == ErrorCode.TASK_NOT_FOUND
        assert "task-123" in exc.msg
        assert exc.data["task_id"] == "task-123"

    def test_task_already_running_exception(self):
        exc = TaskAlreadyRunningException(task_key="order_sync_2024")

        assert exc.code == ErrorCode.TASK_ALREADY_RUNNING
        assert "order_sync_2024" in exc.msg
        assert exc.data["task_key"] == "order_sync_2024"

    def test_scraping_failed_exception(self):
        exc = ScrapingFailedException(target="shop_abc", reason="Parse error")

        assert exc.code == ErrorCode.SCRAPING_FAILED
        assert "shop_abc" in exc.msg
        assert "Parse error" in exc.msg
        assert exc.data["target"] == "shop_abc"
        assert exc.data["reason"] == "Parse error"

    def test_scraping_rate_limit_exception(self):
        exc = ScrapingRateLimitException(target="shop_abc", retry_after=120)

        assert exc.code == ErrorCode.SCRAPING_RATE_LIMIT
        assert "shop_abc" in exc.msg
        assert "120" in exc.msg
        assert exc.data["target"] == "shop_abc"
        assert exc.data["retry_after"] == 120

    def test_scraping_rate_limit_exception_default_retry(self):
        exc = ScrapingRateLimitException(target="shop_xyz")

        assert exc.data["retry_after"] == 60

    def test_etl_transform_exception(self):
        exc = ETLTransformException(stage="validation", details="Missing field: price")

        assert exc.code == ErrorCode.ETL_TRANSFORM_FAILED
        assert "validation" in exc.msg
        assert exc.data["stage"] == "validation"
        assert exc.data["details"] == "Missing field: price"

    def test_exception_string_representation(self):
        exc = ScrapingFailedException(target="test", reason="error")
        exc_str = str(exc)

        assert "[81001]" in exc_str
        assert "test" in exc_str
        assert "error" in exc_str

    def test_on_failure_does_not_re_raise_business_exception(self):
        from src.tasks.base import BaseTask
        from unittest.mock import MagicMock, patch

        task = MagicMock(spec=BaseTask)
        task.request = MagicMock()
        task.request.id = "test-task"
        task._safe_update_status = MagicMock()

        with patch("src.tasks.base.logger") as mock_logger:
            BaseTask.on_failure(
                task,
                ScrapingFailedException(target="test", reason="error"),
                "test-task",
                (),
                {},
                None,
            )

            mock_logger.error.assert_called_once()
            task._safe_update_status.assert_not_called()


class TestErrorCodeMapping:
    def test_task_error_codes_exist(self):
        assert ErrorCode.TASK_NOT_FOUND == 80001
        assert ErrorCode.TASK_ALREADY_RUNNING == 80002
        assert ErrorCode.TASK_TIMEOUT == 80003
        assert ErrorCode.TASK_RETRY_EXHAUSTED == 80004
        assert ErrorCode.TASK_IDEMPOTENCY_CONFLICT == 80005

    def test_scraping_error_codes_exist(self):
        assert ErrorCode.SCRAPING_FAILED == 81001
        assert ErrorCode.SCRAPING_RATE_LIMIT == 81002
        assert ErrorCode.SCRAPING_AUTH_FAILED == 81003
        assert ErrorCode.SCRAPING_HTML_PARSE_ERROR == 81004

    def test_etl_error_codes_exist(self):
        assert ErrorCode.ETL_TRANSFORM_FAILED == 82001
        assert ErrorCode.ETL_VALIDATION_FAILED == 82002
        assert ErrorCode.ETL_DATA_QUALITY_ERROR == 82003
