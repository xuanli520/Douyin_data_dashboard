from starlette.middleware.cors import CORSMiddleware

from src.middleware import cors as cors_module


class TestGetCorsMiddleware:
    def test_returns_configured_middleware(self, monkeypatch):
        monkeypatch.setattr(cors_module, "CORS_ALLOWED_HOSTS", ["http://example.com"])
        monkeypatch.setattr(cors_module, "CORS_ALLOWED_METHODS", ["GET", "POST"])
        monkeypatch.setattr(
            cors_module, "CORS_ALLOWED_HEADERS", ["X-Test", "Authorization"]
        )
        monkeypatch.setattr(cors_module, "CORS_ALLOW_CREDENTIALS", True)

        middleware = cors_module.get_cors_middleware()

        assert middleware.cls is CORSMiddleware
        assert middleware.kwargs["allow_origins"] == ["http://example.com"]
        assert middleware.kwargs["allow_methods"] == ["GET", "POST"]
        assert middleware.kwargs["allow_headers"] == ["X-Test", "Authorization"]
        assert middleware.kwargs["allow_credentials"] is True
