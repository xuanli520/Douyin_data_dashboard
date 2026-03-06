from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urlparse
from typing import Any

from src.config import get_settings
from src.scrapers.shop_dashboard.cookie_manager import CookieManager
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.exceptions import ScrapingFailedException


class BrowserScraper:
    def __init__(
        self,
        refresher: Callable[[ShopDashboardRuntimeConfig], Any] | None = None,
        cookie_manager: CookieManager | None = None,
    ) -> None:
        self._refresher = refresher
        self._cookie_manager = cookie_manager or CookieManager()
        self._settings = get_settings().shop_dashboard

    async def refresh_runtime_context(
        self,
        runtime_config: ShopDashboardRuntimeConfig,
    ) -> ShopDashboardRuntimeConfig:
        refreshed_query: dict[str, Any] = {}

        async def _refresh_cookie() -> dict[str, str]:
            refreshed = await self._refresh_payload(runtime_config)
            query = dict(refreshed.get("common_query") or {})
            if query:
                refreshed_query.update(query)
            return {
                str(k): str(v) for k, v in dict(refreshed.get("cookies") or {}).items()
            }

        cookies = await self._cookie_manager.get(
            runtime_config.shop_id,
            fallback=runtime_config.cookies,
            refresher=_refresh_cookie,
        )
        if cookies:
            runtime_config.cookies = dict(cookies)
        if refreshed_query:
            runtime_config.common_query.update(refreshed_query)
        return runtime_config

    def retry_http(
        self,
        http_scraper,
        runtime_config: ShopDashboardRuntimeConfig,
        date: str,
    ) -> dict[str, Any]:
        refreshed_config = asyncio.run(self.refresh_runtime_context(runtime_config))
        payload = http_scraper.fetch_dashboard_with_context(refreshed_config, date)
        payload["source"] = "browser"
        return payload

    async def scrape_dashboard(
        self,
        runtime_config: ShopDashboardRuntimeConfig,
        date: str,
    ) -> dict[str, Any]:
        refreshed = await self.refresh_runtime_context(runtime_config)
        payload = await self._refresh_with_playwright(refreshed, date)
        payload["source"] = "browser"
        return payload

    async def _refresh_payload(
        self, runtime_config: ShopDashboardRuntimeConfig
    ) -> dict[str, Any]:
        if self._refresher is not None:
            refreshed = self._refresher(runtime_config)
            if inspect.isawaitable(refreshed):
                refreshed = await refreshed
            return dict(refreshed or {})
        return await self._refresh_with_playwright(runtime_config)

    async def _refresh_with_playwright(
        self,
        runtime_config: ShopDashboardRuntimeConfig,
        date: str | None = None,
    ) -> dict[str, Any]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ScrapingFailedException("Playwright is not installed") from exc

        browser = None
        context = None
        try:
            async with async_playwright() as playwright:
                launch_kwargs: dict[str, Any] = {
                    "headless": self._settings.browser_headless,
                }
                if runtime_config.proxy:
                    launch_kwargs["proxy"] = {"server": runtime_config.proxy}
                browser = await playwright.chromium.launch(**launch_kwargs)

                context_kwargs: dict[str, Any] = {}
                if self._settings.browser_user_agent:
                    context_kwargs["user_agent"] = self._settings.browser_user_agent
                context = await browser.new_context(**context_kwargs)

                runtime_cookie_records = self._runtime_cookie_records(runtime_config)
                if runtime_cookie_records:
                    await context.add_cookies(runtime_cookie_records)

                page = await context.new_page()
                target_url = self._build_target_url(runtime_config, date)
                await page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=self._settings.browser_timeout_seconds * 1000,
                )
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=self._settings.browser_timeout_seconds * 1000,
                )
                page_html = await page.content()
                cookie_list = await context.cookies()
                cookie_mapping = self._extract_cookie_mapping(
                    cookie_list, runtime_config.token_keys
                )
                return {
                    "cookies": cookie_mapping,
                    "common_query": dict(runtime_config.common_query),
                    "raw": {"html": page_html},
                }
        except Exception as exc:
            raise ScrapingFailedException("Browser scraping failed") from exc
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()

    def _runtime_cookie_records(
        self, runtime_config: ShopDashboardRuntimeConfig
    ) -> list[dict[str, Any]]:
        hostname = urlparse(self._settings.base_url).hostname or "fxg.jinritemai.com"
        records: list[dict[str, Any]] = []
        for key, value in dict(runtime_config.cookies).items():
            records.append(
                {
                    "name": str(key),
                    "value": str(value),
                    "domain": hostname,
                    "path": "/",
                }
            )
        return records

    def _build_target_url(
        self, runtime_config: ShopDashboardRuntimeConfig, date: str | None
    ) -> str:
        base = self._settings.browser_refresh_url or self._settings.base_url
        parsed = urlparse(base)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update({str(k): str(v) for k, v in runtime_config.common_query.items()})
        if date:
            query["date"] = date
        encoded = urlencode(query)
        return parsed._replace(query=encoded).geturl()

    def _extract_cookie_mapping(
        self, cookies: list[dict[str, Any]], token_keys: list[str]
    ) -> dict[str, str]:
        selected_keys = {str(item) for item in token_keys if str(item)}
        mapping: dict[str, str] = {}
        for cookie in cookies:
            key = str(cookie.get("name") or "")
            if not key:
                continue
            if selected_keys and key not in selected_keys:
                continue
            value = cookie.get("value")
            if value is None:
                continue
            mapping[key] = str(value)
        return mapping
