import httpx
import pytest

from src.scrapers.shop_dashboard.account_shop_resolver import AccountShopResolver


@pytest.mark.asyncio
async def test_account_shop_resolver_without_cookies_returns_fallback_shop_ids():
    resolver = AccountShopResolver()

    shop_ids = await resolver.resolve_shop_ids(
        account_id="acct-1",
        cookies={},
        extra_config={"shop_ids": ["shop-1", "shop-2", "shop-1"]},
    )

    assert shop_ids == ["shop-1", "shop-2"]


@pytest.mark.asyncio
async def test_account_shop_resolver_ignores_non_shop_fields_in_fallback_context():
    resolver = AccountShopResolver()

    shop_ids = await resolver.resolve_shop_ids(
        account_id="acct-1",
        cookies={},
        common_query={
            "shop_mode": "all",
            "subject_aid": 4966,
            "shop_name": "demo",
        },
    )

    assert shop_ids == []


@pytest.mark.asyncio
async def test_account_shop_resolver_resolves_from_shop_subject_endpoint():
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ecomauth/loginv1/get_login_subject_count":
            return httpx.Response(
                status_code=200,
                json={"code": 0, "data": {"count": 2}},
            )
        if request.url.path == "/byteshop/index/getshoplist":
            return httpx.Response(
                status_code=200,
                json={
                    "code": 0,
                    "data": [
                        {"id": "shop-a"},
                        {"id": "shop-b"},
                    ],
                },
            )
        return httpx.Response(status_code=404, json={"code": 404})

    async with httpx.AsyncClient(
        base_url="https://fxg.jinritemai.com",
        transport=httpx.MockTransport(_handler),
    ) as client:
        resolver = AccountShopResolver(client=client)
        shop_ids = await resolver.resolve_shop_ids(
            account_id="acct-1",
            cookies={"sid": "token"},
        )

    assert shop_ids == ["shop-a", "shop-b"]


@pytest.mark.asyncio
async def test_account_shop_resolver_probe_failed_can_refresh_once():
    call_state = {"probe": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ecomauth/loginv1/get_login_subject_count":
            call_state["probe"] += 1
            if call_state["probe"] == 1:
                return httpx.Response(status_code=200, json={"code": 10008})
            return httpx.Response(status_code=200, json={"code": 0})
        if request.url.path == "/byteshop/index/getshoplist":
            return httpx.Response(
                status_code=200,
                json={"code": 0, "data": [{"id": "shop-r1"}]},
            )
        return httpx.Response(status_code=404, json={"code": 404})

    async with httpx.AsyncClient(
        base_url="https://fxg.jinritemai.com",
        transport=httpx.MockTransport(_handler),
    ) as client:
        resolver = AccountShopResolver(client=client)
        shop_ids = await resolver.resolve_shop_ids(
            account_id="acct-1",
            cookies={"sid": "token"},
            refresh_login_callback=lambda _account_id: True,
        )

    assert shop_ids == ["shop-r1"]
