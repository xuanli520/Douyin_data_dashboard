from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from src.scrapers.shop_dashboard.parsers import (
    ensure_payload_success,
    extract_actual_shop_id,
    extract_shop_name,
    parse_comment_details,
    parse_comment_summary,
    parse_core_scores,
    parse_violation_details,
    parse_violation_summary,
)
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError
from src.scrapers.shop_dashboard.query_builder import (
    build_endpoint_request_payload,
)
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    method: str
    path: str
    params: Mapping[str, Any] | None = None
    json_body: Mapping[str, Any] | None = None
    requires_graphql_query: bool = False


ENDPOINT_GROUP_ORDER: tuple[str, ...] = (
    "overview",
    "analysis",
    "diagnosis",
    "graphql",
    "statistics",
    "comment_list",
    "unreply",
    "tags",
    "products",
    "cash_info",
    "score_node",
    "ticket_count",
    "enum_config",
    "waiting_list",
    "top_rule",
    "high_frequency",
)

CORE_REQUIRED_GROUPS: frozenset[str] = frozenset({"overview", "analysis"})
SHOP_CONTEXT_VERIFY_GROUPS: tuple[str, ...] = ("overview", "analysis")


ENDPOINT_SPECS: dict[str, EndpointSpec] = {
    "overview": EndpointSpec(
        method="GET",
        path="/governance/shop/experiencescore/getOverviewByVersion",
        params={
            "exp_version": "release",
            "new_shop_version": "release",
            "source": 1,
        },
    ),
    "analysis": EndpointSpec(
        method="GET",
        path="/governance/shop/experiencescore/getAnalysisScore",
    ),
    "diagnosis": EndpointSpec(
        method="GET",
        path="/governance/ecology/fxg/experience-score/diagnosis-reason-v9",
        params={
            "expVersion": "release",
            "needDiagnosis": True,
            "pageSource": 11,
        },
    ),
    "graphql": EndpointSpec(
        method="POST",
        path="/governance/ecology/fxg/graphql",
        requires_graphql_query=True,
    ),
    "statistics": EndpointSpec(
        method="GET",
        path="/product/tcomment/statistics",
    ),
    "comment_list": EndpointSpec(
        method="GET",
        path="/product/tcomment/commentList",
        params={"page": 0, "pageSize": 20},
    ),
    "unreply": EndpointSpec(
        method="GET",
        path="/product/tcomment/getUnreplyNegativeCommentList",
        params={"page": 1, "page_size": 10, "rank": 1},
    ),
    "tags": EndpointSpec(
        method="GET",
        path="/product/tcomment/getNegativeCommentTagsCount",
    ),
    "products": EndpointSpec(
        method="GET",
        path="/product/tcomment/getNegativeCommentProductList",
    ),
    "cash_info": EndpointSpec(
        method="GET",
        path="/governance/shop/penalty/get_violation_cash_info",
    ),
    "score_node": EndpointSpec(
        method="POST",
        path="/governance/shop/penalty/get_shop_score_node",
        json_body={},
    ),
    "ticket_count": EndpointSpec(
        method="POST",
        path="/governance/shop/penalty/penalty_ticket_count",
        json_body={},
    ),
    "enum_config": EndpointSpec(
        method="POST",
        path="/governance/shop/penalty/enum_config",
        json_body={},
    ),
    "waiting_list": EndpointSpec(
        method="POST",
        path="/governance/shop/penalty/get_waiting_list",
        json_body={},
    ),
    "top_rule": EndpointSpec(
        method="POST",
        path="/governance/shop/penalty/get_top_rule",
        json_body={},
    ),
    "high_frequency": EndpointSpec(
        method="POST",
        path="/governance/shop/penalty/get_high_frequency_penalty",
        json_body={},
    ),
}


