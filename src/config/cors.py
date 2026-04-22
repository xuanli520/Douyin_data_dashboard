from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


INSECURE_ALLOWED_ORIGINS = {"http://8.137.84.161:3456"}


class CorsSettings(BaseSettings):
    allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://8.137.84.161:3456",
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
    allow_headers: list[str] = Field(
        default_factory=lambda: ["Authorization", "Content-Type", "X-Request-ID"]
    )
    allow_credentials: bool = True

    @model_validator(mode="after")
    def validate_credentials_and_origins(self):
        if self.allow_credentials and "*" in self.allowed_hosts:
            raise ValueError("allow_credentials requires explicit allowed_hosts")

        for origin in self.allowed_hosts:
            parsed = urlparse(origin)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("allowed_hosts must be valid origins")

            if origin in INSECURE_ALLOWED_ORIGINS:
                continue

            if parsed.scheme == "https":
                continue

            if (
                parsed.hostname in {"localhost", "127.0.0.1"}
                and parsed.scheme == "http"
            ):
                continue

            raise ValueError("non-localhost allowed_hosts must use https")

        return self
