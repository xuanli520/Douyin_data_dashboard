import httpx
import pytest

from src.tasks.exceptions import ScrapingFailedException


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
            return httpx.Response(200, json={"code": 0, "data": {"trend": [1, 2, 3]}})
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
    assert result["reviews"]["summary"]["negative_comment_count"] == 4
    assert result["violations"]["summary"]["ticket_count"] == 5


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
        with pytest.raises(ScrapingFailedException):
            scraper.fetch_dashboard("shop-1", "2026-03-03")


def test_http_scraper_accepts_runtime_context():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper
    from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig

    transport = httpx.MockTransport(_build_handler())
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = ShopDashboardRuntimeConfig(
            shop_id="shop-1",
            cookies={"a": "b"},
            proxy=None,
            timeout=15,
            retry_count=3,
            rate_limit=100,
            granularity="DAY",
            time_range=None,
            incremental_mode="BY_DATE",
            backfill_last_n_days=3,
            data_latency="T+1",
            target_type="SHOP_OVERVIEW",
            metrics=[],
            dimensions=[],
            filters={},
            top_n=None,
            include_long_tail=False,
            session_level=False,
            dedupe_key=None,
            rule_id=1,
            execution_id="exec-1",
            fallback_chain=("http", "browser", "llm"),
            graphql_query=None,
            common_query={},
            token_keys=[],
            api_groups=["overview"],
        )
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["total_score"] == 4.8


def test_http_scraper_rejects_empty_api_groups():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper
    from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": 500})

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client)
        runtime = ShopDashboardRuntimeConfig(
            shop_id="shop-1",
            cookies={"a": "b"},
            proxy=None,
            timeout=15,
            retry_count=3,
            rate_limit=100,
            granularity="DAY",
            time_range=None,
            incremental_mode="BY_DATE",
            backfill_last_n_days=3,
            data_latency="T+1",
            target_type="TRAFFIC",
            metrics=[],
            dimensions=[],
            filters={},
            top_n=None,
            include_long_tail=False,
            session_level=False,
            dedupe_key=None,
            rule_id=1,
            execution_id="exec-1",
            fallback_chain=("http", "browser", "llm"),
            graphql_query=None,
            common_query={},
            token_keys=[],
            api_groups=[],
        )
        with pytest.raises(ScrapingFailedException):
            scraper.fetch_dashboard_with_context(runtime, "2026-03-03")


def test_http_scraper_uses_runtime_cookie_mapping_without_redis():
    from src.scrapers.shop_dashboard.http_scraper import HttpScraper
    from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig

    calls = {"count": 0}

    def cookie_provider(_shop_id: str) -> dict[str, str]:
        calls["count"] += 1
        return {"sid": "from-redis"}

    transport = httpx.MockTransport(_build_handler())
    with httpx.Client(
        transport=transport, base_url="https://fxg.jinritemai.com"
    ) as client:
        scraper = HttpScraper(client=client, cookie_provider=cookie_provider)
        runtime = ShopDashboardRuntimeConfig(
            shop_id="shop-1",
            cookies={},
            proxy=None,
            timeout=15,
            retry_count=3,
            rate_limit=100,
            granularity="DAY",
            time_range=None,
            incremental_mode="BY_DATE",
            backfill_last_n_days=3,
            data_latency="T+1",
            target_type="SHOP_OVERVIEW",
            metrics=[],
            dimensions=[],
            filters={},
            top_n=None,
            include_long_tail=False,
            session_level=False,
            dedupe_key=None,
            rule_id=1,
            execution_id="exec-1",
            fallback_chain=("http", "browser", "llm"),
            graphql_query=None,
            common_query={},
            token_keys=[],
            api_groups=["overview"],
        )
        result = scraper.fetch_dashboard_with_context(runtime, "2026-03-03")

    assert result["source"] == "script"
    assert calls["count"] == 0
