from .auth import router as auth_router
from .core import router as core_router
from .monitor import router as monitor_router
from .oauth import create_oauth_router
from .admin import router as admin_router
from .v1.data_source import router as data_source_router
from .v1.data_source import scraping_rule_router
from .v1.data_import import router as data_import_router
from .v1.task import router as task_router
from .v1.alerts import router as alerts_router
from .v1.shops import router as shops_router
from .v1.metrics import router as metrics_router
from .v1.experience import router as experience_router
from .v1.dashboard import router as dashboard_router
from .v1.orders import router as orders_router
from .v1.products import router as products_router
from .v1.sales import router as sales_router
from .v1.after_sales import router as after_sales_router
from .v1.notifications import router as notifications_router
from .v1.reports import router as reports_router
from .v1.exports import router as exports_router
from .v1.schedules import router as schedules_router
from .v1.analysis import router as analysis_router
from .v1.system import router as system_router
from .v1 import permissions_router
from .audit import router as audit_router

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
    "alerts_router",
    "shops_router",
    "metrics_router",
    "experience_router",
    "dashboard_router",
    "orders_router",
    "products_router",
    "sales_router",
    "after_sales_router",
    "notifications_router",
    "reports_router",
    "exports_router",
    "schedules_router",
    "analysis_router",
    "system_router",
    "permissions_router",
    "audit_router",
]
