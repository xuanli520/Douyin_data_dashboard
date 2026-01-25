from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from src.config.monitor import MonitorSettings
from src.middleware.monitor import MonitorMiddleware, normalize_path, generate_metrics


class TestNormalizePath:
    def test_static_path(self):
        assert normalize_path("/api/users") == "/api/users"

    def test_path_with_single_param(self):
        assert normalize_path("/api/users/123") == "/api/users/{}"

    def test_path_with_multiple_params(self):
        assert normalize_path("/api/users/123/posts/456") == "/api/users/{}/posts/{}"

    def test_path_with_named_params(self):
        assert normalize_path("/api/users/{user_id}") == "/api/users/{user_id}"


class TestMonitorSettings:
    def test_default_settings(self):
        settings = MonitorSettings()
        assert settings.enabled is True
        assert settings.include_methods is True
        assert settings.include_status_codes is True
        assert len(settings.buckets) == 14
        assert 0.005 in settings.buckets
        assert 10.0 in settings.buckets

    def test_custom_buckets(self):
        settings = MonitorSettings(buckets=(0.1, 0.5, 1.0, 5.0))
        assert len(settings.buckets) == 4
        assert settings.buckets == (0.1, 0.5, 1.0, 5.0)


class TestMonitorMiddleware:
    @pytest.fixture
    def middleware(self):
        return MonitorMiddleware(app=MagicMock())

    @pytest.mark.asyncio
    async def test_request_tracked(self, middleware):
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.method = "GET"

        async def mock_call_next(req):
            return Response(status_code=200)

        with patch("src.middleware.monitor.get_settings") as mock_settings:
            mock_settings.return_value.monitor.enabled = True
            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_skip_metrics_path(self, middleware):
        request = MagicMock(spec=Request)
        request.url.path = "/metrics"
        request.method = "GET"

        call_next_called = False

        async def mock_call_next(req):
            nonlocal call_next_called
            call_next_called = True
            return Response(status_code=200)

        _ = await middleware.dispatch(request, mock_call_next)
        assert call_next_called is True

    @pytest.mark.asyncio
    async def test_skip_docs_paths(self, middleware):
        for path in ["/docs", "/redoc", "/openapi"]:
            request = MagicMock(spec=Request)
            request.url.path = path
            request.method = "GET"

            call_next_called = False

            async def mock_call_next(req):
                nonlocal call_next_called
                call_next_called = True
                return Response(status_code=200)

            _ = await middleware.dispatch(request, mock_call_next)
            assert call_next_called is True


class TestDisabledMonitor:
    @pytest.mark.asyncio
    async def test_disabled_monitor_passes_through(self):
        middleware = MonitorMiddleware(app=MagicMock())

        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.method = "GET"

        call_next_called = False

        async def mock_call_next(req):
            nonlocal call_next_called
            call_next_called = True
            return Response(status_code=200)

        with patch("src.middleware.monitor.get_settings") as mock_settings:
            mock_settings.return_value.monitor.enabled = False
            response = await middleware.dispatch(request, mock_call_next)

            assert call_next_called is True
            assert response.status_code == 200


class TestGenerateMetrics:
    def test_generate_metrics_returns_bytes(self):
        result = generate_metrics()
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_metrics_contains_prometheus_format(self):
        result = generate_metrics()
        text = result.decode("utf-8")
        assert "# HELP" in text or "# TYPE" in text
