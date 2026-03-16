from enum import IntEnum

from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class TaskErrorCode(IntEnum):
    SCRAPING_RATE_LIMIT = int(ErrorCode.SCRAPING_RATE_LIMIT)
    SCRAPING_FAILED = int(ErrorCode.SCRAPING_FAILED)
    SHOP_DASHBOARD_COOKIE_EXPIRED = int(ErrorCode.SHOP_DASHBOARD_COOKIE_EXPIRED)
    SHOP_DASHBOARD_DATA_INCOMPLETE = int(ErrorCode.SHOP_DASHBOARD_DATA_INCOMPLETE)
    SHOP_DASHBOARD_NO_TARGET_SHOPS = int(ErrorCode.SHOP_DASHBOARD_NO_TARGET_SHOPS)
    SHOP_DASHBOARD_SHOP_MISMATCH = int(ErrorCode.SHOP_DASHBOARD_SHOP_MISMATCH)
    SHOP_DASHBOARD_SHOP_CIRCUIT_BREAK = int(ErrorCode.SHOP_DASHBOARD_SHOP_CIRCUIT_BREAK)


class TaskDomainException(BusinessException):
    default_message = "Task exception"
    default_code = ErrorCode.SYS_INTERNAL_ERROR

    def __init__(self, message: str | None = None, error_data: dict | None = None):
        resolved_error_data = dict(error_data or {})
        self.error_data = resolved_error_data
        super().__init__(
            code=self.default_code,
            msg=message or self.default_message,
            data=resolved_error_data,
        )

    def __str__(self) -> str:
        return self.msg


class ScrapingRateLimitException(TaskDomainException):
    default_message = "Rate limited"
    default_code = ErrorCode.SCRAPING_RATE_LIMIT


class ScrapingFailedException(TaskDomainException):
    default_message = "Scraping failed"
    default_code = ErrorCode.SCRAPING_FAILED


class ShopDashboardCookieExpiredException(TaskDomainException):
    default_message = "Shop dashboard cookie expired"
    default_code = ErrorCode.SHOP_DASHBOARD_COOKIE_EXPIRED


class ShopDashboardDataIncompleteException(TaskDomainException):
    default_message = "Shop dashboard data incomplete"
    default_code = ErrorCode.SHOP_DASHBOARD_DATA_INCOMPLETE


class ShopDashboardNoTargetShopsException(TaskDomainException):
    default_message = "No target shops resolved"
    default_code = ErrorCode.SHOP_DASHBOARD_NO_TARGET_SHOPS


class ShopDashboardShopMismatchException(TaskDomainException):
    default_message = "Shop mismatch detected"
    default_code = ErrorCode.SHOP_DASHBOARD_SHOP_MISMATCH


class ShopDashboardShopCircuitBreakException(TaskDomainException):
    default_message = "Shop is circuit broken"
    default_code = ErrorCode.SHOP_DASHBOARD_SHOP_CIRCUIT_BREAK
