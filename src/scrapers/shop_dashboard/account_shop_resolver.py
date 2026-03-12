from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

import httpx


class AccountShopResolver:
    _LOGIN_PROBE_PATH = "/ecomauth/loginv1/get_login_subject_count"
    _LOGIN_PROBE_PARAMS: dict[str, Any] = {"login_source": "doudian_pc_web"}
    _SHOP_LIST_SPECS: tuple[tuple[str, dict[str, Any]], ...] = (
        ("/byteshop/index/getshoplist", {}),
        (
            "/byteshop/loginv2/getallshop",
            {
                "loginSourceV2": "doudian_pc_v2",
                "subject_aid": 4966,
                "loginType": "mobile",
            },
        ),
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
        refresh_login_callback: Any | None = None,
    ) -> list[str]:
        _ = extra_config
        cookie_mapping = dict(cookies or {})
        if not cookie_mapping:
            return []

        params = dict(common_query or {})

        if self._client is not None:
            resolved_shop_ids = await self._resolve_with_client(
                client=self._client,
                account_id=account_id,
                params=params,
                cookies=cookie_mapping,
                refresh_login_callback=refresh_login_callback,
            )
            return resolved_shop_ids

        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            http2=True,
        ) as client:
            resolved_shop_ids = await self._resolve_with_client(
                client=client,
                account_id=account_id,
                params=params,
                cookies=cookie_mapping,
                refresh_login_callback=refresh_login_callback,
            )
            return resolved_shop_ids

    async def _resolve_with_client(
        self,
        *,
        client: httpx.AsyncClient,
        account_id: str,
        params: Mapping[str, Any],
        cookies: Mapping[str, str],
        refresh_login_callback: Any | None = None,
    ) -> list[str]:
        login_ok = await self._probe_login(
            client=client, params=params, cookies=cookies
        )
        if not login_ok and refresh_login_callback is not None:
            refreshed = refresh_login_callback(account_id)
            if inspect.isawaitable(refreshed):
                refreshed = await refreshed
            if bool(refreshed):
                login_ok = await self._probe_login(
                    client=client,
                    params=params,
                    cookies=cookies,
                )
        if not login_ok:
            return []
        for path, endpoint_params in self._SHOP_LIST_SPECS:
            payload = await self._request_json(
                client=client,
                path=path,
                params={**dict(params), **endpoint_params},
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
            params={**dict(params), **self._LOGIN_PROBE_PARAMS},
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
    byteshop_shop_ids = _extract_shop_ids_from_byteshop_payload(payload)
    if byteshop_shop_ids:
        return byteshop_shop_ids
    result: list[str] = []
    _walk_shop_ids(payload, result, parent_key="")
    return _dedupe_shop_ids(result)


def _extract_shop_ids_from_byteshop_payload(payload: Any) -> list[str]:
    if not isinstance(payload, Mapping):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    result: list[str] = []
    for item in data:
        if not isinstance(item, Mapping):
            continue
        for key in ("id", "shop_id", "shopId", "subject_id", "subjectId"):
            result.extend(_normalize_scalar_to_shop_ids(item.get(key)))
    return _dedupe_shop_ids(result)


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
