from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class CorsSettings(BaseSettings):
    allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    allow_methods: list[str] = Field(
        default_factory=lambda: [
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "OPTIONS",
            "PATCH",
            "HEAD",
        ]
    )
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = True

    @model_validator(mode="after")
    def validate_credentials_and_origins(self):
        if self.allow_credentials and "*" in self.allowed_hosts:
            raise ValueError("allow_credentials requires explicit allowed_hosts")
        return self
