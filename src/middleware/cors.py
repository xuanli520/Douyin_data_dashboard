from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from src.config import get_settings

settings = get_settings()

CORS_ALLOWED_HOSTS = settings.cors.allowed_hosts
CORS_ALLOWED_METHODS = settings.cors.allow_methods
CORS_ALLOWED_HEADERS = settings.cors.allow_headers
CORS_ALLOW_CREDENTIALS = settings.cors.allow_credentials


def get_cors_middleware() -> Middleware:
    return Middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED_HOSTS,
        allow_credentials=CORS_ALLOW_CREDENTIALS,
        allow_methods=CORS_ALLOWED_METHODS,
        allow_headers=CORS_ALLOWED_HEADERS,
    )
