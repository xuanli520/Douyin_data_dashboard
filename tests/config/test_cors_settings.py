import pytest

from src.config.cors import CorsSettings


class TestCorsSettings:
    def test_defaults(self):
        settings = CorsSettings()
        assert "http://localhost:3000" in settings.allowed_hosts
        assert "HEAD" in settings.allow_methods
        assert settings.allow_headers == ["*"]
        assert settings.allow_credentials is True

    def test_custom_hosts(self):
        hosts = ["http://app.example.com", "https://prod.example.com"]
        settings = CorsSettings(allowed_hosts=hosts)
        assert settings.allowed_hosts == hosts

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv(
            "ALLOWED_HOSTS", '["http://env.example.com", "https://env.example.com"]'
        )
        settings = CorsSettings()
        assert settings.allowed_hosts == [
            "http://env.example.com",
            "https://env.example.com",
        ]

    def test_empty_hosts(self):
        settings = CorsSettings(allowed_hosts=[])
        assert settings.allowed_hosts == []

    def test_mixed_scheme_hosts(self):
        settings = CorsSettings(
            allowed_hosts=["http://a.example.com", "https://b.example.com"]
        )
        assert settings.allowed_hosts == [
            "http://a.example.com",
            "https://b.example.com",
        ]

    def test_credentials_disallow_wildcard(self):
        with pytest.raises(ValueError):
            CorsSettings(allowed_hosts=["*"], allow_credentials=True)
