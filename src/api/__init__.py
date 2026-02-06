from .auth import router as auth_router
from .core import router as core_router
from .monitor import router as monitor_router
from .oauth import create_oauth_router
from .admin import router as admin_router
from .v1.data_source import router as data_source_router
from .v1.data_source import scraping_rule_router
from .v1.data_import import router as data_import_router
from .v1.task import router as task_router

__all__ = [
    "auth_router",
    "core_router",
    "monitor_router",
    "create_oauth_router",
    "admin_router",
    "data_source_router",
    "scraping_rule_router",
    "data_import_router",
    "task_router",
]
