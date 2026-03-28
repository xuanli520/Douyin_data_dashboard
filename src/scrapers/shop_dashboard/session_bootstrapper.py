from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any

import httpx

from src.config import get_settings
from src.scrapers.shop_dashboard.http_scraper import ENDPOINT_SPECS
from src.scrapers.shop_dashboard.http_scraper import SHOP_CONTEXT_VERIFY_GROUPS
from src.scrapers.shop_dashboard.parsers import (
    extract_actual_shop_id_from_group_payloads,
)
from src.scrapers.shop_dashboard.query_builder import build_endpoint_request_payload
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.session_state_store import SessionStateStore


@dataclass(frozen=True, slots=True)
class _RequestResult:
    success: bool
    error_code: str
    error_message: str
    http_status: int | None = None
    payload_code: str = ""
    payload: dict[str, Any] | None = None
    response_cookies: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class _VerifyResult:
    success: bool
    error_code: str
    error_message: str
    actual_shop_id: str = ""


@dataclass(frozen=True, slots=True)
class _ChooseResult:
    success: bool
    error_code: str
    error_message: str
    cookies: dict[str, str] | None = None


class SessionBootstrapper:
    _PRIMARY_CHOOSE_SHOP_PATH = "/byteshop/loginv2/chooseshop"
    _FALLBACK_CHOOSE_SHOP_PATH = "/byteshop/index/chooseshop"

    def __init__(
        self,
        *,
        state_store: SessionStateStore,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings().shop_dashboard
        self._settings = settings
        self._state_store = state_store
        self._base_url = str(base_url or settings.base_url).rstrip("/")
        self._timeout_seconds = float(timeout_seconds or 8.0)

    async def bootstrap_shops(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        shop_ids: list[str],
        verify_metric_date_by_shop: Mapping[str, str] | None = None,
        force_serial: bool | None = None,
    ) -> dict[str, dict[str, Any]]:
        normalized_shop_ids = _normalize_shop_ids(shop_ids)
        if not normalized_shop_ids:
            return {}
        verify_dates = {
            str(key): str(value)
            for key, value in dict(verify_metric_date_by_shop or {}).items()
            if str(key).strip() and str(value).strip()
        }
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
                        await self.bootstrap_shop(
                            runtime=runtime,
                            shop_id=shop_id,
                            verify_metric_date=verify_dates.get(shop_id),
                        )
                    )
            else:
                semaphore = asyncio.Semaphore(max_parallel)

                async def _run(shop_id: str) -> dict[str, Any]:
                    async with semaphore:
                        return await self.bootstrap_shop(
                            runtime=runtime,
                            shop_id=shop_id,
                            verify_metric_date=verify_dates.get(shop_id),
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
        verify_metric_date: str | None = None,
    ) -> dict[str, Any]:
        target_shop_id = str(shop_id or "").strip()
        if not target_shop_id:
            return {
                "shop_id": "",
                "target_shop_id": "",
                "bootstrap_failed": True,
                "status": "failed",
                "error": "empty_shop_id",
                "error_code": "verify_request_failed",
                "bootstrap_choose_status": "failed",
                "bootstrap_verify_status": "failed",
                "bootstrap_verify_actual_shop_id": "",
                "bootstrap_verify_error_code": "verify_request_failed",
            }

        metric_date = _resolve_metric_date(verify_metric_date)
        account_id = _resolve_storage_account_id(runtime, target_shop_id)
        expected_session_version = (
            str(self._settings.bootstrap_bundle_session_version).strip() or "1"
        )

        existing_bundle = self._state_store.load_bundle(account_id, target_shop_id)
        if _is_bundle_for_target(
            existing_bundle,
            target_shop_id,
            expected_session_version,
        ):
            return {
                "shop_id": target_shop_id,
                "target_shop_id": target_shop_id,
                "bootstrap_failed": False,
                "status": "cached",
                "actual_shop_id": target_shop_id,
                "bootstrap_choose_status": "cached",
                "bootstrap_verify_status": "passed",
                "bootstrap_verify_actual_shop_id": target_shop_id,
                "bootstrap_verify_error_code": "",
            }
        if existing_bundle:
            self._state_store.invalidate_bundle(account_id, target_shop_id)

        unit_runtime = _with_target_shop_query(
            replace(runtime, shop_id=target_shop_id),
            target_shop_id,
        )
        choose_result = await self._choose_shop(unit_runtime, target_shop_id)
        if not choose_result.success:
            self._state_store.invalidate_bundle(account_id, target_shop_id)
            verify_error_code = _map_verify_error_code(choose_result.error_code)
            return {
                "shop_id": target_shop_id,
                "target_shop_id": target_shop_id,
                "bootstrap_failed": True,
                "status": "failed",
                "error": choose_result.error_message,
                "error_code": verify_error_code,
                "bootstrap_choose_status": "failed",
                "bootstrap_verify_status": "skipped",
                "bootstrap_verify_actual_shop_id": "",
                "bootstrap_verify_error_code": verify_error_code,
            }
        if isinstance(choose_result.cookies, dict) and choose_result.cookies:
            unit_runtime = replace(
                unit_runtime,
                cookies={
                    **dict(unit_runtime.cookies or {}),
                    **choose_result.cookies,
                },
            )

        verify_result = await self._verify_shop_context(
            runtime=unit_runtime,
            target_shop_id=target_shop_id,
            verify_metric_date=metric_date,
        )
        if not verify_result.success:
            self._state_store.invalidate_bundle(account_id, target_shop_id)
            response: dict[str, Any] = {
                "shop_id": target_shop_id,
                "target_shop_id": target_shop_id,
                "bootstrap_failed": True,
                "status": "failed",
                "error": verify_result.error_message,
                "error_code": verify_result.error_code,
                "bootstrap_choose_status": "passed",
                "bootstrap_verify_status": "failed",
                "bootstrap_verify_actual_shop_id": verify_result.actual_shop_id,
                "bootstrap_verify_error_code": verify_result.error_code,
            }
            if verify_result.actual_shop_id:
                response["actual_shop_id"] = verify_result.actual_shop_id
            return response

        verified_at = datetime.now(UTC).isoformat()
        bundle = {
            "cookies": dict(unit_runtime.cookies),
            "common_query": dict(unit_runtime.common_query),
            "validated_shop_id": target_shop_id,
            "verified_actual_shop_id": verify_result.actual_shop_id,
            "verify_status": "passed",
            "verified_at": verified_at,
            "session_version": expected_session_version,
        }
        self._state_store.save_bundle(account_id, target_shop_id, bundle)
        return {
            "shop_id": target_shop_id,
            "target_shop_id": target_shop_id,
            "bootstrap_failed": False,
            "status": "success",
            "actual_shop_id": verify_result.actual_shop_id,
            "bootstrap_choose_status": "passed",
            "bootstrap_verify_status": "passed",
            "bootstrap_verify_actual_shop_id": verify_result.actual_shop_id,
            "bootstrap_verify_error_code": "",
        }

    async def _verify_shop_context(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        target_shop_id: str,
        verify_metric_date: str,
    ) -> _VerifyResult:
        timeout_seconds = max(
            float(self._settings.bootstrap_verify_timeout_seconds),
            0.1,
        )
        retry_limit = max(int(self._settings.bootstrap_verify_retry_limit), 0)
        base_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }
        working_cookies = dict(runtime.cookies or {})
        attempts = retry_limit + 1
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout_seconds,
            http2=True,
        ) as client:
            for attempt in range(attempts):
                payloads: dict[str, dict[str, Any]] = {}
                request_failed_result: _RequestResult | None = None
                for group_name in SHOP_CONTEXT_VERIFY_GROUPS:
                    spec = ENDPOINT_SPECS[group_name]
                    request_payload = build_endpoint_request_payload(
                        runtime,
                        metric_date=verify_metric_date,
                        group_name=group_name,
                        base_params=spec.params,
                        base_json_body=spec.json_body,
                        requires_graphql_query=spec.requires_graphql_query,
                        graphql_query=runtime.graphql_query,
                    )
                    if (
                        spec.requires_graphql_query
                        and request_payload.json_body is None
                    ):
                        request_failed_result = _RequestResult(
                            success=False,
                            error_code="request_failed",
                            error_message="graphql_query_missing",
                        )
                        break
                    request_params = dict(runtime.common_query or {})
                    if request_payload.params:
                        request_params.update(request_payload.params)
                    request_headers = dict(base_headers)
                    request_headers["Cookie"] = _build_cookie_header(working_cookies)
                    request_result = await self._request_json(
                        client=client,
                        method=spec.method,
                        path=spec.path,
                        params=request_params,
                        headers=request_headers,
                        json_body=request_payload.json_body,
                    )
                    if request_result.response_cookies:
                        working_cookies.update(request_result.response_cookies)
                    if not request_result.success:
                        if request_result.error_code == "login_expired":
                            return _VerifyResult(
                                success=False,
                                error_code="verify_login_expired",
                                error_message=request_result.error_message
                                or "login_expired",
                            )
                        request_failed_result = request_result
                        break
                    payloads[group_name] = dict(request_result.payload or {})
                if request_failed_result is not None:
                    should_retry = attempt < attempts - 1
                    if should_retry:
                        continue
                    return _VerifyResult(
                        success=False,
                        error_code="verify_request_failed",
                        error_message=(
                            request_failed_result.error_message
                            or "verify_request_failed"
                        ),
                    )

                actual_shop_id = str(
                    extract_actual_shop_id_from_group_payloads(payloads) or ""
                ).strip()
                if not actual_shop_id:
                    should_retry = attempt < attempts - 1
                    if should_retry:
                        continue
                    return _VerifyResult(
                        success=False,
                        error_code="verify_request_failed",
                        error_message="actual_shop_id_missing",
                    )
                if actual_shop_id != target_shop_id:
                    return _VerifyResult(
                        success=False,
                        error_code="verify_shop_mismatch",
                        error_message=(
                            f"verify_shop_mismatch: target={target_shop_id},"
                            f" actual={actual_shop_id}"
                        ),
                        actual_shop_id=actual_shop_id,
                    )
                return _VerifyResult(
                    success=True,
                    error_code="",
                    error_message="",
                    actual_shop_id=actual_shop_id,
                )
        return _VerifyResult(
            success=False,
            error_code="verify_request_failed",
            error_message="verify_request_failed",
        )

    async def _choose_shop(
        self,
        runtime: ShopDashboardRuntimeConfig,
        target_shop_id: str,
    ) -> _ChooseResult:
        params = _build_choose_shop_params(
            common_query=runtime.common_query,
            target_shop_id=target_shop_id,
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }
        timeout_seconds = max(self._timeout_seconds, 0.1)
        working_cookies = dict(runtime.cookies or {})
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout_seconds,
            http2=True,
        ) as client:
            login_expired_failure: _RequestResult | None = None
            latest_failure = _RequestResult(
                success=False,
                error_code="request_failed",
                error_message="choose_shop_failed",
            )
            for path in (
                self._PRIMARY_CHOOSE_SHOP_PATH,
                self._FALLBACK_CHOOSE_SHOP_PATH,
            ):
                for method in ("GET", "POST"):
                    request_headers = dict(headers)
                    request_headers["Cookie"] = _build_cookie_header(working_cookies)
                    request_result = await self._request_json(
                        client=client,
                        method=method,
                        path=path,
                        params=params,
                        headers=request_headers,
                        json_body={},
                    )
                    if request_result.response_cookies:
                        working_cookies.update(request_result.response_cookies)
                    if request_result.success:
                        return _ChooseResult(
                            success=True,
                            error_code="",
                            error_message="",
                            cookies=dict(working_cookies),
                        )
                    latest_failure = request_result
                    if request_result.error_code == "login_expired":
                        login_expired_failure = request_result
                        continue
            if login_expired_failure is not None:
                return _ChooseResult(
                    success=False,
                    error_code="login_expired",
                    error_message=login_expired_failure.error_message
                    or "login_expired",
                    cookies=dict(working_cookies),
                )
            return _ChooseResult(
                success=False,
                error_code=latest_failure.error_code or "request_failed",
                error_message=latest_failure.error_message or "choose_shop_failed",
                cookies=dict(working_cookies),
            )

    async def _request_json(
        self,
        *,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
        json_body: Mapping[str, Any] | None = None,
    ) -> _RequestResult:
        try:
            request_method = method.upper()
            if request_method == "POST":
                response = await client.post(
                    path,
                    params=params,
                    headers=headers,
                    json=dict(json_body or {}),
                )
            else:
                response = await client.get(path, params=params, headers=headers)
        except httpx.TimeoutException:
            return _RequestResult(
                success=False,
                error_code="request_failed",
                error_message=f"request_timeout:{method}:{path}",
            )
        except Exception as exc:
            return _RequestResult(
                success=False,
                error_code="request_failed",
                error_message=str(exc).strip() or f"request_failed:{method}:{path}",
            )

        status_code = int(response.status_code)
        response_cookies = _extract_response_cookie_mapping(response)
        if status_code in {401, 403}:
            return _RequestResult(
                success=False,
                error_code="login_expired",
                error_message=f"http_{status_code}",
                http_status=status_code,
                response_cookies=response_cookies,
            )
        if status_code >= 400:
            return _RequestResult(
                success=False,
                error_code="request_failed",
                error_message=f"http_{status_code}",
                http_status=status_code,
                response_cookies=response_cookies,
            )
        try:
            payload = response.json()
        except ValueError:
            return _RequestResult(
                success=False,
                error_code="request_failed",
                error_message="invalid_json",
                http_status=status_code,
                response_cookies=response_cookies,
            )
        if not isinstance(payload, dict):
            return _RequestResult(
                success=False,
                error_code="request_failed",
                error_message="invalid_payload_type",
                http_status=status_code,
                response_cookies=response_cookies,
            )

        payload_code = _extract_payload_code(payload)
        if payload_code in {"0", "200", ""}:
            return _RequestResult(
                success=True,
                error_code="",
                error_message="",
                http_status=status_code,
                payload_code=payload_code,
                payload=dict(payload),
                response_cookies=response_cookies,
            )
        if payload_code in {"401", "403", "10008"}:
            return _RequestResult(
                success=False,
                error_code="login_expired",
                error_message=f"payload_code_{payload_code}",
                http_status=status_code,
                payload_code=payload_code,
                payload=dict(payload),
                response_cookies=response_cookies,
            )
        return _RequestResult(
            success=False,
            error_code="request_failed",
            error_message=f"payload_code_{payload_code}",
            http_status=status_code,
            payload_code=payload_code,
            payload=dict(payload),
            response_cookies=response_cookies,
        )


