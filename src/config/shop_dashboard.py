from pydantic_settings import BaseSettings


class ShopDashboardSettings(BaseSettings):
    base_url: str = "https://fxg.jinritemai.com"
    runtime_state_dir: str = ".runtime/shop_dashboard_state"
    cookie_ttl_seconds: int = 21600
    lock_ttl_seconds: int = 3600
    shop_lock_ttl_seconds: int = 600
    catalog_cache_ttl_seconds: int = 3600
    catalog_cache_ttl_cap_seconds: int = 7200
    catalog_stale_allow_seconds: int = 7200
    catalog_refresh_lock_ttl_seconds: int = 30
    account_rate_limit_per_minute: int = 15
    llm_timeout_seconds: int = 120
    llm_retry_times: int = 3
    llm_provider: str = "claude"
    llm_endpoint: str | None = None
    llm_model: str | None = None
    browser_headless: bool = True
    browser_timeout_seconds: int = 45
    browser_refresh_url: str = "https://fxg.jinritemai.com"
    browser_lock_wait_seconds: int = 10
    browser_lock_retry_interval_seconds: float = 0.2
    browser_user_agent: str | None = None
    browser_locale: str | None = None
    browser_timezone: str | None = None
    browser_viewport: dict[str, int] | None = None
    bootstrap_concurrency_limit: int = 2
    bootstrap_failure_rate_degrade_threshold: float = 0.4
    bootstrap_force_serial: bool = False
    bootstrap_verify_timeout_seconds: float = 8.0
    bootstrap_verify_retry_limit: int = 1
    bootstrap_verify_strict: bool = True
    bootstrap_bundle_session_version: str = "2"
    shop_mismatch_failure_threshold: int = 3
    shop_mismatch_failure_threshold_degraded: int = 0
    shop_mismatch_failure_threshold_degraded_accounts: str = ""
    shop_mismatch_failure_window_seconds: int = 21600
    shop_mismatch_circuit_open_seconds: int = 21600
    account_switch_mismatch_threshold: int = 3
    account_switch_min_distinct_targets: int = 2
    account_switch_observation_ttl_seconds: int = 900
    unsupported_http_shop_switch_ttl_seconds: int = 900
