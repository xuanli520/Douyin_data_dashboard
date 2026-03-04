from pydantic_settings import BaseSettings


class ShopDashboardSettings(BaseSettings):
    base_url: str = "https://fxg.jinritemai.com"
    cookie_ttl_seconds: int = 21600
    lock_ttl_seconds: int = 3600
    account_rate_limit_per_minute: int = 15
    llm_timeout_seconds: int = 120
