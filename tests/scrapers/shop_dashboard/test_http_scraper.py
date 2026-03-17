import json
import logging

import httpx
import pytest

from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.exceptions import LoginExpiredError
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError
from src.scrapers.shop_dashboard.parsers import extract_shop_name


def _build_runtime(
    *,
    api_groups: list[str],
    cookies: dict[str, str] | None = None,
    retry_count: int = 3,
    graphql_query: str | None = None,
    filters: dict | None = None,
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
    top_n: int | None = None,
    sort_by: str | None = None,
    include_long_tail: bool = False,
    session_level: bool = False,
) -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_mode="EXACT",
        resolved_shop_ids=["shop-1"],
        catalog_stale=False,
        shop_id="shop-1",
        cookies=cookies or {},
        proxy=None,
        timeout=15,
        retry_count=retry_count,
        rate_limit=100,
        granularity="DAY",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=3,
        data_latency="T+1",
        target_type="SHOP_OVERVIEW",
        metrics=metrics or [],
        dimensions=dimensions or [],
        filters=filters or {},
        top_n=top_n,
        sort_by=sort_by,
        include_long_tail=include_long_tail,
        session_level=session_level,
        dedupe_key=None,
        rule_id=1,
        execution_id="exec-1",
        fallback_chain=("http", "agent"),
        graphql_query=graphql_query,
        common_query={},
        token_keys=[],
        api_groups=api_groups,
    )


def _build_handler():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/governance/shop/experiencescore/getOverviewByVersion"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "experience_score": {"value": "4.8"},
                        "goods_score": {"value": 4.7},
                        "logistics_score": {"value": 4.9},
                        "service_score": {"value": 4.6},
                    },
                },
            )
        if path.endswith("/governance/shop/experiencescore/getAnalysisScore"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "trend": [1, 2, 3],
                        "shop_id": "shop-1",
                        "shop_name": "demo-shop",
                    },
                },
            )
        if path.endswith(
            "/governance/ecology/fxg/experience-score/diagnosis-reason-v9"
        ):
            return httpx.Response(200, json={"code": 0, "data": {"reasons": ["r1"]}})
        if path.endswith("/governance/ecology/fxg/graphql"):
            return httpx.Response(200, json={"code": 0, "data": {"home": {"ok": True}}})
        if path.endswith("/product/tcomment/statistics"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"negative_comment_count": 4}},
            )
        if path.endswith("/product/tcomment/commentList"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "list": [
                            {
                                "id": "c-1",
                                "product_id": "p-1",
                                "order_id": "o-1",
                                "content": "bad",
                                "shop_reply": "reply",
                                "comment_time": 1772674049,
                                "sku": "xl-red",
                            }
                        ]
                    },
                },
            )
        if path.endswith("/product/tcomment/getUnreplyNegativeCommentList"):
            return httpx.Response(200, json={"code": 0, "data": {"count": 2}})
        if path.endswith("/product/tcomment/getNegativeCommentTagsCount"):
            return httpx.Response(200, json={"code": 0, "data": {"tags": []}})
        if path.endswith("/product/tcomment/getNegativeCommentProductList"):
            return httpx.Response(200, json={"code": 0, "data": {"products": []}})
        if path.endswith("/governance/shop/penalty/get_violation_cash_info"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"cash": {"deduct_amount": "12.5"}}},
            )
        if path.endswith("/governance/shop/penalty/get_shop_score_node"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"score": {"a_level_point": 1, "b_level_point": 2}},
                },
            )
        if path.endswith("/governance/shop/penalty/penalty_ticket_count"):
            return httpx.Response(200, json={"code": 0, "data": {"total_count": 5}})
        if path.endswith("/governance/shop/penalty/enum_config"):
            return httpx.Response(200, json={"code": 0, "data": {"ok": True}})
        if path.endswith("/governance/shop/penalty/get_waiting_list"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"list": [{"ticket_id": "t-1"}]}},
            )
        if path.endswith("/governance/shop/penalty/get_top_rule"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"list": [{"rule": "rule-1"}]}},
            )
        if path.endswith("/governance/shop/penalty/get_high_frequency_penalty"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"list": [{"rule": "rule-2"}]}},
            )
        return httpx.Response(404, json={"code": 404})

    return handler


