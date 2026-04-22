"""Auth backend defining JWT strategy + refresh token management."""

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Request
from fastapi.responses import Response
from fastapi.security.api_key import APIKeyCookie
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.password import PasswordHelper
from starlette import status

from src.auth.cookies import get_auth_request, should_secure_cookie
from src.cache import CacheProtocol, get_cache
from src.config import Settings, get_settings
from src.shared.redis_keys import redis_keys

_password_helper = PasswordHelper()


def get_password_hash(password: str) -> str:
    return _password_helper.hash(password)


def get_jwt_strategy(settings=Depends(get_settings)) -> JWTStrategy:
    return JWTStrategy(
        secret=settings.auth.jwt_secret,
        algorithm=settings.auth.jwt_algorithm,
        lifetime_seconds=settings.auth.jwt_lifetime_seconds,
    )


class RefreshTokenManager:
    """
    Refresh token manager that handles creation, verification, and revocation of refresh tokens.

    Special Notes: 1. `fastapi-users` does not provide built-in support for refresh tokens.
    2. Revocation (token blacklist) is implemented via cache-based approach, which requires refresh token stateful (opaque token).
    3. JWT (access token) remains stateless.
    """

    def __init__(self, cache: CacheProtocol, settings: Settings):
        self._cache = cache
        self.settings = settings

    async def create_refresh_token(
        self, user_id: int, device_info: str | None = None
    ) -> str:
        """Create a refresh token for the given user.

        Args:
            user_id: The user's ID.
            device_info: Optional device information for tracking. Retrieved from User-Agent Header.

        Returns:
            The generated refresh token string.
        """
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        value = f"{user_id}:{device_info or 'unknown'}:{datetime.now(timezone.utc).isoformat()}"

        await self._cache.set(
            redis_keys.refresh_token(token_hash=token_hash),
            value,
            ttl=self.settings.auth.refresh_token_lifetime_seconds,
        )
        return token

    async def verify_refresh_token(self, token: str) -> int | None:
        """Verify the given refresh token.

        Returns:
            The user ID if the token is valid, None otherwise.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        value = await self._cache.get(redis_keys.refresh_token(token_hash=token_hash))
        if not value:
            return None

        try:
            parts = value.split(":", maxsplit=2)
            user_id = int(parts[0])
            token_created_time = parts[2]
        except (IndexError, ValueError):
            return None

        revoke_time = await self._cache.get(redis_keys.user_revoked(user_id=user_id))
        if revoke_time:
            try:
                created_at = datetime.fromisoformat(token_created_time)
                revoked_at = datetime.fromisoformat(revoke_time)
            except ValueError:
                return None

            if created_at <= revoked_at:
                return None

        return user_id

    async def revoke_token(self, token: str) -> None:
        """Revoke a specific refresh token, deleting it from the cache."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        await self._cache.delete(redis_keys.refresh_token(token_hash=token_hash))

    async def revoke_all_user_tokens(self, user_id: int) -> None:
        """Add the user to the revoked list to invalidate all their refresh tokens."""
        revoke_time = datetime.now(timezone.utc).isoformat()
        await self._cache.set(
            redis_keys.user_revoked(user_id=user_id),
            revoke_time,
            ttl=self.settings.auth.refresh_token_lifetime_seconds,
        )


def get_refresh_token_manager(
    cache: CacheProtocol = Depends(get_cache),
    settings: Settings = Depends(get_settings),
) -> RefreshTokenManager:
    return RefreshTokenManager(cache, settings)


class DynamicAPIKeyCookie(APIKeyCookie):
    def __init__(self) -> None:
        super().__init__(name=get_settings().auth.access_cookie_name, auto_error=False)

    async def __call__(self, request: Request) -> str | None:
        self.model.name = get_settings().auth.access_cookie_name
        api_key = request.cookies.get(self.model.name)
        return self.check_api_key(api_key)


class RuntimeCookieTransport:
    scheme: APIKeyCookie

    def __init__(self) -> None:
        self.scheme = DynamicAPIKeyCookie()

    @property
    def cookie_name(self) -> str:
        return get_settings().auth.access_cookie_name

    @property
    def cookie_max_age(self) -> int:
        return get_settings().auth.jwt_lifetime_seconds

    @property
    def cookie_path(self) -> str:
        return get_settings().auth.cookie_path

    @property
    def cookie_domain(self) -> None:
        return None

    @property
    def cookie_secure(self) -> bool:
        settings = get_settings()
        return should_secure_cookie(get_auth_request(), settings)

    @property
    def cookie_httponly(self) -> bool:
        return get_settings().auth.cookie_httponly

    @property
    def cookie_samesite(self) -> str:
        return get_settings().auth.cookie_samesite

    async def get_login_response(self, token: str) -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.set_cookie(
            self.cookie_name,
            token,
            max_age=self.cookie_max_age,
            path=self.cookie_path,
            domain=self.cookie_domain,
            secure=self.cookie_secure,
            httponly=self.cookie_httponly,
            samesite=self.cookie_samesite,
        )
        return response

    async def get_logout_response(self) -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.set_cookie(
            self.cookie_name,
            "",
            max_age=0,
            path=self.cookie_path,
            domain=self.cookie_domain,
            secure=self.cookie_secure,
            httponly=self.cookie_httponly,
            samesite=self.cookie_samesite,
        )
        return response

    @staticmethod
    def get_openapi_login_responses_success():
        return {status.HTTP_204_NO_CONTENT: {"model": None}}

    @staticmethod
    def get_openapi_logout_responses_success():
        return {status.HTTP_204_NO_CONTENT: {"model": None}}


bearer_transport = BearerTransport(tokenUrl="/auth/login")
cookie_transport = RuntimeCookieTransport()

bearer_auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

cookie_auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)
