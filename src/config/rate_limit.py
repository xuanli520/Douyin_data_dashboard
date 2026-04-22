from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class RateLimitEndpoint(BaseModel):
    limit: int = 100
    window: float = 60


DEFAULT_RATE_LIMIT_ENDPOINTS = {
    "/api/v1/auth/login": RateLimitEndpoint(limit=5, window=60),
}


class RateLimitSettings(BaseSettings):
    enabled: bool = True
    global_limit: int = 1000
    global_window: float = 60
    endpoints: dict[str, RateLimitEndpoint] = Field(default_factory=dict)

    def get_endpoint(self, path: str) -> RateLimitEndpoint | None:
        return self.endpoints.get(path) or DEFAULT_RATE_LIMIT_ENDPOINTS.get(path)
