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
