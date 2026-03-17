from src.domains.data_source.enums import (
    DataSourceType,
    Granularity,
    IncrementalMode,
    TargetType,
)
from src.domains.data_source.models import DataSource
from src.domains.scraping_rule.models import ScrapingRule
from src.scrapers.shop_dashboard.rule_config_resolver import resolve_rule_config


def _build_data_source(*, extra_config: dict | None = None) -> DataSource:
    return DataSource(
        name="resolver-ds",
        source_type=DataSourceType.DOUYIN_SHOP,
        shop_id="ds-shop-1",
        extra_config=extra_config,
    )


def _build_rule(
    *,
    timezone: str = "Asia/Shanghai",
    granularity: Granularity = Granularity.DAY,
    filters: dict | None = None,
    rate_limit: dict | None = None,
    top_n: int | None = None,
    sort_by: str | None = None,
    include_long_tail: bool = False,
    session_level: bool = False,
    extra_config: dict | None = None,
) -> ScrapingRule:
    return ScrapingRule(
        name="resolver-rule",
        data_source_id=1,
        target_type=TargetType.SHOP_OVERVIEW,
        timezone=timezone,
        granularity=granularity,
        incremental_mode=IncrementalMode.BY_DATE,
        filters=filters,
        metrics=["overview"],
        rate_limit=rate_limit,
        top_n=top_n,
        sort_by=sort_by,
        include_long_tail=include_long_tail,
        session_level=session_level,
        extra_config=extra_config,
    )


def test_resolve_rule_config_parses_filters_shop_id_list_and_string():
    data_source = _build_data_source()
    rule = _build_rule(
        filters={"shop_id": [" shop-1 ", "shop-2", "shop-1"], "region": "east"}
    )

    config = resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id="exec-1",
    )
    assert config.shop_ids == ["shop-1", "shop-2"]

    config_with_string = resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id="exec-2",
        overrides={"filters": {"shop_id": " shop-3,shop-4 , shop-3 "}},
    )
    assert config_with_string.shop_ids == ["shop-3", "shop-4"]


def test_resolve_rule_config_parses_json_shop_id_array():
    data_source = _build_data_source()
    rule = _build_rule(filters={"shop_id": '["shop-1","shop-2","shop-1"]'})

    config = resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id="exec-json-shop-ids",
    )
    assert config.shop_ids == ["shop-1", "shop-2"]
    assert config.shop_mode == "EXACT"
    assert config.resolved_shop_ids == ["shop-1", "shop-2"]


def test_resolve_rule_config_field_priority_overrides_rule_extra_and_data_source():
    data_source = _build_data_source(
        extra_config={
            "timezone": "UTC",
            "granularity": "HOUR",
            "rate_limit": {"qps": 1},
            "top_n": 7,
            "sort_by": "ds_sort",
            "include_long_tail": True,
            "session_level": False,
            "filters": {"shop_id": ["ds-shop-a"]},
        }
    )
    rule = _build_rule(
        timezone="Asia/Shanghai",
        granularity=Granularity.DAY,
        filters={"shop_id": ["rule-shop-a"], "region": "rule"},
        rate_limit={"qps": 5},
        top_n=15,
        sort_by="-score",
        include_long_tail=False,
        session_level=False,
        extra_config={
            "timezone": "Asia/Tokyo",
            "granularity": "MONTH",
            "rate_limit": {"qps": 3},
            "top_n": 9,
            "sort_by": "rule_extra_sort",
            "include_long_tail": True,
            "session_level": True,
            "filters": {"shop_id": ["rule-extra-shop-a"]},
        },
    )

    config = resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id="exec-3",
        overrides={
            "timezone": "Europe/London",
            "granularity": "week",
            "rate_limit": 9,
            "top_n": 66,
            "sort_by": "override_sort",
            "include_long_tail": False,
            "session_level": True,
            "filters": {"shop_id": "override-shop-1,override-shop-2"},
        },
    )

    assert config.timezone == "Europe/London"
    assert config.granularity == "WEEK"
    assert config.rate_limit == 9
    assert config.top_n == 66
    assert config.sort_by == "override_sort"
    assert config.include_long_tail is False
    assert config.session_level is True
    assert config.shop_ids == ["override-shop-1", "override-shop-2"]
    assert config.metrics == ["overview"]


def test_resolve_rule_config_should_not_fallback_to_data_source_shop_id():
    data_source = _build_data_source()
    rule = _build_rule(filters={})

    config = resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id="exec-no-fallback",
    )

    assert config.shop_id == ""
    assert config.shop_ids == []
    assert config.resolved_shop_ids == []
    assert config.shop_mode == "EXACT"


def test_resolve_rule_config_all_mode_ignores_shop_id_details():
    data_source = _build_data_source(extra_config={"shop_ids": ["shop-10", "shop-11"]})
    rule = _build_rule(filters={"shop_id": ["shop-1", "shop-2"]})

    config = resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id="exec-all-mode",
        overrides={"all": True, "shop_id": "shop-9"},
    )

    assert config.shop_mode == "ALL"
    assert config.resolved_shop_ids == []
    assert config.filters["all"] is True
    assert config.filters["shop_id"] == ["shop-1", "shop-2"]
