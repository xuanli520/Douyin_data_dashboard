from src.domains.data_source.enums import DataSourceType
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.scrapers.shop_dashboard.runtime import (
    build_runtime_config,
    build_runtime_configs,
)


def _ds(*, extra_config: dict | None = None, shop_id: str = "shop-1") -> DataSource:
    config = dict(extra_config or {})
    config.setdefault("shop_id", shop_id)
    return DataSource(
        name="runtime-ds",
        source_type=DataSourceType.DOUYIN_SHOP,
        extra_config=config,
    )


def _rule() -> ScrapingRule:
    return ScrapingRule(
        name="runtime-rule",
        data_source_id=1,
        filters={"shop_id": ["shop-1"]},
    )


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
        rule=ScrapingRule(
            name="runtime-rule-phone",
            data_source_id=1,
            filters={"shop_id": ["shop-2"]},
        ),
        execution_id="exec-2",
    )
    runtime_with_shop = build_runtime_config(
        data_source=_ds(extra_config={}, shop_id="shop-3"),
        rule=ScrapingRule(
            name="runtime-rule-shop",
            data_source_id=1,
            filters={"shop_id": ["shop-3"]},
        ),
        execution_id="exec-3",
    )

    assert runtime_with_phone.account_id == "13800000000"
    assert runtime_with_shop.account_id == ""


def test_runtime_reads_storage_state_from_extra_config():
    storage_state = {
        "cookies": [{"name": "sid", "value": "token"}],
        "origins": [],
    }
    runtime = build_runtime_config(
        data_source=_ds(
            extra_config={
                "shop_dashboard_login_state": {
                    "storage_state": storage_state,
                }
            },
            shop_id="shop-4",
        ),
        rule=_rule(),
        execution_id="exec-4",
    )
    assert runtime.storage_state == storage_state
    assert runtime.cookies["sid"] == "token"


def test_runtime_api_groups_shop_overview_metrics_overview_does_not_force_violation_groups():
    runtime = build_runtime_config(
        data_source=_ds(extra_config={}, shop_id="shop-5"),
        rule=ScrapingRule(
            name="runtime-rule-metric-overview",
            data_source_id=1,
            metrics=["overview"],
        ),
        execution_id="exec-5",
    )
    assert runtime.api_groups == ["overview"]
    assert "ticket_count" not in runtime.api_groups
    assert "waiting_list" not in runtime.api_groups


def test_build_runtime_configs_fanout_by_filters_shop_ids():
    runtimes = build_runtime_configs(
        data_source=_ds(extra_config={}, shop_id=""),
        rule=ScrapingRule(
            name="runtime-rule-fanout",
            data_source_id=1,
            filters={"shop_id": ["shop-1", "shop-2"]},
        ),
        execution_id="exec-fanout",
    )
    assert [runtime.shop_id for runtime in runtimes] == ["shop-1", "shop-2"]