class HttpScraper:
    def __init__(
        self,
        base_url: str = "https://fxg.jinritemai.com",
        timeout: float = 15.0,
        client: httpx.Client | None = None,
        cookie_provider: Callable[[str], Mapping[str, str]] | None = None,
        common_query_provider: Callable[[str], Mapping[str, Any]] | None = None,
        graphql_query: str | None = None,
        retry_backoff_base: float = 0.2,
        retry_backoff_max: float = 1.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._cookie_provider = cookie_provider
        self._common_query_provider = common_query_provider
        self._graphql_query = graphql_query
        self._retry_backoff_base = max(float(retry_backoff_base), 0.0)
        self._retry_backoff_max = max(float(retry_backoff_max), 0.0)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            http2=True,
        )

    def __enter__(self) -> HttpScraper:
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_dashboard(self, shop_id: str, date: str) -> dict[str, Any]:
        return self._fetch_dashboard(
            shop_id=shop_id,
            date=date,
            runtime_config=None,
            api_groups=list(ENDPOINT_GROUP_ORDER),
            common_query={},
            cookie_mapping=self._cookie_provider(shop_id)
            if self._cookie_provider
            else {},
            graphql_query=self._graphql_query,
            source="script",
            max_retries=0,
        )

    def fetch_dashboard_with_context(
        self, runtime_config: ShopDashboardRuntimeConfig, date: str
    ) -> dict[str, Any]:
        return self._fetch_dashboard(
            shop_id=runtime_config.shop_id,
            date=date,
            runtime_config=runtime_config,
            api_groups=runtime_config.api_groups,
            common_query=runtime_config.common_query,
            cookie_mapping=runtime_config.cookies,
            graphql_query=runtime_config.graphql_query or self._graphql_query,
            source="script",
            max_retries=max(int(runtime_config.retry_count), 0),
        )

    def _fetch_dashboard(
        self,
        *,
        shop_id: str,
        date: str,
        runtime_config: ShopDashboardRuntimeConfig | None,
        api_groups: list[str],
        common_query: Mapping[str, Any],
        cookie_mapping: Mapping[str, str],
        graphql_query: str | None,
        source: str,
        max_retries: int,
    ) -> dict[str, Any]:
        groups = set(api_groups)
        if not groups:
            raise ShopDashboardScraperError(
                "No API groups configured",
                error_data={"target_groups": api_groups, "shop_id": shop_id},
            )
        payloads = {
            group_name: self._build_default_payload()
            for group_name in ENDPOINT_GROUP_ORDER
        }
        group_errors: dict[str, dict[str, str]] = {}
        for group_name in ENDPOINT_GROUP_ORDER:
            if group_name not in groups:
                continue
            spec = ENDPOINT_SPECS[group_name]
            request_payload = build_endpoint_request_payload(
                runtime_config,
                metric_date=date,
                group_name=group_name,
                base_params=spec.params,
                base_json_body=spec.json_body,
                requires_graphql_query=spec.requires_graphql_query,
                graphql_query=graphql_query,
            )
            for warning in request_payload.warnings:
                logger.warning(
                    "shop_dashboard unknown filter group=%s warning=%s shop_id=%s",
                    group_name,
                    warning,
                    shop_id,
                )
            if spec.requires_graphql_query and request_payload.json_body is None:
                continue
            try:
                payloads[group_name] = self._request_json(
                    spec.method,
                    spec.path,
                    shop_id,
                    date,
                    params=request_payload.params,
                    json_body=request_payload.json_body,
                    common_query=common_query,
                    cookie_mapping=cookie_mapping,
                    max_retries=max_retries,
                )
            except ShopDashboardScraperError as exc:
                if group_name in CORE_REQUIRED_GROUPS:
                    raise
                payloads[group_name] = self._build_default_payload()
                group_errors[group_name] = self._extract_group_error(exc)

        overview_payload = payloads["overview"]
        statistics_payload = payloads["statistics"]
        comment_list_payload = payloads["comment_list"]
        unreply_payload = payloads["unreply"]
        tags_payload = payloads["tags"]
        products_payload = payloads["products"]
        cash_payload = payloads["cash_info"]
        score_node_payload = payloads["score_node"]
        ticket_count_payload = payloads["ticket_count"]
        waiting_list_payload = payloads["waiting_list"]
        top_rule_payload = payloads["top_rule"]
        high_frequency_payload = payloads["high_frequency"]

        return {
            "shop_id": shop_id,
            "target_shop_id": shop_id,
            "actual_shop_id": extract_actual_shop_id(
                payloads["analysis"],
                payloads["overview"],
            ),
            "shop_name": extract_shop_name(
                payloads["analysis"],
                payloads["overview"],
            )
            or "",
            "metric_date": date,
            "source": source,
            **parse_core_scores(overview_payload),
            "reviews": {
                "summary": parse_comment_summary(
                    statistics_payload,
                    unreply_payload,
                    tags_payload,
                    products_payload,
                ),
                "items": parse_comment_details(comment_list_payload),
            },
            "violations": {
                "summary": parse_violation_summary(
                    cash_payload, score_node_payload, ticket_count_payload
                ),
                **parse_violation_details(
                    waiting_list_payload, top_rule_payload, high_frequency_payload
                ),
            },
            "raw": self._build_raw_payload(
                payloads=payloads,
                unreply_payload=unreply_payload,
                tags_payload=tags_payload,
                products_payload=products_payload,
                group_errors=group_errors,
            ),
        }

    def _request_json(
        self,
        method: str,
        path: str,
        shop_id: str,
        date: str,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        common_query: Mapping[str, Any] | None = None,
        cookie_mapping: Mapping[str, str] | None = None,
        max_retries: int = 0,
    ) -> dict[str, Any]:
        request_params: dict[str, Any] = {"shop_id": shop_id, "date": date}
        if common_query:
            request_params.update(dict(common_query))
        elif self._common_query_provider:
            request_params.update(dict(self._common_query_provider(shop_id)))
        if params:
            request_params.update(dict(params))

        timeout_seconds = self._resolve_timeout_seconds()
        request_url = self._build_request_url(path)
        logger.debug(
            "shop_dashboard request start method=%s path=%s url=%s",
            method,
            path,
            request_url,
        )
        try:
            response = self._request_with_retry(
                method=method,
                url=path,
                params=request_params,
                json=json_body,
                headers=self._build_headers(shop_id, cookie_mapping=cookie_mapping),
                cookies=self._build_cookies(cookie_mapping),
                max_retries=max_retries,
            )
            logger.debug(
                "shop_dashboard request success method=%s path=%s status=%s",
                method,
                path,
                response.status_code,
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "shop_dashboard request timeout method=%s path=%s url=%s",
                method,
                path,
                request_url,
            )
            raise ShopDashboardScraperError(
                "HTTP request timeout",
                error_data={
                    "method": method,
                    "path": path,
                    "url": request_url,
                    "timeout": timeout_seconds,
                },
            ) from exc
        except httpx.HTTPStatusError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else None
            response_body = response.text if response is not None else ""
            response_body_snippet = response_body[:300] if response_body else ""
            url = str(response.request.url) if response is not None else request_url
            logger.warning(
                "shop_dashboard request status error method=%s path=%s status=%s",
                method,
                path,
                status_code,
            )
            raise ShopDashboardScraperError(
                "HTTP status error",
                error_data={
                    "method": method,
                    "path": path,
                    "url": url,
                    "status_code": status_code,
                    "response_body_snippet": response_body_snippet,
                },
            ) from exc
        except httpx.RequestError as exc:
            resolved_url = (
                str(exc.request.url) if exc.request is not None else request_url
            )
            logger.warning(
                "shop_dashboard request network error method=%s path=%s url=%s",
                method,
                path,
                resolved_url,
            )
            raise ShopDashboardScraperError(
                "HTTP request failed",
                error_data={
                    "method": method,
                    "path": path,
                    "url": resolved_url,
                    "error": str(exc),
                },
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            response_snippet = response.text[:500] if response.text else ""
            logger.warning(
                "shop_dashboard request invalid json method=%s path=%s snippet=%s",
                method,
                path,
                response_snippet,
            )
            raise ShopDashboardScraperError(
                "Invalid JSON response",
                error_data={
                    "path": path,
                    "method": method,
                    "response_body_snippet": response_snippet,
                },
            ) from exc
        if not isinstance(payload, dict):
            raise ShopDashboardScraperError(
                "Unexpected response type",
                error_data={"path": path, "method": method},
            )
        ensure_payload_success(payload)
        return payload

    def _request_with_retry(
        self,
        *,
        method: str,
        url: str,
        params: Mapping[str, Any] | None,
        json: Mapping[str, Any] | None,
        headers: Mapping[str, str] | None,
        cookies: httpx.Cookies | None,
        max_retries: int,
    ) -> httpx.Response:
        total_attempts = max(int(max_retries), 0) + 1
        attempt = 0
        while attempt < total_attempts:
            attempt += 1
            request = self._client.build_request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers=headers,
                cookies=cookies,
            )
            try:
                response = self._client.send(request)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status_code = (
                    exc.response.status_code if exc.response is not None else 0
                )
                if attempt >= total_attempts or not self._is_retryable_status(
                    status_code
                ):
                    raise
                retry_after_seconds = self._retry_after_seconds(exc.response)
                retry_reason = f"status={status_code}"
                if retry_after_seconds is not None:
                    retry_reason = (
                        f"{retry_reason},retry_after={retry_after_seconds:.3f}s"
                    )
                self._log_retry(
                    attempt=attempt,
                    total_attempts=total_attempts,
                    method=method,
                    path=url,
                    reason=retry_reason,
                )
                if retry_after_seconds is not None and retry_after_seconds > 0:
                    time.sleep(retry_after_seconds)
                else:
                    self._sleep_before_retry(attempt)
            except httpx.TimeoutException:
                if attempt >= total_attempts:
                    raise
                self._log_retry(
                    attempt=attempt,
                    total_attempts=total_attempts,
                    method=method,
                    path=url,
                    reason="timeout",
                )
                self._sleep_before_retry(attempt)
            except httpx.RequestError as exc:
                if attempt >= total_attempts:
                    raise
                self._log_retry(
                    attempt=attempt,
                    total_attempts=total_attempts,
                    method=method,
                    path=url,
                    reason=str(exc),
                )
                self._sleep_before_retry(attempt)
        raise ShopDashboardScraperError(
            "HTTP request failed",
            error_data={"method": method, "path": url},
        )

    def _build_raw_payload(
        self,
        *,
        payloads: Mapping[str, dict[str, Any]],
        unreply_payload: dict[str, Any],
        tags_payload: dict[str, Any],
        products_payload: dict[str, Any],
        group_errors: Mapping[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        return {
            "experience": {
                "overview": payloads["overview"],
                "analysis": payloads["analysis"],
                "diagnosis": payloads["diagnosis"],
                "graphql": payloads["graphql"],
            },
            "reviews": {
                "statistics": payloads["statistics"],
                "comment_list": payloads["comment_list"],
                "unreply_negative": unreply_payload,
                "negative_tags": tags_payload,
                "negative_products": products_payload,
            },
            "violations": {
                "cash_info": payloads["cash_info"],
                "score_node": payloads["score_node"],
                "ticket_count": payloads["ticket_count"],
                "enum_config": payloads["enum_config"],
                "waiting_list": payloads["waiting_list"],
                "top_rule": payloads["top_rule"],
                "high_frequency": payloads["high_frequency"],
            },
            "group_errors": {
                group_name: {
                    "code": str(error.get("code", "")),
                    "message": str(error.get("message", "")),
                }
                for group_name, error in dict(group_errors or {}).items()
            },
        }

    @staticmethod
    def _build_default_payload() -> dict[str, Any]:
        return {"code": 0, "data": {}}

    def _build_cookies(
        self, cookie_mapping: Mapping[str, str] | None = None
    ) -> httpx.Cookies | None:
        resolved_cookie_mapping = dict(cookie_mapping or {})
        if not resolved_cookie_mapping:
            return None
        cookies = httpx.Cookies()
        for key, value in resolved_cookie_mapping.items():
            if key is None or value is None:
                continue
            cookies.set(str(key), str(value))
        return cookies if cookies else None

    def _build_headers(
        self, shop_id: str, cookie_mapping: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        _ = (shop_id, cookie_mapping)
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }

    def _build_request_url(self, path: str) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self._base_url}{normalized_path}"

    def _resolve_timeout_seconds(self) -> float | None:
        timeout = getattr(self._client, "timeout", None)
        if isinstance(timeout, (float, int)):
            return float(timeout)
        if not isinstance(timeout, httpx.Timeout):
            return None
        candidates = [
            timeout.connect,
            timeout.read,
            timeout.write,
            timeout.pool,
        ]
        values = [float(item) for item in candidates if isinstance(item, (float, int))]
        return max(values) if values else None

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    @staticmethod
    def _retry_after_seconds(response: httpx.Response | None) -> float | None:
        if response is None:
            return None
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None
        text = retry_after.strip()
        if not text:
            return None
        try:
            return max(float(text), 0.0)
        except ValueError:
            pass
        try:
            parsed_time = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if parsed_time.tzinfo is None:
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)
        return max((parsed_time - datetime.now(timezone.utc)).total_seconds(), 0.0)

    def _sleep_before_retry(self, attempt: int) -> None:
        if self._retry_backoff_base <= 0 or self._retry_backoff_max <= 0:
            return
        base_sleep_seconds = min(
            self._retry_backoff_base * (2 ** (attempt - 1)),
            self._retry_backoff_max,
        )
        if base_sleep_seconds <= 0:
            return
        jittered_sleep_seconds = random.uniform(
            base_sleep_seconds * 0.8,
            base_sleep_seconds * 1.2,
        )
        time.sleep(max(jittered_sleep_seconds, 0.0))

    def _log_retry(
        self,
        *,
        attempt: int,
        total_attempts: int,
        method: str,
        path: str,
        reason: str,
    ) -> None:
        logger.warning(
            "shop_dashboard request retry method=%s path=%s attempt=%s/%s reason=%s",
            method,
            path,
            attempt,
            total_attempts - 1,
            reason,
        )

    @staticmethod
    def _extract_group_error(exc: ShopDashboardScraperError) -> dict[str, str]:
        code = ""
        message = str(exc)
        error_data = getattr(exc, "error_data", {})
        if isinstance(error_data, Mapping):
            raw_code = error_data.get("code")
            if raw_code is None:
                raw_code = error_data.get("status_code")
            if raw_code is not None:
                code = str(raw_code)
            raw_message = (
                error_data.get("message")
                or error_data.get("error")
                or error_data.get("response_body_snippet")
            )
            if raw_message:
                message = str(raw_message)
        return {"code": code, "message": message}
