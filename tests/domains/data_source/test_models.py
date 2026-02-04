from sqlalchemy import select

from src.domains.data_source.models import DataSource, ScrapingRule
from src.domains.data_source.enums import (
    DataSourceStatus,
    DataSourceType,
    ScrapingRuleStatus,
    TargetType,
    Granularity,
    IncrementalMode,
    DataLatency,
)


class TestDataSourceModel:
    async def test_create_data_source(self, test_db):
        async with test_db() as session:
            ds = DataSource(
                name="Test Douyin Shop",
                description="Test data source for Douyin shop",
                source_type=DataSourceType.DOUYIN_SHOP,
                status=DataSourceStatus.ACTIVE,
                shop_id="1234567890",
                account_name="Test Account",
                cookies="test_cookie_data",
                proxy="http://proxy.example.com:8080",
                api_key="test_api_key",
                api_secret="test_api_secret",
                access_token="test_access_token",
                refresh_token="test_refresh_token",
                rate_limit=100,
                retry_count=3,
                timeout=30,
                extra_config={"custom_field": "value"},
            )
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            assert ds.id is not None
            assert ds.name == "Test Douyin Shop"
            assert ds.shop_id == "1234567890"
            assert ds.source_type == DataSourceType.DOUYIN_SHOP
            assert ds.status == DataSourceStatus.ACTIVE
            assert ds.created_at is not None
            assert ds.updated_at is not None

    async def test_data_source_default_values(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Minimal DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            assert ds.source_type == DataSourceType.DOUYIN_SHOP
            assert ds.status == DataSourceStatus.ACTIVE
            assert ds.rate_limit == 100
            assert ds.retry_count == 3
            assert ds.timeout == 30
            assert ds.extra_config is None


class TestScrapingRuleModel:
    async def test_create_scraping_rule_shop_overview(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS", shop_id="1234567890")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="店铺总览采集规则",
                description="每日店铺经营大盘数据采集",
                data_source_id=ds.id,
                status=ScrapingRuleStatus.ACTIVE,
                target_type=TargetType.SHOP_OVERVIEW,
                granularity=Granularity.DAY,
                timezone="Asia/Shanghai",
                time_range={"type": "relative_days", "days": 30},
                schedule={"freq": "daily", "run_at": "02:30"},
                incremental_mode=IncrementalMode.BY_DATE,
                backfill_last_n_days=3,
                dimensions=["date"],
                metrics=[
                    "gmv",
                    "order_cnt",
                    "buyer_cnt",
                    "uv",
                    "pv",
                    "visit_buyer_rate",
                ],
                dedupe_key="shop_id+date",
                rate_limit={
                    "rps": 1,
                    "concurrency": 1,
                    "retry": 3,
                    "backoff_seconds": 5,
                },
                data_latency=DataLatency.T_PLUS_1,
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.id is not None
            assert rule.name == "店铺总览采集规则"
            assert rule.target_type == TargetType.SHOP_OVERVIEW
            assert rule.granularity == Granularity.DAY
            assert rule.timezone == "Asia/Shanghai"
            assert rule.time_range["type"] == "relative_days"
            assert rule.schedule["freq"] == "daily"
            assert rule.backfill_last_n_days == 3

    async def test_create_scraping_rule_traffic(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS", shop_id="1234567890")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="流量分析采集规则",
                data_source_id=ds.id,
                target_type=TargetType.TRAFFIC,
                granularity=Granularity.DAY,
                filters={"channel_in": ["search", "recommend", "live"]},
                dimensions=["date", "channel"],
                metrics=["exposure", "click", "ctr", "shop_uv", "pay_rate"],
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.target_type == TargetType.TRAFFIC
            assert rule.filters["channel_in"] == ["search", "recommend", "live"]

    async def test_create_scraping_rule_product(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS", shop_id="1234567890")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="商品榜单采集规则",
                data_source_id=ds.id,
                target_type=TargetType.PRODUCT,
                granularity=Granularity.DAY,
                dimensions=["date", "product_id"],
                metrics=["product_gmv", "product_pay_cnt", "product_uv", "refund_rate"],
                top_n=200,
                sort_by="gmv",
                include_long_tail=False,
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.target_type == TargetType.PRODUCT
            assert rule.top_n == 200
            assert rule.sort_by == "gmv"
            assert rule.include_long_tail is False

    async def test_create_scraping_rule_live(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS", shop_id="1234567890")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="直播分析采集规则",
                data_source_id=ds.id,
                target_type=TargetType.LIVE,
                granularity=Granularity.HOUR,
                dimensions=["date", "live_room_id", "anchor_id"],
                metrics=["live_gmv", "live_uv", "watch_time", "add_cart_cnt"],
                session_level=True,
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.target_type == TargetType.LIVE
            assert rule.granularity == Granularity.HOUR
            assert rule.session_level is True

    async def test_create_scraping_rule_aftersale_refund(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS", shop_id="1234567890")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="售后退款采集规则",
                data_source_id=ds.id,
                target_type=TargetType.AFTERSALE_REFUND,
                granularity=Granularity.DAY,
                backfill_last_n_days=14,
                filters={"refund_reason_in": ["质量", "不喜欢", "发错", "破损"]},
                dimensions=["date", "refund_reason"],
                metrics=["refund_cnt", "refund_amount", "refund_rate"],
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.target_type == TargetType.AFTERSALE_REFUND
            assert rule.backfill_last_n_days == 14
            assert rule.data_latency == DataLatency.T_PLUS_1

    async def test_create_scraping_rule_ads(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS", shop_id="1234567890")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="广告投放采集规则",
                data_source_id=ds.id,
                target_type=TargetType.ADS,
                granularity=Granularity.DAY,
                backfill_last_n_days=2,
                filters={"campaign_ids": ["camp_001", "camp_002"]},
                dimensions=["date", "campaign_id"],
                metrics=["cost", "impressions", "clicks", "ctr", "roi", "cvr"],
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.target_type == TargetType.ADS
            assert rule.backfill_last_n_days == 2

    async def test_scraping_rule_default_values(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="Minimal Rule",
                data_source_id=ds.id,
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.status == ScrapingRuleStatus.ACTIVE
            assert rule.target_type == TargetType.SHOP_OVERVIEW
            assert rule.granularity == Granularity.DAY
            assert rule.timezone == "Asia/Shanghai"
            assert rule.incremental_mode == IncrementalMode.BY_DATE
            assert rule.backfill_last_n_days == 3
            assert rule.data_latency == DataLatency.T_PLUS_1
            assert rule.include_long_tail is False
            assert rule.session_level is False


class TestDataSourceScrapingRuleRelationship:
    async def test_one_to_many_relationship(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS with Rules", shop_id="123")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule1 = ScrapingRule(
                name="Rule 1",
                data_source_id=ds.id,
                target_type=TargetType.SHOP_OVERVIEW,
            )
            rule2 = ScrapingRule(
                name="Rule 2",
                data_source_id=ds.id,
                target_type=TargetType.TRAFFIC,
            )
            session.add_all([rule1, rule2])
            await session.commit()

            result = await session.execute(
                select(ScrapingRule).where(ScrapingRule.data_source_id == ds.id)
            )
            rules = result.scalars().all()

            assert len(rules) == 2
            assert all(r.data_source_id == ds.id for r in rules)

    async def test_cascade_delete(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS for Delete")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(name="Rule to Delete", data_source_id=ds.id)
            session.add(rule)
            await session.commit()

            result = await session.execute(
                select(ScrapingRule).where(ScrapingRule.data_source_id == ds.id)
            )
            assert result.scalar_one_or_none() is not None

            await session.delete(ds)
            await session.commit()

            result = await session.execute(
                select(ScrapingRule).where(ScrapingRule.data_source_id == ds.id)
            )
            assert result.scalar_one_or_none() is None


class TestTargetTypeEnum:
    async def test_all_target_types(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            for i, target_type in enumerate(TargetType):
                rule = ScrapingRule(
                    name=f"Rule {i}",
                    data_source_id=ds.id,
                    target_type=target_type,
                )
                session.add(rule)

            await session.commit()

            result = await session.execute(select(ScrapingRule))
            rules = result.scalars().all()
            assert len(rules) == len(TargetType)


class TestGranularityEnum:
    async def test_all_granularities(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            for i, granularity in enumerate(Granularity):
                rule = ScrapingRule(
                    name=f"Rule {i}",
                    data_source_id=ds.id,
                    granularity=granularity,
                )
                session.add(rule)

            await session.commit()

            result = await session.execute(select(ScrapingRule))
            rules = result.scalars().all()
            assert len(rules) == len(Granularity)


class TestIncrementalModeEnum:
    async def test_all_incremental_modes(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            for i, mode in enumerate(IncrementalMode):
                rule = ScrapingRule(
                    name=f"Rule {i}",
                    data_source_id=ds.id,
                    incremental_mode=mode,
                )
                session.add(rule)

            await session.commit()

            result = await session.execute(select(ScrapingRule))
            rules = result.scalars().all()
            assert len(rules) == len(IncrementalMode)


class TestDataLatencyEnum:
    async def test_all_data_latencies(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            for i, latency in enumerate(DataLatency):
                rule = ScrapingRule(
                    name=f"Rule {i}",
                    data_source_id=ds.id,
                    data_latency=latency,
                )
                session.add(rule)

            await session.commit()

            result = await session.execute(select(ScrapingRule))
            rules = result.scalars().all()
            assert len(rules) == len(DataLatency)


class TestJSONFields:
    async def test_time_range_absolute(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="Absolute Time Range Rule",
                data_source_id=ds.id,
                time_range={
                    "type": "absolute",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                },
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.time_range["type"] == "absolute"
            assert rule.time_range["start_date"] == "2026-01-01"
            assert rule.time_range["end_date"] == "2026-01-31"

    async def test_filters_complex(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="Complex Filters Rule",
                data_source_id=ds.id,
                target_type=TargetType.PRODUCT,
                filters={
                    "category_ids": ["cat_001", "cat_002"],
                    "product_ids": ["prod_001"],
                    "channel_in": ["search", "recommend"],
                },
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.filters["category_ids"] == ["cat_001", "cat_002"]
            assert rule.filters["channel_in"] == ["search", "recommend"]

    async def test_rate_limit_config(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="Rate Limited Rule",
                data_source_id=ds.id,
                rate_limit={
                    "rps": 1,
                    "concurrency": 1,
                    "retry": 3,
                    "backoff_seconds": 5,
                },
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.rate_limit["rps"] == 1
            assert rule.rate_limit["backoff_seconds"] == 5

    async def test_dimensions_and_metrics_arrays(self, test_db):
        async with test_db() as session:
            ds = DataSource(name="Test DS")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)

            rule = ScrapingRule(
                name="Full Metrics Rule",
                data_source_id=ds.id,
                target_type=TargetType.SHOP_OVERVIEW,
                dimensions=["date"],
                metrics=[
                    "gmv",
                    "order_cnt",
                    "buyer_cnt",
                    "uv",
                    "pv",
                    "visit_buyer_rate",
                    "aov",
                    "refund_rate",
                ],
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

            assert rule.dimensions == ["date"]
            assert len(rule.metrics) == 8
            assert "gmv" in rule.metrics
