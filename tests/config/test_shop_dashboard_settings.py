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
    assert settings.shop_dashboard.catalog_cache_ttl_seconds == 3600
    assert settings.shop_dashboard.catalog_cache_ttl_cap_seconds == 7200
    assert settings.shop_dashboard.catalog_refresh_lock_ttl_seconds == 30
    assert settings.shop_dashboard.account_rate_limit_per_minute == 15
    assert settings.shop_dashboard.bootstrap_concurrency_limit == 2
    assert settings.shop_dashboard.bootstrap_failure_rate_degrade_threshold == 0.4
    assert settings.shop_dashboard.bootstrap_force_serial is False
    assert settings.shop_dashboard.bootstrap_verify_timeout_seconds == 8.0
    assert settings.shop_dashboard.bootstrap_verify_retry_limit == 1
    assert settings.shop_dashboard.bootstrap_verify_strict is True
    assert settings.shop_dashboard.bootstrap_bundle_session_version == "2"
    assert settings.shop_dashboard.shop_mismatch_failure_threshold == 3
    assert settings.shop_dashboard.shop_mismatch_failure_threshold_degraded == 0
    assert (
        settings.shop_dashboard.shop_mismatch_failure_threshold_degraded_accounts == ""
    )
    assert settings.shop_dashboard.shop_mismatch_failure_window_seconds == 21600
    assert settings.shop_dashboard.shop_mismatch_circuit_open_seconds == 21600
    assert settings.shop_dashboard.account_switch_mismatch_threshold == 3
    assert settings.shop_dashboard.account_switch_min_distinct_targets == 2
    assert settings.shop_dashboard.account_switch_observation_ttl_seconds == 900
    assert settings.shop_dashboard.unsupported_http_shop_switch_ttl_seconds == 900
    assert settings.shop_dashboard.llm_timeout_seconds == 120


