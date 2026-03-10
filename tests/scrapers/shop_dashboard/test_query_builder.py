from datetime import datetime

from src.domains.data_source.enums import (
    DataSourceType,
    Granularity,
    IncrementalMode,
    TargetType,
)
from src.domains.data_source.models import DataSource, ScrapingRule
from src.scrapers.shop_dashboard.query_builder import build_endpoint_query_context
from src.scrapers.shop_dashboard.rule_config_resolver import resolve_rule_config
from src.tasks.collection.shop_dashboard_plan_builder import CollectionPlanUnit


def test_build_endpoint_query_context_applies_filters_dimensions_metrics_and_options():
    data_source = DataSource(
        name="query-ds",
        source_type=DataSourceType.DOUYIN_SHOP,
        shop_id="shop-1",
    )
    rule = ScrapingRule(
        name="query-rule",
        data_source_id=1,
        target_type=TargetType.SHOP_OVERVIEW,
        granularity=Granularity.DAY,
        timezone="Asia/Shanghai",
        incremental_mode=IncrementalMode.BY_DATE,
        filters={"shop_id": ["shop-1"], "region": "east"},
        dimensions=["shop", "category"],
        metrics=["overview", "analysis"],
        top_n=30,
        sort_by="-total_score",
        include_long_tail=True,
        session_level=True,
    )
    config = resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id="exec-query",
    )
    unit = CollectionPlanUnit(
        shop_id="shop-1",
        window_start=datetime.fromisoformat("2026-03-03T00:00:00"),
        window_end=datetime.fromisoformat("2026-03-03T23:59:59"),
        metric_date="2026-03-03",
        granularity="DAY",
        cursor="cursor-1",
        plan_index=0,
    )

    context = build_endpoint_query_context(config, unit)

    assert context.params["filters"]["region"] == "east"
    assert context.params["dimensions"] == ["shop", "category"]
    assert context.params["metrics"] == ["overview", "analysis"]
    assert context.params["top_n"] == 30
    assert context.params["sort_by"] == "-total_score"
    assert context.params["include_long_tail"] is True
    assert context.params["session_level"] is True

    assert context.json_body["filters"]["region"] == "east"
    assert context.json_body["dimensions"] == ["shop", "category"]
    assert context.json_body["metrics"] == ["overview", "analysis"]
    assert context.json_body["top_n"] == 30
    assert context.json_body["sort_by"] == "-total_score"
    assert context.json_body["include_long_tail"] is True
    assert context.json_body["session_level"] is True

    assert context.graphql_variables["filters"]["region"] == "east"
    assert context.graphql_variables["dimensions"] == ["shop", "category"]
    assert context.graphql_variables["metrics"] == ["overview", "analysis"]
