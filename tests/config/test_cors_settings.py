import pytest

from src.config.cors import CorsSettings


class TestCorsSettings:
    def test_defaults(self):
        settings = CorsSettings()
        assert "http://localhost:3000" in settings.allowed_hosts
        assert "http://8.137.84.161:3456" in settings.allowed_hosts
        assert "HEAD" in settings.allow_methods
        assert settings.allow_headers == [
            "Authorization",
            "Content-Type",
            "X-Request-ID",
        ]
        assert settings.allow_credentials is True

    def test_custom_hosts(self):
        hosts = ["https://app.example.com", "https://prod.example.com"]
        settings = CorsSettings(allowed_hosts=hosts)
        assert settings.allowed_hosts == hosts

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv(
            "ALLOWED_HOSTS",
            '["https://env-a.example.com", "https://env-b.example.com"]',
        )
        settings = CorsSettings()
        assert settings.allowed_hosts == [
            "https://env-a.example.com",
            "https://env-b.example.com",
        ]

    def test_empty_hosts(self):
        settings = CorsSettings(allowed_hosts=[])
        assert settings.allowed_hosts == []

    def test_mixed_scheme_hosts(self):
        settings = CorsSettings(
            allowed_hosts=["http://8.137.84.161:3456", "https://b.example.com"]
        )
        assert settings.allowed_hosts == [
            "http://8.137.84.161:3456",
            "https://b.example.com",
        ]

    def test_credentials_disallow_wildcard(self):
        with pytest.raises(ValueError):
            CorsSettings(allowed_hosts=["*"], allow_credentials=True)

    def test_disallow_non_localhost_http(self):
        with pytest.raises(ValueError):
            CorsSettings(allowed_hosts=["http://a.example.com"])
