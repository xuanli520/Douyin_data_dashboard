from __future__ import annotations

from typing import Any


class ShopDashboardScraperError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_data: dict[str, Any] | None = None,
    ) -> None:
        self.error_data = dict(error_data or {})
        super().__init__(message)


class LoginExpiredError(ShopDashboardScraperError):
    pass


class DataIncompleteError(ShopDashboardScraperError):
    pass
