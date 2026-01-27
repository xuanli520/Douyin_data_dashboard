from pydantic import Field
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