def test_http_scraper_maps_core_scores():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    transport = httpx.MockTransport(_build_handler())
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(
            client=client, graphql_query="query ExperienceScoreHome { __typename }"
        )
        result = scraper.fetch_dashboard("shop-1", "2026-03-03")

    assert result["total_score"] == 4.8
    assert result["product_score"] == 4.7
    assert result["logistics_score"] == 4.9
    assert result["service_score"] == 4.6
    assert result["shop_name"] == "demo-shop"
    assert result["reviews"]["summary"]["negative_comment_count"] == 4
    assert result["violations"]["summary"]["ticket_count"] == 5


def test_http_scraper_extract_shop_name_fallback_to_overview():
    analysis_without_name = {"code": 0, "data": {"shop_id": "shop-1"}}
    overview_with_name = {"code": 0, "data": {"shop_name": "fallback-shop"}}

    assert (
        extract_shop_name(analysis_without_name, overview_with_name) == "fallback-shop"
    )


def test_http_scraper_raises_when_login_expired():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(
            "/governance/shop/experiencescore/getOverviewByVersion"
        ):
            return httpx.Response(
                200,
                json={"code": 10008, "message": "登录信息已失效"},
            )
        return httpx.Response(200, json={"code": 0, "data": {}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client, graphql_query="query X { __typename }")
        with pytest.raises(LoginExpiredError):
            scraper.fetch_dashboard("shop-1", "2026-03-03")


def test_http_scraper_accepts_runtime_context():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    transport = httpx.MockTransport(_build_handler())
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = _build_runtime(api_groups=["overview"])
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["total_score"] == 4.8


def test_http_scraper_keeps_core_scores_when_violation_groups_return_business_error():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/governance/shop/experiencescore/getOverviewByVersion"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "experience_score": {"value": "4.8"},
                        "goods_score": {"value": 4.7},
                        "logistics_score": {"value": 4.9},
                        "service_score": {"value": 4.6},
                    },
                },
            )
        if path.endswith("/governance/shop/penalty/penalty_ticket_count"):
            return httpx.Response(
                200,
                json={"code": 30042, "message": "permission denied"},
            )
        if path.endswith("/governance/shop/penalty/get_waiting_list"):
            return httpx.Response(
                200,
                json={"code": 30043, "message": "forbidden"},
            )
        return httpx.Response(200, json={"code": 0, "data": {}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = _build_runtime(
            api_groups=[
                "overview",
                "analysis",
                "cash_info",
                "score_node",
                "ticket_count",
                "waiting_list",
            ]
        )
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["total_score"] == 4.8
    assert result["product_score"] == 4.7
    assert result["logistics_score"] == 4.9
    assert result["service_score"] == 4.6
    assert result["violations"]["summary"]["ticket_count"] == 0
    assert result["violations"]["waiting_list"] == []
    assert result["raw"]["group_errors"]["ticket_count"]["code"] == "30042"
    assert result["raw"]["group_errors"]["waiting_list"]["message"] == "forbidden"


def test_http_scraper_rejects_empty_api_groups():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": 500})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = _build_runtime(api_groups=[])
        with pytest.raises(ShopDashboardScraperError):
            scraper.fetch_dashboard_with_context(runtime, "2026-03-03")


def test_http_scraper_uses_runtime_cookie_mapping_without_redis():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    calls = {"count": 0}

    def cookie_provider(_shop_id: str) -> dict[str, str]:
        calls["count"] += 1
        return {"sid": "from-redis"}

    transport = httpx.MockTransport(_build_handler())
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client, cookie_provider=cookie_provider)
        runtime = _build_runtime(api_groups=["overview"], cookies={})
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["source"] == "script"
    assert calls["count"] == 0


def test_http_scraper_supports_context_manager():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    transport = httpx.MockTransport(_build_handler())
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        called = {"closed": False}

        def _mark_closed() -> None:
            called["closed"] = True

        scraper.close = _mark_closed  # type: ignore[method-assign]
        with scraper as scoped:
            assert scoped is scraper

    assert called["closed"] is True


def test_http_scraper_default_payload_objects_are_isolated():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    transport = httpx.MockTransport(_build_handler())
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = _build_runtime(api_groups=["overview"])
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    analysis_payload = result["raw"]["experience"]["analysis"]
    diagnosis_payload = result["raw"]["experience"]["diagnosis"]
    statistics_payload = result["raw"]["reviews"]["statistics"]
    assert analysis_payload == {"code": 0, "data": {}}
    assert analysis_payload is not diagnosis_payload
    assert analysis_payload is not statistics_payload


def test_http_scraper_uses_httpx_cookies_with_special_values():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    seen_cookie_header: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(
            "/governance/shop/experiencescore/getOverviewByVersion"
        ):
            seen_cookie_header["value"] = request.headers.get("cookie", "")
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "experience_score": {"value": "4.8"},
                        "goods_score": {"value": 4.7},
                        "logistics_score": {"value": 4.9},
                        "service_score": {"value": 4.6},
                    },
                },
            )
        return httpx.Response(200, json={"code": 0, "data": {}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = _build_runtime(
            api_groups=["overview"],
            cookies={"sid": "token=a b", "sessionid": "x=y"},
        )
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["total_score"] == 4.8
    assert "sid=token=a b" in seen_cookie_header["value"]
    assert "sessionid=x=y" in seen_cookie_header["value"]


def test_http_scraper_build_headers_does_not_embed_cookie():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    transport = httpx.MockTransport(_build_handler())
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        headers = scraper._build_headers("shop-1", cookie_mapping={"sid": "token"})

    assert "Cookie" not in headers


def test_http_scraper_executes_groups_via_endpoint_registry():
    from src.scrapers.shop_dashboard.http_scraper import (
        ENDPOINT_GROUP_ORDER,
        ENDPOINT_SPECS,
        HttpScraper,
    )

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"code": 0, "data": {}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client, graphql_query="query X { __typename }")
        scraper.fetch_dashboard("shop-1", "2026-03-03")

    expected = {
        (ENDPOINT_SPECS[group].method, ENDPOINT_SPECS[group].path)
        for group in ENDPOINT_GROUP_ORDER
    }
    assert set(calls) == expected


def test_http_scraper_applies_filters_dimensions_top_n_sort_into_post_json():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    captured: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/governance/shop/penalty/get_shop_score_node"):
            captured["params"] = dict(request.url.params)
            captured["json"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"code": 0, "data": {"score": {}}})
        return httpx.Response(200, json={"code": 0, "data": {}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = _build_runtime(
            api_groups=["score_node"],
            filters={"shop_id": ["shop-1"], "region": "east"},
            dimensions=["shop", "category"],
            metrics=["overview", "analysis"],
            top_n=20,
            sort_by="-total_score",
            include_long_tail=True,
            session_level=True,
        )
        scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert captured["params"]["filter_region"] == "east"
    assert captured["params"]["dimensions"] == "shop,category"
    assert captured["params"]["metrics"] == "overview,analysis"
    assert captured["params"]["top_n"] == "20"
    assert captured["params"]["sort_by"] == "-total_score"
    assert captured["json"]["filters"]["region"] == "east"
    assert captured["json"]["dimensions"] == ["shop", "category"]
    assert captured["json"]["metrics"] == ["overview", "analysis"]
    assert captured["json"]["top_n"] == 20
    assert captured["json"]["sort_by"] == "-total_score"
    assert captured["json"]["include_long_tail"] is True
    assert captured["json"]["session_level"] is True


def test_http_scraper_unknown_filters_only_warn_and_continue(caplog):
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(
            "/governance/shop/experiencescore/getOverviewByVersion"
        ):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "experience_score": {"value": "4.8"},
                        "goods_score": {"value": 4.7},
                        "logistics_score": {"value": 4.9},
                        "service_score": {"value": 4.6},
                    },
                },
            )
        return httpx.Response(200, json={"code": 0, "data": {}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = _build_runtime(
            api_groups=["overview"],
            filters={"shop_id": ["shop-1"], "unknown_dimension": "x"},
        )
        with caplog.at_level(logging.WARNING):
            result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["total_score"] == 4.8
    assert "unknown_filter:unknown_dimension" in caplog.text
