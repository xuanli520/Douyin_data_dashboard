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
    pool_size: int = 5
    max_overflow: int = 10
    pool_recycle: int = 1800
    run_coro_timeout_seconds: int = 30

    @property
    def url(self) -> str:
        if self.driver == "sqlite":
            return f"sqlite+aiosqlite:///{self.database}"
        password = quote_plus(self.password)
        return f"postgresql+asyncpg://{self.user}:{password}@{self.host}:{self.port}/{self.database}"
