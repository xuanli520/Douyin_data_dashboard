import pytest

from src.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_shop_dashboard_settings_defaults():
    settings = get_settings()

    assert settings.shop_dashboard.base_url == "https://fxg.jinritemai.com"
    assert settings.shop_dashboard.cookie_ttl_seconds == 21600
    assert settings.shop_dashboard.lock_ttl_seconds == 3600
    assert settings.shop_dashboard.account_rate_limit_per_minute == 15
    assert settings.shop_dashboard.llm_timeout_seconds == 120


def test_shop_dashboard_settings_env_override(monkeypatch):
    monkeypatch.setenv("SHOP_DASHBOARD__BASE_URL", "https://example.com")
    monkeypatch.setenv("SHOP_DASHBOARD__COOKIE_TTL_SECONDS", "600")
    monkeypatch.setenv("SHOP_DASHBOARD__LOCK_TTL_SECONDS", "120")
    monkeypatch.setenv("SHOP_DASHBOARD__ACCOUNT_RATE_LIMIT_PER_MINUTE", "8")
    monkeypatch.setenv("SHOP_DASHBOARD__LLM_TIMEOUT_SECONDS", "90")

    settings = get_settings()

    assert settings.shop_dashboard.base_url == "https://example.com"
    assert settings.shop_dashboard.cookie_ttl_seconds == 600
    assert settings.shop_dashboard.lock_ttl_seconds == 120
    assert settings.shop_dashboard.account_rate_limit_per_minute == 8
    assert settings.shop_dashboard.llm_timeout_seconds == 90
