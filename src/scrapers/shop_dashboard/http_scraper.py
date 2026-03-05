from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import httpx

from src.scrapers.shop_dashboard.parsers import (
    ensure_payload_success,
    parse_comment_details,
    parse_comment_summary,
    parse_core_scores,
    parse_violation_details,
    parse_violation_summary,
)
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.tasks.exceptions import ScrapingFailedException


class HttpScraper:
    def __init__(
        self,
        base_url: str = "https://fxg.jinritemai.com",
        timeout: float = 15.0,
        client: httpx.Client | None = None,
        cookie_provider: Callable[[str], Mapping[str, str]] | None = None,
        common_query_provider: Callable[[str], Mapping[str, Any]] | None = None,
        graphql_query: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._cookie_provider = cookie_provider
        self._common_query_provider = common_query_provider
        self._graphql_query = graphql_query
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            http2=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_dashboard(self, shop_id: str, date: str) -> dict[str, Any]:
        all_groups = [
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
        ]
        return self._fetch_dashboard(
            shop_id=shop_id,
            date=date,
            api_groups=all_groups,
            common_query={},
            cookie_mapping=self._cookie_provider(shop_id)
            if self._cookie_provider
            else {},
            graphql_query=self._graphql_query,
            source="script",
        )

    def fetch_dashboard_with_context(
        self, runtime_config: ShopDashboardRuntimeConfig, date: str
    ) -> dict[str, Any]:
        return self._fetch_dashboard(
            shop_id=runtime_config.shop_id,
            date=date,
            api_groups=runtime_config.api_groups,
            common_query=runtime_config.common_query,
            cookie_mapping=runtime_config.cookies,
            graphql_query=runtime_config.graphql_query or self._graphql_query,
            source="script",
        )

    def _fetch_dashboard(
        self,
        *,
        shop_id: str,
        date: str,
        api_groups: list[str],
        common_query: Mapping[str, Any],
        cookie_mapping: Mapping[str, str],
        graphql_query: str | None,
        source: str,
    ) -> dict[str, Any]:
        groups = set(api_groups)
        default_payload: dict[str, Any] = {"code": 0, "data": {}}

        overview_payload = default_payload
        if "overview" in groups:
            overview_payload = self._request_json(
                "GET",
                "/governance/shop/experiencescore/getOverviewByVersion",
                shop_id,
                date,
                params={
                    "exp_version": "release",
                    "new_shop_version": "release",
                    "source": 1,
                },
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        analysis_payload = default_payload
        if "analysis" in groups:
            analysis_payload = self._request_json(
                "GET",
                "/governance/shop/experiencescore/getAnalysisScore",
                shop_id,
                date,
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        diagnosis_payload = default_payload
        if "diagnosis" in groups:
            diagnosis_payload = self._request_json(
                "GET",
                "/governance/ecology/fxg/experience-score/diagnosis-reason-v9",
                shop_id,
                date,
                params={
                    "expVersion": "release",
                    "needDiagnosis": True,
                    "pageSource": 11,
                },
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        graphql_payload: dict[str, Any] = default_payload
        if "graphql" in groups and graphql_query:
            graphql_payload = self._request_json(
                "POST",
                "/governance/ecology/fxg/graphql",
                shop_id,
                date,
                json_body={
                    "operationName": "ExperienceScoreHome",
                    "query": graphql_query,
                    "variables": {"shopId": shop_id, "date": date},
                },
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        statistics_payload = default_payload
        if "statistics" in groups:
            statistics_payload = self._request_json(
                "GET",
                "/product/tcomment/statistics",
                shop_id,
                date,
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        comment_list_payload = default_payload
        if "comment_list" in groups:
            comment_list_payload = self._request_json(
                "GET",
                "/product/tcomment/commentList",
                shop_id,
                date,
                params={"page": 0, "pageSize": 20},
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        unreply_payload = default_payload
        if "unreply" in groups:
            unreply_payload = self._request_json(
                "GET",
                "/product/tcomment/getUnreplyNegativeCommentList",
                shop_id,
                date,
                params={"page": 1, "page_size": 10, "rank": 1},
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        tags_payload = default_payload
        if "tags" in groups:
            tags_payload = self._request_json(
                "GET",
                "/product/tcomment/getNegativeCommentTagsCount",
                shop_id,
                date,
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        products_payload = default_payload
        if "products" in groups:
            products_payload = self._request_json(
                "GET",
                "/product/tcomment/getNegativeCommentProductList",
                shop_id,
                date,
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        cash_payload = default_payload
        if "cash_info" in groups:
            cash_payload = self._request_json(
                "GET",
                "/governance/shop/penalty/get_violation_cash_info",
                shop_id,
                date,
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        score_node_payload = default_payload
        if "score_node" in groups:
            score_node_payload = self._request_json(
                "POST",
                "/governance/shop/penalty/get_shop_score_node",
                shop_id,
                date,
                json_body={},
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        ticket_count_payload = default_payload
        if "ticket_count" in groups:
            ticket_count_payload = self._request_json(
                "POST",
                "/governance/shop/penalty/penalty_ticket_count",
                shop_id,
                date,
                json_body={},
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        enum_payload = default_payload
        if "enum_config" in groups:
            enum_payload = self._request_json(
                "POST",
                "/governance/shop/penalty/enum_config",
                shop_id,
                date,
                json_body={},
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        waiting_list_payload = default_payload
        if "waiting_list" in groups:
            waiting_list_payload = self._request_json(
                "POST",
                "/governance/shop/penalty/get_waiting_list",
                shop_id,
                date,
                json_body={},
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        top_rule_payload = default_payload
        if "top_rule" in groups:
            top_rule_payload = self._request_json(
                "POST",
                "/governance/shop/penalty/get_top_rule",
                shop_id,
                date,
                json_body={},
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        high_frequency_payload = default_payload
        if "high_frequency" in groups:
            high_frequency_payload = self._request_json(
                "POST",
                "/governance/shop/penalty/get_high_frequency_penalty",
                shop_id,
                date,
                json_body={},
                common_query=common_query,
                cookie_mapping=cookie_mapping,
            )

        return {
            "shop_id": shop_id,
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
            "raw": {
                "experience": {
                    "overview": overview_payload,
                    "analysis": analysis_payload,
                    "diagnosis": diagnosis_payload,
                    "graphql": graphql_payload,
                },
                "reviews": {
                    "statistics": statistics_payload,
                    "comment_list": comment_list_payload,
                    "unreply_negative": unreply_payload,
                    "negative_tags": tags_payload,
                    "negative_products": products_payload,
                },
                "violations": {
                    "cash_info": cash_payload,
                    "score_node": score_node_payload,
                    "ticket_count": ticket_count_payload,
                    "enum_config": enum_payload,
                    "waiting_list": waiting_list_payload,
                    "top_rule": top_rule_payload,
                    "high_frequency": high_frequency_payload,
                },
            },
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
    ) -> dict[str, Any]:
        request_params: dict[str, Any] = {"shop_id": shop_id, "date": date}
        if common_query:
            request_params.update(dict(common_query))
        elif self._common_query_provider:
            request_params.update(dict(self._common_query_provider(shop_id)))
        if params:
            request_params.update(dict(params))

        try:
            response = self._client.request(
                method=method,
                url=path,
                params=request_params,
                json=json_body,
                headers=self._build_headers(shop_id, cookie_mapping=cookie_mapping),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ScrapingFailedException(
                "HTTP request failed",
                error_data={"path": path, "method": method},
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ScrapingFailedException(
                "Invalid JSON response",
                error_data={"path": path, "method": method},
            ) from exc
        if not isinstance(payload, dict):
            raise ScrapingFailedException(
                "Unexpected response type",
                error_data={"path": path, "method": method},
            )
        ensure_payload_success(payload)
        return payload

    def _build_headers(
        self, shop_id: str, cookie_mapping: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }
        resolved_cookie_mapping = dict(cookie_mapping or {})
        if not resolved_cookie_mapping and self._cookie_provider:
            resolved_cookie_mapping = dict(self._cookie_provider(shop_id))
        if resolved_cookie_mapping:
            headers["Cookie"] = "; ".join(
                f"{key}={value}" for key, value in resolved_cookie_mapping.items()
            )
        return headers
