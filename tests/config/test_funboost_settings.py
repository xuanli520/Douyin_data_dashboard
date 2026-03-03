import pytest

from src.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_funboost_settings_defaults():
    settings = get_settings()

    assert settings.funboost.broker_kind == "REDIS_ACK_ABLE"
    assert settings.funboost.status_ttl_seconds == 3600
    assert settings.funboost.default_function_timeout == 3600
    assert settings.funboost.default_max_retry_times == 3
    assert settings.funboost.default_retry_interval == 60
    assert settings.funboost.pull_msg_batch_size == 1


def test_funboost_settings_env_override(monkeypatch):
    monkeypatch.setenv("FUNBOOST__BROKER_KIND", "REDIS_STREAM")
    monkeypatch.setenv("FUNBOOST__STATUS_TTL_SECONDS", "7200")
    monkeypatch.setenv("FUNBOOST__DEFAULT_FUNCTION_TIMEOUT", "1800")
    monkeypatch.setenv("FUNBOOST__DEFAULT_MAX_RETRY_TIMES", "5")
    monkeypatch.setenv("FUNBOOST__DEFAULT_RETRY_INTERVAL", "30")
    monkeypatch.setenv("FUNBOOST__PULL_MSG_BATCH_SIZE", "2")

    settings = get_settings()

    assert settings.funboost.broker_kind == "REDIS_STREAM"
    assert settings.funboost.status_ttl_seconds == 7200
    assert settings.funboost.default_function_timeout == 1800
    assert settings.funboost.default_max_retry_times == 5
    assert settings.funboost.default_retry_interval == 30
    assert settings.funboost.pull_msg_batch_size == 2
