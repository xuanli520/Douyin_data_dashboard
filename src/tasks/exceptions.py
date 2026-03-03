from enum import IntEnum

from src.tasks.funboost_compat import FunboostException


class TaskErrorCode(IntEnum):
    SCRAPING_RATE_LIMIT = 61001
    SCRAPING_FAILED = 61002


class ScrapingRateLimitException(FunboostException):
    default_message = "Rate limited"
    default_code = TaskErrorCode.SCRAPING_RATE_LIMIT


class ScrapingFailedException(FunboostException):
    default_message = "Scraping failed"
    default_code = TaskErrorCode.SCRAPING_FAILED
