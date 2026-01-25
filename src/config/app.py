from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    name: str = Field(default="fastapi-boilerplate")

    version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    timezone: int = Field(default=8, description="UTC offset in hours")

    @model_validator(mode="after")
    def validate_name(self):
        if not self.name:
            self.name = "fastapi-boilerplate"
        return self
