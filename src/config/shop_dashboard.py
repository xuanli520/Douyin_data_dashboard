from typing import Any

from pydantic_settings import BaseSettings


def resolve_llm_endpoint(settings: Any) -> str:
    endpoint = str(getattr(settings, "llm_endpoint", "") or "").strip()
    if endpoint:
        return endpoint
    base_url = str(getattr(settings, "llm_base_url", "") or "").strip().rstrip("/")
    if not base_url:
        return ""
    provider = str(getattr(settings, "llm_provider", "claude") or "").strip().lower()
    if provider == "openai":
        return f"{base_url}/chat/completions"
    return base_url


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
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    agent_artifact_dir: str = ".runtime/agent_artifacts"
    agent_artifact_ttl_seconds: int = 86400
    agent_max_steps: int = 30
    agent_allowed_origins: list[str] = ["https://fxg.jinritemai.com"]
    agent_browser_driver: str = "playwright_cli"
    agent_browser_headed: bool = False
    agent_login_browser_headed: bool = False
    agent_login_code_timeout_seconds: int = 300
    agent_login_session_ttl_seconds: int = 900
    agent_login_max_steps: int = 20
    agent_login_debug_events: bool = False
    browser_headless: bool = True
    browser_timeout_seconds: int = 45
    browser_refresh_url: str = "https://fxg.jinritemai.com"
    browser_lock_wait_seconds: int = 10
    browser_lock_retry_interval_seconds: float = 0.2
    browser_user_agent: str | None = None
    browser_locale: str | None = None
    browser_timezone: str | None = None
    browser_viewport: dict[str, int] | None = None
    agent_batch_concurrency_limit: int = 1
    shop_mismatch_failure_threshold: int = 3
    shop_mismatch_failure_threshold_degraded: int = 0
    shop_mismatch_failure_threshold_degraded_accounts: str = ""
    shop_mismatch_failure_window_seconds: int = 21600
    shop_mismatch_circuit_open_seconds: int = 21600

    def resolved_llm_endpoint(self) -> str:
        return resolve_llm_endpoint(self)
