from src.domains.data_source.enums import DataSourceType
from src.domains.data_source.models import DataSource, ScrapingRule
from src.scrapers.shop_dashboard.runtime import build_runtime_config


def _ds(*, extra_config: dict | None = None, shop_id: str = "shop-1") -> DataSource:
    return DataSource(
        name="runtime-ds",
        source_type=DataSourceType.DOUYIN_SHOP,
        shop_id=shop_id,
        extra_config=extra_config,
    )


def _rule() -> ScrapingRule:
    return ScrapingRule(name="runtime-rule", data_source_id=1)


def test_runtime_account_key_priority_account_id_then_phone_then_shop_id():
    runtime = build_runtime_config(
        data_source=_ds(
            extra_config={"account_id": "acct-1", "user_phone": "13800000000"},
            shop_id="shop-1",
        ),
        rule=_rule(),
        execution_id="exec-1",
    )
    assert runtime.account_id == "acct-1"


def test_runtime_account_key_fallback_to_phone_then_shop():
    runtime_with_phone = build_runtime_config(
        data_source=_ds(extra_config={"user_phone": "13800000000"}, shop_id="shop-2"),
        rule=_rule(),
        execution_id="exec-2",
    )
    runtime_with_shop = build_runtime_config(
        data_source=_ds(extra_config={}, shop_id="shop-3"),
        rule=_rule(),
        execution_id="exec-3",
    )

    assert runtime_with_phone.account_id == "13800000000"
    assert runtime_with_shop.account_id == "shop_shop-3"
