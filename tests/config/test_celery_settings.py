import pytest
from unittest.mock import Mock, patch
from src.config.celery import CelerySettings
from src.exceptions import ConfigInvalidException
from src.tasks.base import BaseTask
from src.shared.errors import ErrorCode


class TestCelerySettingsValidation:
    def test_task_status_ttl_default(self):
        settings = CelerySettings()
        assert settings.task_status_ttl == 3600

    def test_task_status_ttl_valid_positive(self):
        settings = CelerySettings(task_status_ttl=1800)
        assert settings.task_status_ttl == 1800

    def test_task_status_ttl_accepts_max_valid(self):
        settings = CelerySettings(task_status_ttl=31536000)
        assert settings.task_status_ttl == 31536000

    def test_task_status_ttl_rejects_zero_via_business_exception(self):
        mock_settings = Mock()
        mock_settings.celery.task_status_ttl = 0

        with patch("src.config.get_settings", return_value=mock_settings):
            task = BaseTask()
            with pytest.raises(ConfigInvalidException) as exc_info:
                task._safe_update_status("task-123", "STARTED", {})

        assert exc_info.value.data["field"] == "celery.task_status_ttl"
        assert "task_status_ttl must be greater than 0" in exc_info.value.data["reason"]
        assert exc_info.value.code == ErrorCode.CONFIG_INVALID

    def test_task_status_ttl_rejects_negative_via_business_exception(self):
        mock_settings = Mock()
        mock_settings.celery.task_status_ttl = -1

        with patch("src.config.get_settings", return_value=mock_settings):
            task = BaseTask()
            with pytest.raises(ConfigInvalidException) as exc_info:
                task._safe_update_status("task-123", "STARTED", {})

        assert exc_info.value.data["field"] == "celery.task_status_ttl"
        assert "task_status_ttl must be greater than 0" in exc_info.value.data["reason"]
        assert exc_info.value.code == ErrorCode.CONFIG_INVALID

    def test_task_status_ttl_rejects_excessive_value_via_business_exception(self):
        mock_settings = Mock()
        mock_settings.celery.task_status_ttl = 40000000

        with patch("src.config.get_settings", return_value=mock_settings):
            task = BaseTask()
            with pytest.raises(ConfigInvalidException) as exc_info:
                task._safe_update_status("task-123", "STARTED", {})

        assert exc_info.value.data["field"] == "celery.task_status_ttl"
        assert "task_status_ttl cannot exceed 1 year" in exc_info.value.data["reason"]
        assert exc_info.value.code == ErrorCode.CONFIG_INVALID

    def test_broker_url_default(self):
        settings = CelerySettings()
        assert settings.broker_url == ""

    def test_result_backend_default(self):
        settings = CelerySettings()
        assert settings.result_backend == ""

    def test_custom_broker_url(self):
        settings = CelerySettings(broker_url="redis://localhost:6379/0")
        assert settings.broker_url == "redis://localhost:6379/0"

    def test_custom_result_backend(self):
        settings = CelerySettings(result_backend="redis://localhost:6379/1")
        assert settings.result_backend == "redis://localhost:6379/1"
