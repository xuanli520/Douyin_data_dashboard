from .auth import router as auth_router
from .core import router as core_router
from .monitor import router as monitor_router
from .oauth import create_oauth_router
from .admin import router as admin_router
from .v1 import data_import

__all__ = [
    "auth_router",
    "core_router",
    "monitor_router",
    "create_oauth_router",
    "admin_router",
    "data_import",
]