def test_shop_dashboard_settings_env_override(monkeypatch):
    monkeypatch.setenv("SHOP_DASHBOARD__BASE_URL", "https://example.com")
    monkeypatch.setenv("SHOP_DASHBOARD__COOKIE_TTL_SECONDS", "600")
    monkeypatch.setenv("SHOP_DASHBOARD__LOCK_TTL_SECONDS", "120")
    monkeypatch.setenv("SHOP_DASHBOARD__CATALOG_CACHE_TTL_SECONDS", "4000")
    monkeypatch.setenv("SHOP_DASHBOARD__CATALOG_CACHE_TTL_CAP_SECONDS", "4100")
    monkeypatch.setenv("SHOP_DASHBOARD__CATALOG_REFRESH_LOCK_TTL_SECONDS", "35")
    monkeypatch.setenv("SHOP_DASHBOARD__ACCOUNT_RATE_LIMIT_PER_MINUTE", "8")
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_CONCURRENCY_LIMIT", "4")
    monkeypatch.setenv(
        "SHOP_DASHBOARD__BOOTSTRAP_FAILURE_RATE_DEGRADE_THRESHOLD",
        "0.3",
    )
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_FORCE_SERIAL", "true")
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_TIMEOUT_SECONDS", "5.5")
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_RETRY_LIMIT", "3")
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_VERIFY_STRICT", "false")
    monkeypatch.setenv("SHOP_DASHBOARD__BOOTSTRAP_BUNDLE_SESSION_VERSION", "9")
    monkeypatch.setenv("SHOP_DASHBOARD__SHOP_MISMATCH_FAILURE_THRESHOLD", "5")
    monkeypatch.setenv("SHOP_DASHBOARD__SHOP_MISMATCH_FAILURE_THRESHOLD_DEGRADED", "2")
    monkeypatch.setenv(
        "SHOP_DASHBOARD__SHOP_MISMATCH_FAILURE_THRESHOLD_DEGRADED_ACCOUNTS",
        "acct-1|acct-2",
    )
    monkeypatch.setenv("SHOP_DASHBOARD__SHOP_MISMATCH_FAILURE_WINDOW_SECONDS", "100")
    monkeypatch.setenv("SHOP_DASHBOARD__SHOP_MISMATCH_CIRCUIT_OPEN_SECONDS", "120")
    monkeypatch.setenv("SHOP_DASHBOARD__ACCOUNT_SWITCH_MISMATCH_THRESHOLD", "4")
    monkeypatch.setenv("SHOP_DASHBOARD__ACCOUNT_SWITCH_MIN_DISTINCT_TARGETS", "3")
    monkeypatch.setenv("SHOP_DASHBOARD__ACCOUNT_SWITCH_OBSERVATION_TTL_SECONDS", "180")
    monkeypatch.setenv(
        "SHOP_DASHBOARD__UNSUPPORTED_HTTP_SHOP_SWITCH_TTL_SECONDS", "600"
    )
    monkeypatch.setenv("SHOP_DASHBOARD__LLM_TIMEOUT_SECONDS", "90")

    settings = get_settings()

    assert settings.shop_dashboard.base_url == "https://example.com"
    assert settings.shop_dashboard.cookie_ttl_seconds == 600
    assert settings.shop_dashboard.lock_ttl_seconds == 120
    assert settings.shop_dashboard.catalog_cache_ttl_seconds == 4000
    assert settings.shop_dashboard.catalog_cache_ttl_cap_seconds == 4100
    assert settings.shop_dashboard.catalog_refresh_lock_ttl_seconds == 35
    assert settings.shop_dashboard.account_rate_limit_per_minute == 8
    assert settings.shop_dashboard.bootstrap_concurrency_limit == 4
    assert settings.shop_dashboard.bootstrap_failure_rate_degrade_threshold == 0.3
    assert settings.shop_dashboard.bootstrap_force_serial is True
    assert settings.shop_dashboard.bootstrap_verify_timeout_seconds == 5.5
    assert settings.shop_dashboard.bootstrap_verify_retry_limit == 3
    assert settings.shop_dashboard.bootstrap_verify_strict is False
    assert settings.shop_dashboard.bootstrap_bundle_session_version == "9"
    assert settings.shop_dashboard.shop_mismatch_failure_threshold == 5
    assert settings.shop_dashboard.shop_mismatch_failure_threshold_degraded == 2
    assert (
        settings.shop_dashboard.shop_mismatch_failure_threshold_degraded_accounts
        == "acct-1|acct-2"
    )
    assert settings.shop_dashboard.shop_mismatch_failure_window_seconds == 100
    assert settings.shop_dashboard.shop_mismatch_circuit_open_seconds == 120
    assert settings.shop_dashboard.account_switch_mismatch_threshold == 4
    assert settings.shop_dashboard.account_switch_min_distinct_targets == 3
    assert settings.shop_dashboard.account_switch_observation_ttl_seconds == 180
    assert settings.shop_dashboard.unsupported_http_shop_switch_ttl_seconds == 600
    assert settings.shop_dashboard.llm_timeout_seconds == 90


def test_shop_dashboard_settings_llm_controls(monkeypatch):
    monkeypatch.setenv("SHOP_DASHBOARD__LLM_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("SHOP_DASHBOARD__LLM_RETRY_TIMES", "3")
    monkeypatch.setenv("SHOP_DASHBOARD__LLM_PROVIDER", "openai")
    monkeypatch.setenv("SHOP_DASHBOARD__LLM_ENDPOINT", "https://example.test/v1/chat")
    monkeypatch.setenv("SHOP_DASHBOARD__LLM_MODEL", "gpt-4o-mini")

    settings = get_settings()

    assert settings.shop_dashboard.llm_timeout_seconds == 90
    assert settings.shop_dashboard.llm_retry_times == 3
    assert settings.shop_dashboard.llm_provider == "openai"
    assert settings.shop_dashboard.llm_endpoint == "https://example.test/v1/chat"
    assert settings.shop_dashboard.llm_model == "gpt-4o-mini"


def test_browser_anti_risk_settings_exposed(monkeypatch):
    monkeypatch.setenv("SHOP_DASHBOARD__BROWSER_LOCALE", "zh-CN")
    settings = get_settings()
    assert settings.shop_dashboard.browser_locale == "zh-CN"
