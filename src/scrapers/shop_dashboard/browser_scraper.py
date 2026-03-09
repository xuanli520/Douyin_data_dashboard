from __future__ import annotations
import asyncio
import inspect
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

from src.config import get_settings
from src.scrapers.shop_dashboard.login_state import check_login_status
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore
from src.tasks.exceptions import ScrapingFailedException


class BrowserScraper:
    def __init__(
        self,
        refresher: Callable[[ShopDashboardRuntimeConfig], Any] | None = None,
        state_store: SessionStateStore | None = None,
        state_dir: str | Path | None = None,
    ) -> None:
        self._refresher = refresher
        self._settings = get_settings().shop_dashboard
        self._state_store = state_store or self._initialize_state_store(state_dir)

    def _initialize_state_store(
        self, state_dir: str | Path | None
    ) -> SessionStateStore:
        target_dir = (
            Path(state_dir) if state_dir else Path(".runtime") / "shop_dashboard_state"
        )
        return SessionStateStore(base_dir=target_dir)

    async def refresh_runtime_context(
        self, runtime_config: ShopDashboardRuntimeConfig
    ) -> ShopDashboardRuntimeConfig:
        refreshed = await self._refresh_payload(runtime_config)
        self._update_runtime_config(refreshed, runtime_config)
        return runtime_config

    def _update_runtime_config(
        self, refreshed: dict[str, Any], runtime_config: ShopDashboardRuntimeConfig
    ) -> None:
        self._update_cookies(refreshed, runtime_config)
        self._update_common_query(refreshed, runtime_config)

    def _update_cookies(
        self, refreshed: dict[str, Any], runtime_config: ShopDashboardRuntimeConfig
    ) -> None:
        refreshed_cookies = {
            str(k): str(v) for k, v in refreshed.get("cookies", {}).items()
        }
        account_id = self._resolve_account_id(runtime_config)
        if refreshed_cookies:
            runtime_config.cookies = refreshed_cookies
        else:
            state_cookies = self._state_store.load_cookie_mapping(account_id)
            if state_cookies:
                runtime_config.cookies = state_cookies

    def _update_common_query(
        self, refreshed: dict[str, Any], runtime_config: ShopDashboardRuntimeConfig
    ) -> None:
        refreshed_query = dict(refreshed.get("common_query") or {})
        if refreshed_query:
            runtime_config.common_query.update(refreshed_query)

    def retry_http(
        self, http_scraper, runtime_config: ShopDashboardRuntimeConfig, date: str
    ) -> dict[str, Any]:
        refreshed_config = asyncio.run(self.refresh_runtime_context(runtime_config))
        payload = http_scraper.fetch_dashboard_with_context(refreshed_config, date)
        payload["source"] = "browser"
        return payload

    async def scrape_dashboard(
        self, runtime_config: ShopDashboardRuntimeConfig, date: str
    ) -> dict[str, Any]:
        refreshed = await self.refresh_runtime_context(runtime_config)
        payload = await self._refresh_with_playwright(refreshed, date)
        payload["source"] = "browser"
        return payload

    async def _refresh_payload(
        self, runtime_config: ShopDashboardRuntimeConfig
    ) -> dict[str, Any]:
        if self._refresher:
            return await self._call_refresher(runtime_config)
        return await self._refresh_with_playwright(runtime_config)

    async def _call_refresher(
        self, runtime_config: ShopDashboardRuntimeConfig
    ) -> dict[str, Any]:
        refreshed = self._refresher(runtime_config)
        if inspect.isawaitable(refreshed):
            refreshed = await refreshed
        return dict(refreshed or {})

    async def _refresh_with_playwright(
        self, runtime_config: ShopDashboardRuntimeConfig, date: str | None = None
    ) -> dict[str, Any]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ScrapingFailedException("Playwright is not installed") from exc

        browser, context = None, None
        account_id = self._resolve_account_id(runtime_config)
        storage_state = self._state_store.load(account_id)

        try:
            async with async_playwright() as playwright:
                launch_kwargs = self._build_browser_launch_kwargs(runtime_config)
                browser = await playwright.chromium.launch(**launch_kwargs)
                context = await self._build_browser_context(browser, storage_state)
                page = await self._create_page(context, runtime_config, date)
                page_html = await page.content()
                storage_state = await context.storage_state()

                self._state_store.save(account_id, storage_state)
                cookie_mapping = await self._extract_cookie_mapping(
                    context, runtime_config.token_keys
                )

                return {
                    "cookies": cookie_mapping,
                    "common_query": dict(runtime_config.common_query),
                    "raw": {"html": page_html},
                    "storage_state": storage_state,
                }
        except ScrapingFailedException:
            raise
        except Exception as exc:
            raise ScrapingFailedException("Browser scraping failed") from exc
        finally:
            await self._close_browser(browser, context)

    def _build_browser_launch_kwargs(
        self, runtime_config: ShopDashboardRuntimeConfig
    ) -> dict[str, Any]:
        launch_kwargs = {
            "headless": self._settings.browser_headless,
        }
        if runtime_config.proxy:
            launch_kwargs["proxy"] = {"server": runtime_config.proxy}
        return launch_kwargs

    async def _build_browser_context(
        self, browser, storage_state: dict[str, Any] | None
    ) -> Any:
        context_kwargs = self._build_browser_context_kwargs(storage_state)
        context = await browser.new_context(**context_kwargs)
        return context

    def _build_browser_context_kwargs(
        self, storage_state: dict[str, Any] | None
    ) -> dict[str, Any]:
        context_kwargs = {}
        if self._settings.browser_user_agent:
            context_kwargs["user_agent"] = self._settings.browser_user_agent
        if browser_locale := getattr(self._settings, "browser_locale", None):
            context_kwargs["locale"] = browser_locale
        if browser_timezone := getattr(self._settings, "browser_timezone", None):
            context_kwargs["timezone_id"] = browser_timezone
        if browser_viewport := getattr(self._settings, "browser_viewport", None):
            if isinstance(browser_viewport, dict):
                context_kwargs["viewport"] = browser_viewport
        if storage_state:
            context_kwargs["storage_state"] = storage_state
        return context_kwargs

    async def _create_page(
        self, context, runtime_config: ShopDashboardRuntimeConfig, date: str | None
    ) -> Any:
        page = await context.new_page()
        target_url = self._build_target_url(runtime_config, date)
        await page.goto(
            target_url,
            wait_until="domcontentloaded",
            timeout=self._settings.browser_timeout_seconds * 1000,
        )
        await page.wait_for_load_state(
            "networkidle", timeout=self._settings.browser_timeout_seconds * 1000
        )
        if not await check_login_status(page):
            raise ScrapingFailedException("Browser login session expired")
        return page

    async def _close_browser(self, browser, context) -> None:
        if context:
            with suppress(Exception):
                await context.close()
        if browser:
            with suppress(Exception):
                await browser.close()

    def _runtime_cookie_records(
        self, runtime_config: ShopDashboardRuntimeConfig
    ) -> list[dict[str, Any]]:
        hostname = urlparse(self._settings.base_url).hostname or "fxg.jinritemai.com"
        return [
            {
                "name": str(key),
                "value": str(value),
                "domain": hostname,
                "path": "/",
            }
            for key, value in dict(runtime_config.cookies).items()
        ]

    def _build_target_url(
        self, runtime_config: ShopDashboardRuntimeConfig, date: str | None
    ) -> str:
        base = self._settings.browser_refresh_url or self._settings.base_url
        parsed = urlparse(base)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update({str(k): str(v) for k, v in runtime_config.common_query.items()})
        if date:
            query["date"] = date
        return parsed._replace(query=urlencode(query)).geturl()

    async def _extract_cookie_mapping(
        self, context, token_keys: list[str]
    ) -> dict[str, str]:
        cookies = await context.cookies()
        selected_keys = {str(item) for item in token_keys if str(item)}
        return {
            str(cookie["name"]): str(cookie["value"])
            for cookie in cookies
            if str(cookie["name"]) in selected_keys
        }

    @staticmethod
    def _resolve_account_id(runtime_config: ShopDashboardRuntimeConfig) -> str:
        account_id = str(getattr(runtime_config, "account_id", "") or "").strip()
        return account_id if account_id else f"shop_{runtime_config.shop_id}"
