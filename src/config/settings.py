from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .app import AppSettings
from .auth import AuthSettings
from .cache import CacheSettings
from .captcha import CaptchaSettings
from .database import DatabaseSettings
from .funboost import FunboostSettings
from .log import LogSettings
from .rate_limit import RateLimitSettings
from .circuit_breaker import CircuitBreakerSettings
from .monitor import MonitorSettings
from .cors import CorsSettings
from .shop_dashboard import ShopDashboardSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        # avoid snake_case conflict
        env_nested_delimiter="__",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    captcha: CaptchaSettings = Field(default_factory=CaptchaSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    circuit_breaker: CircuitBreakerSettings = Field(
        default_factory=CircuitBreakerSettings
    )
    monitor: MonitorSettings = Field(default_factory=MonitorSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    funboost: FunboostSettings = Field(default_factory=FunboostSettings)
    shop_dashboard: ShopDashboardSettings = Field(
        default_factory=ShopDashboardSettings
    )
