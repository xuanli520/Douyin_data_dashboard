from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import exceptions
from fastapi_users import BaseUserManager, IntegerIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache import CacheProtocol, get_cache
from src.auth.models import OAuthAccount, User
from src.config import Settings, get_settings
from src.session import get_session


async def get_user_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    def __init__(self, user_db, settings: Settings, cache: CacheProtocol):
        super().__init__(user_db)
        self.settings = settings
        self.cache = cache

    @property
    def reset_password_token_secret(self):
        return self.settings.auth.jwt_secret

    @property
    def verification_token_secret(self):
        return self.settings.auth.jwt_secret

    async def authenticate(
        self, credentials: OAuth2PasswordRequestForm
    ) -> User | None:
        try:
            user = await self.get_by_email(credentials.username)
        except exceptions.UserNotExists:
            user = await self._get_by_username(credentials.username)

        if user is None:
            self.password_helper.hash(credentials.password)
            return None

        verified, updated_password_hash = self.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )
        if not verified:
            return None
        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})

        return user

    async def _get_by_username(self, username: str) -> User | None:
        statement = select(User).where(func.lower(User.username) == func.lower(username))
        results = await self.user_db.session.execute(statement)
        return results.unique().scalar_one_or_none()

    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        pass

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        pass

    async def on_after_reset_password(
        self, user: User, request: Request | None = None
    ) -> None:
        from .backend import RefreshTokenManager

        refresh_manager = RefreshTokenManager(self.cache, self.settings)
        await refresh_manager.revoke_all_user_tokens(user.id)


async def get_user_manager(
    user_db=Depends(get_user_db),
    settings: Settings = Depends(get_settings),
    cache: CacheProtocol = Depends(get_cache),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db, settings, cache)
