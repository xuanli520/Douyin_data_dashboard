from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import httpx

from src.config import get_settings
from src.scrapers.shop_dashboard.browser_scraper import BrowserScraper
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


class SessionBootstrapper:
    _PRIMARY_CHOOSE_SHOP_PATH = "/byteshop/loginv2/chooseshop"
    _FALLBACK_CHOOSE_SHOP_PATH = "/byteshop/index/chooseshop"

    def __init__(
        self,
        *,
        state_store: SessionStateStore,
        browser_scraper: BrowserScraper | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings().shop_dashboard
        self._settings = settings
        self._state_store = state_store
        self._browser_scraper = browser_scraper or BrowserScraper(
            state_store=state_store
        )
        self._base_url = str(base_url or settings.base_url).rstrip("/")
        self._timeout_seconds = float(timeout_seconds or 8.0)

    async def bootstrap_shops(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        shop_ids: list[str],
        force_serial: bool | None = None,
    ) -> dict[str, dict[str, Any]]:
        normalized_shop_ids = _normalize_shop_ids(shop_ids)
        if not normalized_shop_ids:
            return {}
        serial_mode = bool(
            self._settings.bootstrap_force_serial
            if force_serial is None
            else force_serial
        )
        concurrency_limit = max(int(self._settings.bootstrap_concurrency_limit), 1)
        max_parallel = 1 if serial_mode else concurrency_limit
        batch_size = max_parallel
        results: dict[str, dict[str, Any]] = {}
        attempted = 0
        failed = 0
        index = 0
        while index < len(normalized_shop_ids):
            batch = normalized_shop_ids[index : index + batch_size]
            if max_parallel <= 1:
                batch_results: list[dict[str, Any]] = []
                for shop_id in batch:
                    batch_results.append(
                        await self.bootstrap_shop(runtime=runtime, shop_id=shop_id)
                    )
            else:
                semaphore = asyncio.Semaphore(max_parallel)

                async def _run(shop_id: str) -> dict[str, Any]:
                    async with semaphore:
                        return await self.bootstrap_shop(
                            runtime=runtime, shop_id=shop_id
                        )

                batch_results = await asyncio.gather(
                    *[_run(shop_id) for shop_id in batch],
                    return_exceptions=False,
                )
            for item in batch_results:
                shop_id = str(item.get("shop_id") or "").strip()
                if not shop_id:
                    continue
                results[shop_id] = item
                attempted += 1
                if bool(item.get("bootstrap_failed")):
                    failed += 1
            index += len(batch)
            if max_parallel > 1 and attempted > 0:
                failed_rate = failed / attempted
                if failed_rate >= float(
                    self._settings.bootstrap_failure_rate_degrade_threshold
                ):
                    max_parallel = 1
                    batch_size = 1
        return results

    async def bootstrap_shop(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        shop_id: str,
    ) -> dict[str, Any]:
        target_shop_id = str(shop_id or "").strip()
        if not target_shop_id:
            return {
                "shop_id": "",
                "bootstrap_failed": True,
                "status": "failed",
                "error": "empty_shop_id",
            }
        account_id = _resolve_account_id(runtime, target_shop_id)
        existing_bundle = self._state_store.load_bundle(account_id, target_shop_id)
        if existing_bundle and existing_bundle.get("cookies"):
            return {
                "shop_id": target_shop_id,
                "bootstrap_failed": False,
                "status": "cached",
            }
        unit_runtime = replace(runtime, shop_id=target_shop_id)
        try:
            chosen = await self._choose_shop(unit_runtime, target_shop_id)
            if not chosen:
                raise RuntimeError("choose_shop_failed")
            refreshed_runtime = await self._browser_scraper.refresh_runtime_context(
                unit_runtime
            )
            bundle = {
                "cookies": dict(refreshed_runtime.cookies),
                "common_query": dict(refreshed_runtime.common_query),
                "validated_shop_id": target_shop_id,
                "validated_at": datetime.now(timezone.utc).isoformat(),
                "session_version": "1",
            }
            self._state_store.save_bundle(account_id, target_shop_id, bundle)
            return {
                "shop_id": target_shop_id,
                "bootstrap_failed": False,
                "status": "success",
            }
        except Exception as exc:
            return {
                "shop_id": target_shop_id,
                "bootstrap_failed": True,
                "status": "failed",
                "error": str(exc),
            }

    async def _choose_shop(
        self,
        runtime: ShopDashboardRuntimeConfig,
        target_shop_id: str,
    ) -> bool:
        params = dict(runtime.common_query or {})
        params["shop_id"] = target_shop_id
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Cookie": _build_cookie_header(runtime.cookies),
        }
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=max(self._timeout_seconds, 0.1),
            http2=True,
        ) as client:
            primary_payload = await self._request_json(
                client=client,
                path=self._PRIMARY_CHOOSE_SHOP_PATH,
                params=params,
                headers=headers,
            )
            if _is_success_payload(primary_payload):
                return True
            fallback_payload = await self._request_json(
                client=client,
                path=self._FALLBACK_CHOOSE_SHOP_PATH,
                params=params,
                headers=headers,
            )
            return _is_success_payload(fallback_payload)

    async def _request_json(
        self,
        *,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any] | None:
        try:
            response = await client.get(path, params=params, headers=headers)
        except Exception:
            return None
        if response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict):
            return payload
        return None


def _resolve_account_id(runtime: ShopDashboardRuntimeConfig, shop_id: str) -> str:
    account_id = str(getattr(runtime, "account_id", "") or "").strip()
    if account_id:
        return account_id
    normalized_shop_id = str(shop_id).strip()
    if normalized_shop_id:
        return f"shop_{normalized_shop_id}"
    return "shop_anonymous"


def _normalize_shop_ids(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _is_success_payload(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("code")
    if code in {0, "0", 200, "200"}:
        return True
    return False


def _build_cookie_header(cookies: dict[str, str]) -> str:
    cookie_items = []
    for key, value in dict(cookies or {}).items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if not key_text or not value_text:
            continue
        cookie_items.append(f"{key_text}={value_text}")
    return "; ".join(cookie_items)
