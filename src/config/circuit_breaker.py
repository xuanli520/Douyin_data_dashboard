from pydantic_settings import BaseSettings


class CircuitBreakerSettings(BaseSettings):
    failure_threshold: int = 5
    recovery_timeout: int = 60