def _resolve_storage_account_id(
    runtime: ShopDashboardRuntimeConfig,
    shop_id: str,
) -> str:
    account_id = str(getattr(runtime, "account_id", "") or "").strip()
    if account_id:
        return account_id
    rule_id = int(getattr(runtime, "rule_id", 0) or 0)
    if rule_id > 0:
        return f"rule_{rule_id}"
    normalized_shop_id = str(shop_id).strip()
    if normalized_shop_id:
        return f"shop_{normalized_shop_id}"
    return "shop_anonymous"


def _resolve_metric_date(value: str | None) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return date.today().isoformat()


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


def _extract_payload_code(payload: Mapping[str, Any]) -> str:
    code = payload.get("code")
    if code is None:
        code = payload.get("status_code")
    if code is None:
        code = payload.get("errno")
    return str(code).strip() if code is not None else ""


def _map_verify_error_code(error_code: str) -> str:
    if error_code == "login_expired":
        return "verify_login_expired"
    return "verify_request_failed"


def _build_cookie_header(cookies: Mapping[str, Any]) -> str:
    cookie_items = []
    for key, value in dict(cookies or {}).items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if not key_text or not value_text:
            continue
        cookie_items.append(f"{key_text}={value_text}")
    return "; ".join(cookie_items)


def _extract_response_cookie_mapping(response: Any) -> dict[str, str]:
    cookies_container = getattr(response, "cookies", None)
    if cookies_container is None:
        return {}
    cookie_items = getattr(cookies_container, "items", None)
    if not callable(cookie_items):
        return {}
    result: dict[str, str] = {}
    for key, value in cookie_items():
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if not key_text or not value_text:
            continue
        result[key_text] = value_text
    return result


