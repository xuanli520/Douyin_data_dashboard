from __future__ import annotations

import json
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from redis.exceptions import ResponseError

from src.config import get_settings
from src.scrapers.shop_dashboard.account_shop_resolver import AccountShopResolver
from src.shared.redis_keys import redis_keys


@dataclass(frozen=True, slots=True)
class AccountShopCatalogResult:
    shop_ids: list[str]
    catalog_stale: bool
    resolve_source: str


class AccountShopCatalogService:
    _RELEASE_SCRIPT = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    else
        return 0
    end
    """

    def __init__(
        self,
        *,
        account_shop_resolver: AccountShopResolver | None = None,
        redis_client: Any | None = None,
        catalog_cache_ttl_seconds: int | None = None,
        catalog_cache_ttl_cap_seconds: int | None = None,
        catalog_stale_allow_seconds: int | None = None,
        catalog_refresh_lock_ttl_seconds: int | None = None,
    ) -> None:
        settings = get_settings().shop_dashboard
        self._resolver = account_shop_resolver or AccountShopResolver()
        self._redis = redis_client
        default_ttl = int(
            catalog_cache_ttl_seconds or settings.catalog_cache_ttl_seconds or 3600
        )
        ttl_cap = int(
            catalog_cache_ttl_cap_seconds
            or settings.catalog_cache_ttl_cap_seconds
            or 7200
        )
        self._catalog_cache_ttl_seconds = max(min(default_ttl, ttl_cap), 1)
        self._catalog_stale_allow_seconds = max(
            int(
                catalog_stale_allow_seconds
                or settings.catalog_stale_allow_seconds
                or self._catalog_cache_ttl_seconds
            ),
            1,
        )
        self._catalog_cache_store_seconds = max(
            self._catalog_cache_ttl_seconds,
            self._catalog_stale_allow_seconds,
        )
        self._catalog_refresh_lock_ttl_seconds = max(
            int(
                catalog_refresh_lock_ttl_seconds
                or settings.catalog_refresh_lock_ttl_seconds
                or 30
            ),
            1,
        )
        self._memory_cache: dict[str, tuple[list[str], int, float]] = {}
        self._memory_locks: dict[str, tuple[str, float]] = {}

    async def get_shop_catalog(
        self,
        *,
        account_id: str,
        cookies: Mapping[str, str] | None,
        common_query: Mapping[str, Any] | None = None,
        extra_config: Mapping[str, Any] | None = None,
        force_refresh: bool = False,
        refresh_login_callback: Callable[[str], Awaitable[bool] | bool] | None = None,
    ) -> AccountShopCatalogResult:
        normalized_account_id = str(account_id or "").strip() or "anonymous"
        catalog_key = redis_keys.shop_dashboard_shop_catalog(
            account_id=normalized_account_id
        )
        refresh_lock_key = redis_keys.shop_dashboard_shop_catalog_refresh_lock(
            account_id=normalized_account_id
        )
        cached_shop_ids = (
            []
            if force_refresh
            else self._load_catalog_cache(catalog_key, allow_stale=False)
        )
        if cached_shop_ids and not force_refresh:
            return AccountShopCatalogResult(
                shop_ids=list(cached_shop_ids),
                catalog_stale=False,
                resolve_source="cache",
            )

        token = self._acquire_lock(refresh_lock_key)
        if not token:
            fallback_cached_shop_ids = cached_shop_ids or self._load_catalog_cache(
                catalog_key,
                allow_stale=True,
            )
            if fallback_cached_shop_ids:
                return AccountShopCatalogResult(
                    shop_ids=list(fallback_cached_shop_ids),
                    catalog_stale=True,
                    resolve_source="cache_stale",
                )
            shop_ids = await self._resolver.resolve_shop_ids(
                account_id=normalized_account_id,
                cookies=cookies,
                common_query=common_query,
                extra_config=extra_config,
                refresh_login_callback=refresh_login_callback,
            )
            shop_ids = _normalize_shop_ids(shop_ids)
            if shop_ids:
                self._save_catalog_cache(catalog_key, shop_ids)
            return AccountShopCatalogResult(
                shop_ids=shop_ids,
                catalog_stale=False,
                resolve_source="live",
            )

        try:
            if not force_refresh:
                cached_shop_ids = self._load_catalog_cache(
                    catalog_key,
                    allow_stale=False,
                )
                if cached_shop_ids:
                    return AccountShopCatalogResult(
                        shop_ids=list(cached_shop_ids),
                        catalog_stale=False,
                        resolve_source="cache",
                    )
            shop_ids = await self._resolver.resolve_shop_ids(
                account_id=normalized_account_id,
                cookies=cookies,
                common_query=common_query,
                extra_config=extra_config,
                refresh_login_callback=refresh_login_callback,
            )
            shop_ids = _normalize_shop_ids(shop_ids)
            if shop_ids:
                self._save_catalog_cache(catalog_key, shop_ids)
                return AccountShopCatalogResult(
                    shop_ids=shop_ids,
                    catalog_stale=False,
                    resolve_source="live",
                )
            fallback_cached_shop_ids = cached_shop_ids or self._load_catalog_cache(
                catalog_key,
                allow_stale=True,
            )
            if fallback_cached_shop_ids:
                return AccountShopCatalogResult(
                    shop_ids=list(fallback_cached_shop_ids),
                    catalog_stale=True,
                    resolve_source="cache_stale",
                )
            return AccountShopCatalogResult(
                shop_ids=[],
                catalog_stale=False,
                resolve_source="live",
            )
        except Exception:
            fallback_cached_shop_ids = cached_shop_ids or self._load_catalog_cache(
                catalog_key,
                allow_stale=True,
            )
            if fallback_cached_shop_ids:
                return AccountShopCatalogResult(
                    shop_ids=list(fallback_cached_shop_ids),
                    catalog_stale=True,
                    resolve_source="cache_stale",
                )
            raise
        finally:
            self._release_lock(refresh_lock_key, token)

    def _save_catalog_cache(self, key: str, shop_ids: list[str]) -> None:
        payload = json.dumps(
            {
                "shop_ids": list(shop_ids),
                "updated_at": int(time.time()),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        redis_set = getattr(self._redis, "set", None)
        if callable(redis_set):
            redis_set(
                key,
                payload,
                ex=self._catalog_cache_store_seconds,
            )
            return
        now = time.time()
        self._memory_cache[key] = (
            list(shop_ids),
            int(now),
            now + self._catalog_cache_store_seconds,
        )

    def _load_catalog_cache(self, key: str, *, allow_stale: bool) -> list[str]:
        redis_get = getattr(self._redis, "get", None)
        raw: Any = None
        if callable(redis_get):
            raw = redis_get(key)
        else:
            cached = self._memory_cache.get(key)
            if cached is None:
                return []
            shop_ids, updated_at, expires_at = cached
            if expires_at <= time.time():
                self._memory_cache.pop(key, None)
                return []
            if self._is_cache_usable(updated_at=updated_at, allow_stale=allow_stale):
                return _normalize_shop_ids(shop_ids)
            return []
        if raw is None:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        if not isinstance(raw, str):
            return []
        text = raw.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except ValueError:
            return []
        if not isinstance(payload, dict):
            return []
        shop_ids = _normalize_shop_ids(payload.get("shop_ids"))
        if not shop_ids:
            return []
        updated_at_raw = payload.get("updated_at")
        try:
            updated_at = int(updated_at_raw)
        except (TypeError, ValueError):
            return shop_ids
        if self._is_cache_usable(updated_at=updated_at, allow_stale=allow_stale):
            return shop_ids
        return []

    def _is_cache_usable(self, *, updated_at: int, allow_stale: bool) -> bool:
        now = int(time.time())
        age_seconds = max(now - int(updated_at), 0)
        if age_seconds <= self._catalog_cache_ttl_seconds:
            return True
        if allow_stale and age_seconds <= self._catalog_stale_allow_seconds:
            return True
        return False

    def _acquire_lock(self, key: str) -> str | None:
        token = os.urandom(16).hex()
        redis_set = getattr(self._redis, "set", None)
        if callable(redis_set):
            acquired = redis_set(
                key,
                token,
                nx=True,
                ex=self._catalog_refresh_lock_ttl_seconds,
            )
            if acquired:
                return token
            return None
        cached = self._memory_locks.get(key)
        now = time.time()
        if cached is not None and cached[1] > now:
            return None
        self._memory_locks[key] = (
            token,
            now + self._catalog_refresh_lock_ttl_seconds,
        )
        return token

    def _release_lock(self, key: str, token: str | None) -> None:
        if not token:
            return
        redis_eval = getattr(self._redis, "eval", None)
        if callable(redis_eval):
            try:
                redis_eval(self._RELEASE_SCRIPT, 1, key, token)
                return
            except ResponseError as exc:
                message = str(exc).lower()
                if "unknown command" not in message or "eval" not in message:
                    raise
        redis_get = getattr(self._redis, "get", None)
        redis_delete = getattr(self._redis, "delete", None)
        if callable(redis_get) and callable(redis_delete):
            if redis_get(key) == token:
                redis_delete(key)
            return
        current = self._memory_locks.get(key)
        if current is not None and current[0] == token:
            self._memory_locks.pop(key, None)


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
