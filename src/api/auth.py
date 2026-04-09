from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
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
from src.auth.cookies import clear_session_cookies, set_auth_cookie
from src.auth.captcha import AliyunCaptchaService, get_captcha_service
from src.auth.manager import UserManager, get_user_manager
from src.auth.schemas import (
    MessageResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from src.config import Settings, get_settings
from src.shared.errors import ErrorCode
from src.exceptions import AuthSessionException, BusinessException
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


@router.post("/login")
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
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    user_agent, ip = extract_client_info(request)

    try:
        is_human = await captcha_service.verify(captchaVerifyParam)
    except Exception:
        extra = _build_audit_extra(username=username)
        extra["reason"] = "captcha_unavailable"
        await audit_service.log(
            action=AuditAction.LOGIN,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
            extra=extra,
        )
        raise BusinessException(
            ErrorCode.SYS_INTERNAL_ERROR, "Captcha service unavailable"
        )

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

    response = JSONResponse(
        status_code=200,
        content=MessageResponse(detail="Login successful").model_dump(),
    )
    set_auth_cookie(
        response,
        name=settings.auth.access_cookie_name,
        value=access_token,
        max_age=settings.auth.jwt_lifetime_seconds,
        request=request,
        settings=settings,
    )
    set_auth_cookie(
        response,
        name=settings.auth.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.auth.refresh_token_lifetime_seconds,
        request=request,
        settings=settings,
    )
    return response


@router.post("/refresh")
async def refresh_jwt(
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
    strategy=Depends(get_jwt_strategy),
    refresh_manager: RefreshTokenManager = Depends(get_refresh_token_manager),
    audit_service: AuditService = Depends(get_audit_service),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    user_agent, ip = extract_client_info(request)
    refresh_token = request.cookies.get(settings.auth.refresh_cookie_name)

    if not refresh_token:
        await audit_service.log(
            action=AuditAction.REFRESH,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
        )
        raise AuthSessionException(
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid token",
        )

    user_id = await refresh_manager.verify_refresh_token(refresh_token)

    if not user_id:
        await audit_service.log(
            action=AuditAction.REFRESH,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
        )
        raise AuthSessionException(
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid token",
        )

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
        raise AuthSessionException(
            ErrorCode.USER_INACTIVE,
            "User inactive",
        )

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

    response = JSONResponse(
        status_code=200,
        content=MessageResponse(detail="Session refreshed").model_dump(),
    )
    set_auth_cookie(
        response,
        name=settings.auth.access_cookie_name,
        value=access_token,
        max_age=settings.auth.jwt_lifetime_seconds,
        request=request,
        settings=settings,
    )
    return response


@router.post("/logout")
async def logout(
    request: Request,
    refresh_manager: RefreshTokenManager = Depends(get_refresh_token_manager),
    audit_service: AuditService = Depends(get_audit_service),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    user_agent, ip = extract_client_info(request)
    refresh_token = request.cookies.get(settings.auth.refresh_cookie_name)

    if not refresh_token:
        await audit_service.log(
            action=AuditAction.LOGOUT,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
        )
        raise AuthSessionException(
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid token",
        )

    user_id = await refresh_manager.verify_refresh_token(refresh_token)

    if not user_id:
        await audit_service.log(
            action=AuditAction.LOGOUT,
            result=AuditResult.FAILURE,
            user_agent=user_agent,
            ip=ip,
        )
        raise AuthSessionException(
            ErrorCode.AUTH_TOKEN_INVALID,
            "Invalid token",
        )

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

    response = JSONResponse(
        status_code=200,
        content=MessageResponse(detail="Successfully logged out").model_dump(),
    )
    clear_session_cookies(response, request, settings)
    return response
