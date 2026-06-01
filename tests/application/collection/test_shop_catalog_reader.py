from types import SimpleNamespace

import pytest

from src.application.collection.account_shop_catalog_service import AccountShopCatalogResult
from src.application.collection.shop_catalog_reader import ShopDashboardShopCatalogReader
from src.domains.data_source.enums import DataSourceType
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode


class _Repo:
    def __init__(self, data_source):
        self.data_source = data_source

    async def get_by_id(self, data_source_id):
        return self.data_source


class _CatalogService:
    def __init__(self):
        self.calls = []

    async def get_shop_catalog(self, **kwargs):
        self.calls.append(kwargs)
        return AccountShopCatalogResult(
            shop_ids=["shop-1", "shop-2"],
            catalog_stale=False,
            resolve_source="fixture",
        )


@pytest.mark.asyncio
async def test_shop_catalog_reader_returns_catalog_from_shop_data_source():
    catalog_service = _CatalogService()
    reader = ShopDashboardShopCatalogReader(
        data_source_repo=_Repo(
            SimpleNamespace(
                id=7,
                source_type=DataSourceType.DOUYIN_SHOP,
                extra_config={
                    "shop_dashboard_login_state_meta": {"account_id": "acct-1"},
                    "shop_dashboard_login_state": {
                        "storage_state": {
                            "cookies": [{"name": "sid", "value": "token"}],
                            "origins": [],
                        },
                    },
                    "common_query": {"from": "dashboard"},
                },
            ),
        ),
        catalog_service=catalog_service,
    )

    catalog = await reader.get_for_data_source(7, force_refresh=True)

    assert catalog.data_source_id == 7
    assert catalog.account_id == "acct-1"
    assert catalog.shop_ids == ["shop-1", "shop-2"]
    assert catalog.resolve_source == "fixture"
    assert catalog_service.calls[0]["force_refresh"] is True
    assert catalog_service.calls[0]["cookies"] == {"sid": "token"}


@pytest.mark.asyncio
async def test_shop_catalog_reader_rejects_missing_data_source():
    reader = ShopDashboardShopCatalogReader(data_source_repo=_Repo(None))

    with pytest.raises(BusinessException) as exc_info:
        await reader.get_for_data_source(99)

    assert exc_info.value.code == ErrorCode.DATASOURCE_NOT_FOUND


@pytest.mark.asyncio
async def test_shop_catalog_reader_rejects_non_shop_data_source():
    reader = ShopDashboardShopCatalogReader(
        data_source_repo=_Repo(
            SimpleNamespace(
                id=7,
                source_type=DataSourceType.FILE_UPLOAD,
                extra_config={},
            ),
        ),
    )

    with pytest.raises(BusinessException) as exc_info:
        await reader.get_for_data_source(7)

    assert exc_info.value.code == ErrorCode.DATASOURCE_UNSUPPORTED_TYPE
