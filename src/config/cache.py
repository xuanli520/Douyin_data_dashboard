from typing import Literal
from urllib.parse import quote

from pydantic_settings import BaseSettings


class CacheSettings(BaseSettings):
    backend: Literal["redis", "local"] = "redis"
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    encoding: str = "utf-8"
    decode_responses: bool = True
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    max_connections: int = 50
    retry_on_timeout: bool = True
    experience_metrics_ttl_seconds: int = 3600
    experience_dashboard_ttl_seconds: int = 1800
    experience_issues_ttl_seconds: int = 300
    experience_cache_index_ttl_seconds: int = 7200

    @property
    def url(self) -> str:
        if self.password:
            encoded_password = quote(self.password, safe="")
            return f"redis://:{encoded_password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"
