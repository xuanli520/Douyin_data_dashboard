from enum import IntEnum


class TaskErrorCode(IntEnum):
    SCRAPING_RATE_LIMIT = 61001
    SCRAPING_FAILED = 61002
    SHOP_DASHBOARD_COOKIE_EXPIRED = 62001
    SHOP_DASHBOARD_DATA_INCOMPLETE = 62002
    SHOP_DASHBOARD_NO_TARGET_SHOPS = 62003
    SHOP_DASHBOARD_SHOP_MISMATCH = 62004
    SHOP_DASHBOARD_SHOP_CIRCUIT_BREAK = 62005


class TaskDomainException(Exception):
    default_message = "Task exception"
    default_code = 0

    def __init__(self, message: str | None = None, error_data: dict | None = None):
        self.error_data = error_data or {}
        super().__init__(message or self.default_message)


class ScrapingRateLimitException(TaskDomainException):
    default_message = "Rate limited"
    default_code = TaskErrorCode.SCRAPING_RATE_LIMIT


class ScrapingFailedException(TaskDomainException):
    default_message = "Scraping failed"
    default_code = TaskErrorCode.SCRAPING_FAILED


class ShopDashboardCookieExpiredException(TaskDomainException):
    default_message = "Shop dashboard cookie expired"
    default_code = TaskErrorCode.SHOP_DASHBOARD_COOKIE_EXPIRED


class ShopDashboardDataIncompleteException(TaskDomainException):
    default_message = "Shop dashboard data incomplete"
    default_code = TaskErrorCode.SHOP_DASHBOARD_DATA_INCOMPLETE


class ShopDashboardNoTargetShopsException(TaskDomainException):
    default_message = "No target shops resolved"
    default_code = TaskErrorCode.SHOP_DASHBOARD_NO_TARGET_SHOPS


class ShopDashboardShopMismatchException(TaskDomainException):
    default_message = "Shop mismatch detected"
    default_code = TaskErrorCode.SHOP_DASHBOARD_SHOP_MISMATCH


class ShopDashboardShopCircuitBreakException(TaskDomainException):
    default_message = "Shop is circuit broken"
    default_code = TaskErrorCode.SHOP_DASHBOARD_SHOP_CIRCUIT_BREAK
