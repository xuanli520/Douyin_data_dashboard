from pydantic import Field
from typing import Literal
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    driver: Literal["postgresql", "sqlite"] = "postgresql"
    host: str = "localhost"
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = ""
    echo: bool = False
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_recycle: int = Field(default=1800, ge=0)
    run_coro_timeout_seconds: int = 30

    @property
    def url(self) -> str:
        if self.driver == "sqlite":
            return f"sqlite+aiosqlite:///{self.database}"
        user = quote_plus(self.user)
        password = quote_plus(self.password)
        return f"postgresql+asyncpg://{user}:{password}@{self.host}:{self.port}/{self.database}"
