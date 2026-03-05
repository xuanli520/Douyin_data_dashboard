from pydantic_settings import BaseSettings


class ShopDashboardSettings(BaseSettings):
    base_url: str = "https://fxg.jinritemai.com"
    cookie_ttl_seconds: int = 21600
    lock_ttl_seconds: int = 3600
    account_rate_limit_per_minute: int = 15
    llm_timeout_seconds: int = 120
    browser_headless: bool = True
    browser_timeout_seconds: int = 45
    browser_refresh_url: str = "https://fxg.jinritemai.com"
    browser_lock_wait_seconds: int = 10
    browser_lock_retry_interval_seconds: float = 0.2
    browser_user_agent: str | None = None
