from fastapi import Request
from fastapi.responses import Response

from src.config import Settings


def is_https_request(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        first_proto = forwarded_proto.split(",")[0].strip().lower()
        if first_proto == "https":
            return True
    return request.url.scheme == "https"


def set_auth_cookie(
    response: Response,
    *,
    name: str,
    value: str,
    max_age: int,
    request: Request,
    settings: Settings,
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=settings.auth.cookie_path,
        domain=None,
        secure=is_https_request(request),
        httponly=settings.auth.cookie_httponly,
        samesite=settings.auth.cookie_samesite,
    )


def clear_auth_cookie(
    response: Response, *, name: str, request: Request, settings: Settings
) -> None:
    response.delete_cookie(
        name,
        path=settings.auth.cookie_path,
        domain=None,
        secure=is_https_request(request),
        httponly=settings.auth.cookie_httponly,
        samesite=settings.auth.cookie_samesite,
    )


def clear_session_cookies(
    response: Response, request: Request, settings: Settings
) -> None:
    clear_auth_cookie(
        response,
        name=settings.auth.access_cookie_name,
        request=request,
        settings=settings,
    )
    clear_auth_cookie(
        response,
        name=settings.auth.refresh_cookie_name,
        request=request,
        settings=settings,
    )
