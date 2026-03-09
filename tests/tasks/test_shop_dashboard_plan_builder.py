from datetime import UTC, datetime

import pytest

from src.domains.data_source.enums import (
    DataSourceType,
    Granularity,
    IncrementalMode,
    TargetType,
)
from src.domains.data_source.models import DataSource, ScrapingRule
from src.scrapers.shop_dashboard.rule_config_resolver import resolve_rule_config
from src.tasks.collection.shop_dashboard_plan_builder import build_collection_plan


def _resolve_config(
    *,
    granularity: Granularity,
    time_range: dict | None = None,
    incremental_mode: IncrementalMode = IncrementalMode.BY_DATE,
    backfill_last_n_days: int = 3,
    filters: dict | None = None,
    extra_config: dict | None = None,
):
    data_source = DataSource(
        name="plan-ds",
        source_type=DataSourceType.DOUYIN_SHOP,
        shop_id="default-shop",
    )
    rule = ScrapingRule(
        name="plan-rule",
        data_source_id=1,
        target_type=TargetType.SHOP_OVERVIEW,
        granularity=granularity,
        timezone="Asia/Shanghai",
        incremental_mode=incremental_mode,
        backfill_last_n_days=backfill_last_n_days,
        time_range=time_range,
        filters=filters or {"shop_id": ["shop-1"]},
        extra_config=extra_config,
    )
    return resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id="exec-plan",
    )


@pytest.mark.parametrize(
    ("granularity", "time_range", "expected_count"),
    [
        (
            Granularity.HOUR,
            {
                "start": "2026-03-02T00:00:00+08:00",
                "end": "2026-03-02T02:00:00+08:00",
            },
            3,
        ),
        (
            Granularity.DAY,
            {
                "start": "2026-03-02",
                "end": "2026-03-04",
            },
            3,
        ),
        (
            Granularity.WEEK,
            {
                "start": "2026-03-02",
                "end": "2026-03-15",
            },
            2,
        ),
        (
            Granularity.MONTH,
            {
                "start": "2026-03-01",
                "end": "2026-04-30",
            },
            2,
        ),
    ],
)
def test_build_collection_plan_supports_all_granularity_windows(
    granularity, time_range, expected_count
):
    config = _resolve_config(granularity=granularity, time_range=time_range)
    units = build_collection_plan(
        config,
        now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
    )
    assert len(units) == expected_count
    assert {unit.granularity for unit in units} == {granularity.value}


def test_time_range_overrides_incremental_backfill_window():
    config = _resolve_config(
        granularity=Granularity.DAY,
        time_range={"start": "2026-03-05", "end": "2026-03-06"},
        incremental_mode=IncrementalMode.BY_DATE,
        backfill_last_n_days=15,
    )
    units = build_collection_plan(
        config,
        now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
    )
    assert len(units) == 2
    assert [unit.metric_date for unit in units] == ["2026-03-05", "2026-03-06"]


def test_by_cursor_uses_cursor_from_filters_or_extra_config():
    config_with_filter_cursor = _resolve_config(
        granularity=Granularity.DAY,
        incremental_mode=IncrementalMode.BY_CURSOR,
        filters={"shop_id": ["shop-1", "shop-2"], "cursor": "cursor-from-filter"},
    )
    units_with_filter_cursor = build_collection_plan(
        config_with_filter_cursor,
        now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
    )
    assert len(units_with_filter_cursor) == 2
    assert {unit.cursor for unit in units_with_filter_cursor} == {"cursor-from-filter"}

    config_with_extra_cursor = _resolve_config(
        granularity=Granularity.DAY,
        incremental_mode=IncrementalMode.BY_CURSOR,
        filters={"shop_id": ["shop-3"]},
        extra_config={"cursor": "cursor-from-extra"},
    )
    units_with_extra_cursor = build_collection_plan(
        config_with_extra_cursor,
        now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
    )
    assert len(units_with_extra_cursor) == 1
    assert units_with_extra_cursor[0].cursor == "cursor-from-extra"
