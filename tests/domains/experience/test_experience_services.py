from datetime import UTC, date, datetime

from src.cache.local import LocalCache
from src.domains.experience.repository import ExperienceRepository
from src.domains.experience.services import ExperienceQueryService
from src.shared.redis_keys import redis_keys


class _FakeRedisClient:
    def __init__(self) -> None:
        self._set_members: dict[str, set[str]] = {}

    async def eval(self, script: str, numkeys: int, *args):  # pragma: no cover
        if numkeys != 1:
            raise ValueError("expected exactly one key")
        index_key, cache_key, _ttl = args
        members = self._set_members.setdefault(str(index_key), set())
        members.add(str(cache_key))
        return 1

    async def type(self, key: str) -> str:
        if key in self._set_members:
            return "set"
        return "none"

    async def smembers(self, key: str) -> set[str]:
        return set(self._set_members.get(key, set()))


class _FakeRedisSetCache:
    def __init__(self) -> None:
        self.client = _FakeRedisClient()
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        if await self.client.type(key) == "set":
            raise RuntimeError(
                "WRONGTYPE Operation against a key holding the wrong kind of value"
            )
        return self._store.get(key)

    async def delete(self, key: str) -> bool:
        deleted = False
        if key in self._store:
            del self._store[key]
            deleted = True
        if key in self.client._set_members:
            del self.client._set_members[key]
            deleted = True
        return deleted

    async def exists(self, key: str) -> bool:
        return key in self._store or key in self.client._set_members

    async def close(self) -> None:
        self._store.clear()
        self.client._set_members.clear()


async def _seed_metrics_and_issues(repo: ExperienceRepository) -> None:
    for metric_date, values in [
        (
            date(2026, 3, 1),
            {"product": 90.0, "logistics": 88.0, "service": 86.0, "risk": 80.0},
        ),
        (
            date(2026, 3, 2),
            {"product": 91.0, "logistics": 87.0, "service": 87.0, "risk": 81.0},
        ),
        (
            date(2026, 3, 3),
            {"product": 92.0, "logistics": 89.0, "service": 88.0, "risk": 79.0},
        ),
    ]:
        for dimension, score in values.items():
            await repo.upsert_metric(
                shop_id="1001",
                metric_date=metric_date,
                dimension=dimension,
                metric_key="dimension_score",
                metric_score=score,
                metric_value=score,
                metric_unit="pt",
                source_field=f"raw.{dimension}.score",
                is_penalty=dimension == "risk",
                deduct_points=max(0.0, 100.0 - score) if dimension == "risk" else 0.0,
                source="seed",
            )

    await repo.upsert_metric(
        shop_id="1001",
        metric_date=date(2026, 3, 3),
        dimension="risk",
        metric_key="fake_transaction",
        metric_score=78.0,
        metric_value=22.0,
        metric_unit="pt",
        source_field="raw.risk.fake_transaction_cases",
        is_penalty=True,
        deduct_points=22.0,
        source="seed",
        extra={"impact_score": 14.3, "status": "processing", "owner": "owner_7"},
    )

    await repo.upsert_metric(
        shop_id="1001",
        metric_date=date(2026, 3, 3),
        dimension="product",
        metric_key="product_return_rate",
        metric_score=89.0,
        metric_value=1.8,
        metric_unit="%",
        source_field="raw.product.return_rate",
        source="seed",
    )

    await repo.upsert_issue(
        shop_id="1001",
        metric_date=date(2026, 3, 3),
        dimension="product",
        issue_key="issue_1",
        issue_title="product defect complaints",
        status="pending",
        owner="owner_1",
        impact_score=18.5,
        deduct_points=6.2,
        occurred_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
        deadline_at=datetime(2026, 3, 6, 18, 0, tzinfo=UTC),
        source="seed",
    )
    await repo.upsert_issue(
        shop_id="1001",
        metric_date=date(2026, 3, 2),
        dimension="risk",
        issue_key="issue_2",
        issue_title="policy violation warning",
        status="resolved",
        owner="owner_2",
        impact_score=11.0,
        deduct_points=3.0,
        occurred_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
        deadline_at=None,
        source="seed",
    )


