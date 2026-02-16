from pydantic_settings import BaseSettings


class CelerySettings(BaseSettings):
    broker_url: str = ""
    result_backend: str = ""
    task_status_ttl: int = 3600
