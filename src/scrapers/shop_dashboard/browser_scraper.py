from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
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
        if state_store is not None:
            self._state_store = state_store
        else:
            target_dir = (
                Path(state_dir)
                if state_dir is not None
                else Path(".runtime") / "shop_dashboard_state"
            )
            self._state_store = SessionStateStore(base_dir=target_dir)

    async def refresh_runtime_context(
        self,
        runtime_config: ShopDashboardRuntimeConfig,
    ) -> ShopDashboardRuntimeConfig:
        refreshed = await self._refresh_payload(runtime_config)
        refreshed_query = dict(refreshed.get("common_query") or {})
        refreshed_cookies = {
            str(k): str(v) for k, v in dict(refreshed.get("cookies") or {}).items()
        }

        account_id = self._resolve_account_id(runtime_config)
        storage_state = refreshed.get("storage_state")
        if isinstance(storage_state, dict):
            self._state_store.save(account_id, storage_state)

        if refreshed_cookies:
            runtime_config.cookies = refreshed_cookies
        else:
            state_cookies = self._state_store.load_cookie_mapping(account_id)
            if state_cookies:
                runtime_config.cookies = state_cookies

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
        account_id = self._resolve_account_id(runtime_config)
        storage_state = self._state_store.load(account_id)
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
                browser_locale = getattr(self._settings, "browser_locale", None)
                browser_timezone = getattr(self._settings, "browser_timezone", None)
                browser_viewport = getattr(self._settings, "browser_viewport", None)
                if browser_locale:
                    context_kwargs["locale"] = browser_locale
                if browser_timezone:
                    context_kwargs["timezone_id"] = browser_timezone
                if isinstance(browser_viewport, dict):
                    context_kwargs["viewport"] = browser_viewport
                if storage_state:
                    context_kwargs["storage_state"] = storage_state
                context = await browser.new_context(**context_kwargs)

                if not storage_state:
                    runtime_cookie_records = self._runtime_cookie_records(
                        runtime_config
                    )
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
                if not await check_login_status(page):
                    raise ScrapingFailedException(
                        "Browser login session expired",
                        error_data={"account_id": account_id},
                    )
                page_html = await page.content()
                storage_state = await context.storage_state()
                self._state_store.save(account_id, storage_state)
                cookie_list = await context.cookies()
                cookie_mapping = self._extract_cookie_mapping(
                    cookie_list, runtime_config.token_keys
                )
                if not cookie_mapping:
                    cookie_mapping = self._state_store.load_cookie_mapping(account_id)
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

    @staticmethod
    def _resolve_account_id(runtime_config: ShopDashboardRuntimeConfig) -> str:
        account_id = str(getattr(runtime_config, "account_id", "") or "").strip()
        if account_id:
            return account_id
        return f"shop_{runtime_config.shop_id}"