async def test_get_overview_returns_weighted_score_and_alerts(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        await _seed_metrics_and_issues(repo)
        await session.commit()

        service = ExperienceQueryService(repo=repo)
        overview = await service.get_overview(shop_id=1001, date_range="30d")

        assert overview.shop_id == 1001
        assert len(overview.dimensions) == 4
        # formula: product*40% + logistics*30% + service*30% - risk_deduct_points
        # latest scores: product=92, logistics=89, service=88, risk_deduct_points=21
        assert overview.overall_score == 68.9
        assert overview.alerts.total == 2
        assert overview.alerts.critical == 1
        assert overview.alerts.warning == 1
        assert overview.alerts.unread == 1


async def test_get_metric_detail_risk_contains_penalty_fields(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        await _seed_metrics_and_issues(repo)
        await session.commit()

        service = ExperienceQueryService(repo=repo)
        detail = await service.get_metric_detail(
            shop_id=1001,
            metric_type="risk",
            period="30d",
            date_range="30d",
        )

        assert detail.metric_type == "risk"
        assert len(detail.sub_metrics) == 3
        assert len(detail.trend) >= 1
        fake_tx = [
            item for item in detail.sub_metrics if item.id == "fake_transaction"
        ][0]
        assert fake_tx.deduct_points is not None
        assert fake_tx.impact_score is not None
        assert fake_tx.status == "processing"
        assert fake_tx.owner == "owner_7"


async def test_get_dashboard_kpis_contains_trend_and_change(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        await _seed_metrics_and_issues(repo)
        await session.commit()

        service = ExperienceQueryService(repo=repo)
        kpis = await service.get_dashboard_kpis(shop_id=1001, date_range="30d")

        assert kpis.shop_id == 1001
        assert len(kpis.kpis) == 3
        assert len(kpis.trend) == 3
        assert kpis.kpis[0].id == "orders"
        assert kpis.kpis[1].id == "gmv"
        assert kpis.kpis[2].id == "refund_rate"
        assert kpis.kpis[0].change.endswith("%")


async def test_get_metric_detail_uses_cache_on_repeated_query(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        await _seed_metrics_and_issues(repo)
        await session.commit()

        cache = LocalCache()
        service = ExperienceQueryService(repo=repo, cache=cache)

        original_list_metric_rows = repo.list_metric_rows
        list_metric_rows_call_count = 0

        async def counted_list_metric_rows(*args, **kwargs):
            nonlocal list_metric_rows_call_count
            list_metric_rows_call_count += 1
            return await original_list_metric_rows(*args, **kwargs)

        repo.list_metric_rows = counted_list_metric_rows  # type: ignore[method-assign]

        first = await service.get_metric_detail(
            shop_id=1001,
            metric_type="product",
            period="30d",
            date_range="30d",
        )
        second = await service.get_metric_detail(
            shop_id=1001,
            metric_type="product",
            period="30d",
            date_range="30d",
        )

        assert list_metric_rows_call_count == 1
        assert first.model_dump() == second.model_dump()
        await cache.close()


async def test_invalidate_shop_date_should_refresh_cached_dashboard_data(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        await _seed_metrics_and_issues(repo)
        await session.commit()

        cache = LocalCache()
        service = ExperienceQueryService(repo=repo, cache=cache)

        first = await service.get_dashboard_overview(shop_id=1001, date_range="30d")

        await repo.upsert_metric(
            shop_id="1001",
            metric_date=date(2026, 3, 3),
            dimension="product",
            metric_key="dimension_score",
            metric_score=62.0,
            metric_value=62.0,
            metric_unit="pt",
            source_field="raw.product.score",
            source="seed_v2",
        )
        await session.commit()

        stale = await service.get_dashboard_overview(shop_id=1001, date_range="30d")
        assert stale.model_dump() == first.model_dump()

        await service.invalidate_shop_date(shop_id=1001, metric_date=date(2026, 3, 3))
        refreshed = await service.get_dashboard_overview(shop_id=1001, date_range="30d")

        assert refreshed.cards["gmv"] != stale.cards["gmv"]
        await cache.close()


async def test_invalidate_shop_date_should_support_redis_set_index(test_db):
    async with test_db() as session:
        repo = ExperienceRepository(session)
        cache = _FakeRedisSetCache()
        service = ExperienceQueryService(repo=repo, cache=cache)

        cache_key = "experience:dashboard:1001:30d:overview"
        await cache.set(cache_key, '{"shop_id":1001}')
        index_key = redis_keys.experience_cache_date_index(
            shop_id=1001,
            metric_date="2026-03-03",
        )
        await cache.client.eval("SADD", 1, index_key, cache_key, 300)

        deleted = await service.invalidate_shop_date(
            shop_id=1001,
            metric_date=date(2026, 3, 3),
        )

        assert deleted == 1
        assert await cache.exists(cache_key) is False
        assert await cache.exists(index_key) is False
