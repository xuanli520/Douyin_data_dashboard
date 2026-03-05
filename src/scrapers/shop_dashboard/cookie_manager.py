from __future__ import annotations

from typing import Any

from src.domains.data_source.models import DataSource
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


class CookieManager:
    def get_for_runtime(
        self, runtime_config: ShopDashboardRuntimeConfig
    ) -> dict[str, str]:
        return dict(runtime_config.cookies)

    def get_for_data_source(self, data_source: DataSource) -> dict[str, str]:
        cookies = data_source.cookies
        if isinstance(cookies, str):
            return self._parse_cookie_string(cookies)
        if isinstance(cookies, dict):
            return {str(k): str(v) for k, v in cookies.items() if v is not None}
        return {}

    def apply_refresh(
        self, runtime_config: ShopDashboardRuntimeConfig, refreshed: dict[str, Any]
    ) -> ShopDashboardRuntimeConfig:
        merged = dict(runtime_config.cookies)
        merged.update(
            {str(k): str(v) for k, v in dict(refreshed or {}).items() if v is not None}
        )
        runtime_config.cookies = merged
        return runtime_config

    @staticmethod
    def _parse_cookie_string(cookie_text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for pair in cookie_text.split(";"):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key:
                result[key] = value
        return result
