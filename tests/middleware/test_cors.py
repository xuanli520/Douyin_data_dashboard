from starlette.middleware.cors import CORSMiddleware

from src.middleware import cors as cors_module


class TestGetCorsMiddleware:
    def test_returns_configured_middleware(self, monkeypatch):
        class DummyCors:
            allowed_hosts = ["http://example.com"]
            allow_methods = ["GET", "POST"]
            allow_headers = ["X-Test", "Authorization"]
            allow_credentials = True

        class DummySettings:
            cors = DummyCors()

        monkeypatch.setattr(cors_module, "get_settings", lambda: DummySettings())

        middleware = cors_module.get_cors_middleware()

        assert middleware.cls is CORSMiddleware
        assert middleware.kwargs["allow_origins"] == ["http://example.com"]
        assert middleware.kwargs["allow_methods"] == ["GET", "POST"]
        assert middleware.kwargs["allow_headers"] == ["X-Test", "Authorization"]
        assert middleware.kwargs["allow_credentials"] is True
