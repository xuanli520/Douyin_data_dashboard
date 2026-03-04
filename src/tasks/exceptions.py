from enum import IntEnum

from src.tasks.funboost_compat import FunboostException


class TaskErrorCode(IntEnum):
    SCRAPING_RATE_LIMIT = 61001
    SCRAPING_FAILED = 61002
    SHOP_DASHBOARD_COOKIE_EXPIRED = 62001
    SHOP_DASHBOARD_DATA_INCOMPLETE = 62002


class ScrapingRateLimitException(FunboostException):
    default_message = "Rate limited"
    default_code = TaskErrorCode.SCRAPING_RATE_LIMIT


class ScrapingFailedException(FunboostException):
    default_message = "Scraping failed"
    default_code = TaskErrorCode.SCRAPING_FAILED


class ShopDashboardCookieExpiredException(FunboostException):
    default_message = "Shop dashboard cookie expired"
    default_code = TaskErrorCode.SHOP_DASHBOARD_COOKIE_EXPIRED


class ShopDashboardDataIncompleteException(FunboostException):
    default_message = "Shop dashboard data incomplete"
    default_code = TaskErrorCode.SHOP_DASHBOARD_DATA_INCOMPLETE
