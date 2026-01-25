from pydantic import BaseModel
from pydantic_settings import BaseSettings


class RateLimitEndpoint(BaseModel):
    limit: int = 100
    window: int = 60


class RateLimitSettings(BaseSettings):
    enabled: bool = True
    global_limit: int = 1000
    global_window: int = 60
    endpoints: dict[str, RateLimitEndpoint] = {}
