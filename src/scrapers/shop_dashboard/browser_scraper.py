from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.scrapers.shop_dashboard.cookie_manager import CookieManager
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


class BrowserScraper:
    def __init__(
        self,
        refresher: Callable[[ShopDashboardRuntimeConfig], dict[str, Any]] | None = None,
        cookie_manager: CookieManager | None = None,
    ) -> None:
        self._refresher = refresher
        self._cookie_manager = cookie_manager or CookieManager()

    def refresh_runtime_context(
        self,
        runtime_config: ShopDashboardRuntimeConfig,
    ) -> ShopDashboardRuntimeConfig:
        if self._refresher is None:
            return runtime_config
        refreshed = dict(self._refresher(runtime_config) or {})
        refreshed_cookies = dict(refreshed.get("cookies") or {})
        if refreshed_cookies:
            self._cookie_manager.apply_refresh(runtime_config, refreshed_cookies)
        refreshed_query = dict(refreshed.get("common_query") or {})
        if refreshed_query:
            runtime_config.common_query.update(refreshed_query)
        return runtime_config

    def retry_http(
        self,
        http_scraper,
        runtime_config: ShopDashboardRuntimeConfig,
        date: str,
    ) -> dict[str, Any]:
        refreshed_config = self.refresh_runtime_context(runtime_config)
        payload = http_scraper.fetch_dashboard_with_context(refreshed_config, date)
        payload["source"] = "browser"
        return payload
