import httpx
import pytest

from src.scrapers.shop_dashboard.account_shop_resolver import AccountShopResolver


@pytest.mark.asyncio
async def test_account_shop_resolver_resolves_from_extra_config():
    resolver = AccountShopResolver()

    shop_ids = await resolver.resolve_shop_ids(
        account_id="acct-1",
        cookies={},
        extra_config={"shop_ids": ["shop-1", "shop-2", "shop-1"]},
    )

    assert shop_ids == ["shop-1", "shop-2"]


@pytest.mark.asyncio
async def test_account_shop_resolver_resolves_from_shop_subject_endpoint():
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/compass/user/info":
            return httpx.Response(
                status_code=200,
                json={"code": 0, "data": {"user_id": 1}},
            )
        if request.url.path == "/api/compass/shop/get_login_subject":
            return httpx.Response(
                status_code=200,
                json={
                    "code": 0,
                    "data": {
                        "shops": [
                            {"shop_id": "shop-a"},
                            {"shopId": "shop-b"},
                        ]
                    },
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
