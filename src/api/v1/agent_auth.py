from __future__ import annotations

from fastapi import WebSocket
from fastapi_users.db import SQLAlchemyUserDatabase

from src import cache as cache_module
from src import session as session_module
from src.auth import User
from src.auth.backend import get_jwt_strategy
from src.auth.manager import UserManager
from src.auth.models import OAuthAccount
from src.auth.rbac import PermissionRepository
from src.auth.rbac import PermissionService
from src.config import get_settings


async def authorize_agent_websocket(
    websocket: WebSocket,
    permission: str,
) -> bool:
    token = _websocket_token(websocket)
    if not token:
        return False
    session_factory = session_module.async_session_factory
    if session_factory is None:
        return False
    async with session_factory() as db_session:
        user_db = SQLAlchemyUserDatabase(db_session, User, OAuthAccount)
        user_manager = UserManager(user_db, get_settings(), cache_module.cache)
        strategy = get_jwt_strategy(get_settings())
        user = await strategy.read_token(token, user_manager)
        if user is None or not user.is_active:
            return False
        if user.is_superuser:
            return True
        permission_service = PermissionService(PermissionRepository(db_session))
        return await permission_service.check_permissions(user.id, [permission])


def _websocket_token(websocket: WebSocket) -> str | None:
    authorization = websocket.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.casefold() == "bearer" and value.strip():
        return value.strip()
    query_token = websocket.query_params.get("access_token")
    if query_token:
        return query_token
    settings = get_settings()
    return websocket.cookies.get(settings.auth.access_cookie_name)
