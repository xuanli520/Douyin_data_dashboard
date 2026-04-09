from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class AuthSettings(BaseSettings):
    jwt_secret: str

    jwt_algorithm: Literal["HS256", "HS512"] = Field(default="HS256")
    jwt_lifetime_seconds: int = Field(default=1800)
    refresh_token_lifetime_seconds: int = Field(default=2592000)
    access_cookie_name: str = Field(default="access_token")
    refresh_cookie_name: str = Field(default="refresh_token")
    cookie_path: str = Field(default="/")
    cookie_samesite: str = Field(default="lax")
    cookie_httponly: bool = Field(default=True)
    cookie_secure: bool = Field(default=False)

    oauth_google_client_id: str | None = None
    oauth_google_client_secret: str | None = None
    oauth_github_client_id: str | None = None
    oauth_github_client_secret: str | None = None
