from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.audit import AuditService, get_audit_service
from src.audit.schemas import AuditAction, AuditResult
from src.audit.service import extract_client_info
from src.auth import fastapi_users
from src.auth.models import User
from src.auth.backend import (
    RefreshTokenManager,
    get_jwt_strategy,
    get_refresh_token_manager,
)
from src.auth.captcha import AliyunCaptchaService, get_captcha_service
from src.auth.manager import UserManager, get_user_manager
from src.auth.schemas import (
    AccessTokenResponse,
    MessageResponse,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from src.shared.errors import ErrorCode
from src.exceptions import BusinessException
from src.session import get_session


router = APIRouter()


async def _load_user_with_roles(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def _resolve_account_type(user: User) -> str | None:
    if user.is_superuser:
        return "admin"
    role_names = [
        role.name.strip().lower() for role in (user.roles or []) if role and role.name
    ]
    if "admin" in role_names or "super_admin" in role_names:
        return "admin"
    if "operator" in role_names:
        return "operator"
    if "analyst" in role_names:
        return "analyst"
    if "api" in role_names:
        return "api"
    if "user" in role_names:
        return "operator"
    return role_names[0] if role_names else None


def _build_audit_extra(user: User | None = None, username: str | None = None) -> dict:
    extra: dict = {}
    if username:
        extra["username"] = username
    if user and user.id is not None:
        extra["user_id"] = str(user.id)
        account_type = _resolve_account_type(user)
        if account_type:
            extra["account_type"] = account_type
    return extra


router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="",
    tags=["auth"],
)

router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="",
    tags=["auth"],
)

router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="",
    tags=["auth"],
)

router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)


@router.post("/jwt/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    captchaVerifyParam: str | None = Form(None),
    user_manager: UserManager = Depends(get_user_manager),
    strategy=Depends(get_jwt_strategy),
    refresh_manager: RefreshTokenManager = Depends(get_refresh_token_manager),
    audit_service: AuditService = Depends(get_audit_service),
    captcha_service: AliyunCaptchaService = Depends(get_captcha_service),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user_agent, ip = extract_client_info(request)

    try:
        is_human = await captcha_service.verify(captchaVerifyParam)
    except Exception:
        is_human = False

    if not is_human:
        extra = _build_audit_extra(username=username)
        extra["reason"] = "captcha_failed"
        await audit_service.log(
            action=AuditAction.LOGIN,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
            extra=extra,
        )
        raise BusinessException(
            ErrorCode.AUTH_INVALID_CREDENTIALS, "Captcha verification failed"
        )

    credentials = type(
        "Credentials",
        (),
        {"username": username, "password": password},
    )()
    user = await user_manager.authenticate(credentials)
    if not user or not user.is_active:
        extra = _build_audit_extra(username=username)
        await audit_service.log(
            action=AuditAction.LOGIN,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
            extra=extra,
        )
        raise BusinessException(
            ErrorCode.AUTH_INVALID_CREDENTIALS, "Invalid credentials"
        )

    access_token = await strategy.write_token(user)

    refresh_token = await refresh_manager.create_refresh_token(user.id, user_agent)

    user_with_roles = await _load_user_with_roles(session, user.id) or user
    extra = _build_audit_extra(user_with_roles, user.username)
    await audit_service.log(
        action=AuditAction.LOGIN,
        result=AuditResult.SUCCESS,
        actor_id=user.id,
        user_agent=user_agent,
        ip=ip,
        extra=extra or None,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
    )


@router.post("/jwt/refresh")
async def refresh_jwt(
    request: Request,
    refresh_token: str,
    user_manager: UserManager = Depends(get_user_manager),
    strategy=Depends(get_jwt_strategy),
    refresh_manager: RefreshTokenManager = Depends(get_refresh_token_manager),
    audit_service: AuditService = Depends(get_audit_service),
    session: AsyncSession = Depends(get_session),
) -> AccessTokenResponse:
    user_agent, ip = extract_client_info(request)

    user_id = await refresh_manager.verify_refresh_token(refresh_token)

    if not user_id:
        await audit_service.log(
            action=AuditAction.REFRESH,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
        )
        raise BusinessException(ErrorCode.AUTH_TOKEN_INVALID, "Invalid token")

    user = await user_manager.get(user_id)
    if not user or not user.is_active:
        extra = None
        if user:
            user_with_roles = await _load_user_with_roles(session, user.id) or user
            extra = _build_audit_extra(user_with_roles, user.username)
        await audit_service.log(
            action=AuditAction.REFRESH,
            result=AuditResult.FAILURE,
            actor_id=user_id,
            user_agent=user_agent,
            ip=ip,
            extra=extra,
        )
        raise BusinessException(ErrorCode.USER_INACTIVE, "User inactive")

    access_token = await strategy.write_token(user)

    user_with_roles = await _load_user_with_roles(session, user.id) or user
    extra = _build_audit_extra(user_with_roles, user.username)
    await audit_service.log(
        action=AuditAction.REFRESH,
        result=AuditResult.SUCCESS,
        actor_id=user.id,
        user_agent=user_agent,
        ip=ip,
        extra=extra or None,
    )

    return AccessTokenResponse(access_token=access_token, token_type="Bearer")


@router.post("/jwt/logout")
async def logout(
    request: Request,
    refresh_token: str,
    refresh_manager: RefreshTokenManager = Depends(get_refresh_token_manager),
    audit_service: AuditService = Depends(get_audit_service),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    user_agent, ip = extract_client_info(request)
    user_id = await refresh_manager.verify_refresh_token(refresh_token)

    if not user_id:
        await audit_service.log(
            action=AuditAction.LOGOUT,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
        )
        raise BusinessException(ErrorCode.AUTH_TOKEN_INVALID, "Invalid token")

    await refresh_manager.revoke_token(refresh_token)

    user_with_roles = await _load_user_with_roles(session, user_id)
    extra = (
        _build_audit_extra(user_with_roles, user_with_roles.username)
        if user_with_roles
        else None
    )
    await audit_service.log(
        action=AuditAction.LOGOUT,
        result=AuditResult.SUCCESS,
        actor_id=user_id,
        user_agent=user_agent,
        ip=ip,
        extra=extra,
    )

    return MessageResponse(detail="Successfully logged out")
