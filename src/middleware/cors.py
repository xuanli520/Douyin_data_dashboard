from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from src.config import get_settings


def get_cors_middleware() -> Middleware:
    settings = get_settings()
    return Middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allowed_hosts,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
    )