def _build_choose_shop_params(
    *,
    common_query: Mapping[str, Any] | None,
    target_shop_id: str,
) -> dict[str, Any]:
    params = dict(common_query or {})
    params["shop_id"] = target_shop_id
    params["subject_id"] = target_shop_id
    return params


def _with_target_shop_query(
    runtime: ShopDashboardRuntimeConfig,
    target_shop_id: str,
) -> ShopDashboardRuntimeConfig:
    merged_query = dict(runtime.common_query or {})
    merged_query["shop_id"] = target_shop_id
    merged_query["subject_id"] = target_shop_id
    return replace(
        runtime,
        cookies=dict(runtime.cookies or {}),
        common_query=merged_query,
    )


def _is_bundle_for_target(
    bundle: dict[str, Any] | None,
    target_shop_id: str,
    expected_session_version: str,
) -> bool:
    if not isinstance(bundle, dict):
        return False
    cookies = bundle.get("cookies")
    if not isinstance(cookies, dict) or not cookies:
        return False
    common_query = bundle.get("common_query")
    if not isinstance(common_query, dict):
        return False
    session_version = str(bundle.get("session_version") or "").strip()
    if session_version != expected_session_version:
        return False
    verify_status = str(bundle.get("verify_status") or "").strip().lower()
    if verify_status != "passed":
        return False
    normalized_target_shop_id = str(target_shop_id or "").strip()
    verified_actual_shop_id = str(bundle.get("verified_actual_shop_id") or "").strip()
    if verified_actual_shop_id != normalized_target_shop_id:
        return False
    validated_shop_id = str(bundle.get("validated_shop_id") or "").strip()
    if validated_shop_id and validated_shop_id != normalized_target_shop_id:
        return False
    return True
