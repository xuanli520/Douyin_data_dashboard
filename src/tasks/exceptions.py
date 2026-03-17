from src.domains.task.exceptions import ScrapingFailedException
from src.domains.task.exceptions import ScrapingRateLimitException
from src.domains.task.exceptions import ShopDashboardCookieExpiredException
from src.domains.task.exceptions import ShopDashboardDataIncompleteException
from src.domains.task.exceptions import ShopDashboardNoTargetShopsException
from src.domains.task.exceptions import ShopDashboardShopCircuitBreakException
from src.domains.task.exceptions import ShopDashboardShopMismatchException
from src.domains.task.exceptions import TaskErrorCode

__all__ = [
    "TaskErrorCode",
    "ScrapingRateLimitException",
    "ScrapingFailedException",
    "ShopDashboardCookieExpiredException",
    "ShopDashboardDataIncompleteException",
    "ShopDashboardNoTargetShopsException",
    "ShopDashboardShopMismatchException",
    "ShopDashboardShopCircuitBreakException",
]
