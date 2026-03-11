from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class AccountShopResolver:
    _LOGIN_PROBE_PATH = "/api/compass/user/info"
    _SHOP_LIST_PATHS: tuple[str, ...] = (
        "/api/compass/shop/get_login_subject",
        "/api/compass/user/get_login_subject",
        "/api/compass/user/get_login_subject_list",
    )

    def __init__(
        self,
        *,
        base_url: str = "https://fxg.jinritemai.com",
        timeout: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = max(float(timeout), 0.1)
        self._client = client

    async def resolve_shop_ids(
        self,
        *,
        account_id: str,
        cookies: Mapping[str, str] | None,
        common_query: Mapping[str, Any] | None = None,
        extra_config: Mapping[str, Any] | None = None,
    ) -> list[str]:
        configured_shop_ids = _resolve_shop_ids_from_extra_config(extra_config)
        cookie_mapping = dict(cookies or {})
        if not cookie_mapping:
            return configured_shop_ids

        params = dict(common_query or {})
        if account_id and "account_id" not in params:
            params["account_id"] = account_id

        if self._client is not None:
            resolved_shop_ids = await self._resolve_with_client(
                client=self._client,
                params=params,
                cookies=cookie_mapping,
            )
            return resolved_shop_ids or configured_shop_ids

        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            http2=True,
        ) as client:
            resolved_shop_ids = await self._resolve_with_client(
                client=client,
                params=params,
                cookies=cookie_mapping,
            )
            return resolved_shop_ids or configured_shop_ids

    async def _resolve_with_client(
        self,
        *,
        client: httpx.AsyncClient,
        params: Mapping[str, Any],
        cookies: Mapping[str, str],
    ) -> list[str]:
        if not await self._probe_login(client=client, params=params, cookies=cookies):
            return []
        for path in self._SHOP_LIST_PATHS:
            payload = await self._request_json(
                client=client,
                path=path,
                params=params,
                cookies=cookies,
            )
            if not isinstance(payload, Mapping):
                continue
            shop_ids = _extract_shop_ids_from_payload(payload)
            if shop_ids:
                return shop_ids
        return []

    async def _probe_login(
        self,
        *,
        client: httpx.AsyncClient,
        params: Mapping[str, Any],
        cookies: Mapping[str, str],
    ) -> bool:
        payload = await self._request_json(
            client=client,
            path=self._LOGIN_PROBE_PATH,
            params=params,
            cookies=cookies,
        )
        if not isinstance(payload, Mapping):
            return False
        code = payload.get("code")
        if code in {0, "0", 200, "200"}:
            return True
        if code in {401, "401", 403, "403", 10008, "10008"}:
            return False
        return bool(payload.get("data"))

    async def _request_json(
        self,
        *,
        client: httpx.AsyncClient,
        path: str,
        params: Mapping[str, Any],
        cookies: Mapping[str, str],
    ) -> dict[str, Any] | None:
        request_headers: dict[str, str] = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }
        cookie_items = [
            f"{str(key).strip()}={str(value).strip()}"
            for key, value in dict(cookies).items()
            if str(key).strip() and value is not None and str(value).strip()
        ]
        if cookie_items:
            request_headers["Cookie"] = "; ".join(cookie_items)
        try:
            response = await client.get(
                path,
                params=dict(params),
                headers=request_headers,
            )
        except Exception:
            return None
        if response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, Mapping):
            return dict(payload)
        return None


def _extract_shop_ids_from_payload(payload: Any) -> list[str]:
    result: list[str] = []
    _walk_shop_ids(payload, result, parent_key="")
    return _dedupe_shop_ids(result)


def _resolve_shop_ids_from_extra_config(
    extra_config: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(extra_config, Mapping):
        return []
    return _extract_shop_ids_from_payload(extra_config)


def _walk_shop_ids(value: Any, result: list[str], *, parent_key: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in {"shop_id", "shopid"}:
                result.extend(_normalize_scalar_to_shop_ids(item))
            elif normalized_key in {
                "shop_ids",
                "shop_list",
                "shoplist",
                "shops",
                "subjects",
                "subject_list",
            }:
                result.extend(_normalize_value_to_shop_ids(item))
            elif normalized_key == "id" and any(
                token in parent_key for token in ("shop", "subject")
            ):
                result.extend(_normalize_scalar_to_shop_ids(item))
            _walk_shop_ids(item, result, parent_key=normalized_key)
        return
    if isinstance(value, list):
        for item in value:
            _walk_shop_ids(item, result, parent_key=parent_key)


def _normalize_value_to_shop_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_normalize_value_to_shop_ids(item))
        return result
    if isinstance(value, Mapping):
        result: list[str] = []
        for key in ("shop_id", "shopId", "id", "value"):
            if key in value:
                result.extend(_normalize_scalar_to_shop_ids(value.get(key)))
        return result
    return _normalize_scalar_to_shop_ids(value)


def _normalize_scalar_to_shop_ids(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    if text.lower() in {"all", "*"}:
        return []
    return [text]


def _dedupe_shop_ids(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
