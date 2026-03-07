from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from redis import Redis
from redis.exceptions import ResponseError

from src.config import get_settings
from src.domains.data_source.models import DataSource
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


class CookieManager:
    _RELEASE_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    else
        return 0
    end
    """

    def __init__(
        self,
        redis_client: Redis | Any | None = None,
        ttl_seconds: int | None = None,
        lock_ttl_seconds: int | None = None,
        lock_wait_seconds: float | None = None,
        lock_retry_interval_seconds: float | None = None,
        key_prefix: str = "douyin:shop_dashboard:cookie",
    ) -> None:
        settings = get_settings()
        self._ttl_seconds = int(
            ttl_seconds or settings.shop_dashboard.cookie_ttl_seconds
        )
        self._lock_ttl_seconds = int(
            lock_ttl_seconds or settings.shop_dashboard.lock_ttl_seconds
        )
        self._lock_wait_seconds = float(
            lock_wait_seconds or settings.shop_dashboard.browser_lock_wait_seconds
        )
        self._lock_retry_interval_seconds = float(
            lock_retry_interval_seconds
            or settings.shop_dashboard.browser_lock_retry_interval_seconds
        )
        self._key_prefix = key_prefix
        self._redis = redis_client or Redis(
            host=settings.cache.host,
            port=settings.cache.port,
            db=settings.cache.db,
            password=settings.cache.password,
            encoding=settings.cache.encoding,
            decode_responses=True,
            socket_timeout=settings.cache.socket_timeout,
            socket_connect_timeout=settings.cache.socket_connect_timeout,
            retry_on_timeout=settings.cache.retry_on_timeout,
        )

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
        merged.update(self._normalize_cookie_mapping(refreshed))
        runtime_config.cookies = merged
        return runtime_config

    async def get(
        self,
        shop_id: str,
        fallback: Mapping[str, Any] | str | None = None,
        refresher: Callable[[], Awaitable[Mapping[str, Any] | str | None]]
        | Callable[[], Mapping[str, Any] | str | None]
        | None = None,
    ) -> dict[str, str]:
        fallback_cookie = self._normalize_cookie_mapping(fallback)
        if refresher is None:
            return fallback_cookie

        deadline = time.monotonic() + self._lock_wait_seconds
        while True:
            lock_token = self._acquire_refresh_lock(shop_id)
            if lock_token:
                try:
                    refreshed = refresher()
                    if asyncio.iscoroutine(refreshed):
                        refreshed = await refreshed
                    refreshed_cookie = self._normalize_cookie_mapping(refreshed)
                    return refreshed_cookie or fallback_cookie
                finally:
                    self._release_refresh_lock(shop_id, lock_token)

            if time.monotonic() >= deadline:
                return fallback_cookie

            await asyncio.sleep(self._lock_retry_interval_seconds)

    def get_cached(self, shop_id: str) -> dict[str, str]:
        _ = shop_id
        return {}

    def set(self, shop_id: str, cookies: Mapping[str, Any] | str) -> dict[str, str]:
        _ = shop_id
        return self._normalize_cookie_mapping(cookies)

    def _cookie_key(self, shop_id: str) -> str:
        return f"{self._key_prefix}:{shop_id}"

    def _lock_key(self, shop_id: str) -> str:
        return f"{self._key_prefix}:lock:{shop_id}"

    def _acquire_refresh_lock(self, shop_id: str) -> str | None:
        token = os.urandom(16).hex()
        key = self._lock_key(shop_id)
        if self._redis.set(key, token, nx=True, ex=self._lock_ttl_seconds):
            return token
        return None

    def _release_refresh_lock(self, shop_id: str, token: str) -> None:
        key = self._lock_key(shop_id)
        eval_func = getattr(self._redis, "eval", None)
        if callable(eval_func):
            try:
                eval_func(self._RELEASE_SCRIPT, 1, key, token)
                return
            except ResponseError as exc:
                message = str(exc).lower()
                if "unknown command" not in message or "eval" not in message:
                    raise

        current = self._redis.get(key)
        if current == token:
            self._redis.delete(key)

    @classmethod
    def _normalize_cookie_mapping(
        cls, value: Mapping[str, Any] | str | Any | None
    ) -> dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, str):
            return cls._parse_cookie_string(value)

        if isinstance(value, Mapping):
            cookie_payload: Any = value.get("cookies", value)
            if isinstance(cookie_payload, str):
                return cls._parse_cookie_string(cookie_payload)
            if isinstance(cookie_payload, Mapping):
                normalized: dict[str, str] = {}
                for key, val in cookie_payload.items():
                    if val is None:
                        continue
                    if key == "_refreshed_at":
                        continue
                    normalized[str(key)] = str(val)
                return normalized
        return {}

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
