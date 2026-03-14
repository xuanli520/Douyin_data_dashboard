from datetime import date

from src.cache.local import LocalCache
from src.domains.experience.services import ExperienceQueryService
from src.domains.shop_dashboard.repository import ShopDashboardRepository
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


async def _seed_materials(repo: ShopDashboardRepository) -> None:
    for metric_date, values in [
        (
            date(2026, 3, 1),
            {
                "total": 86.6,
                "product": 90.0,
                "logistics": 88.0,
                "service": 86.0,
                "bad_behavior": 20.0,
            },
        ),
        (
            date(2026, 3, 2),
            {
                "total": 87.2,
                "product": 91.0,
                "logistics": 87.0,
                "service": 87.0,
                "bad_behavior": 19.0,
            },
        ),
        (
            date(2026, 3, 3),
            {
                "total": 89.9,
                "product": 92.0,
                "logistics": 89.0,
                "service": 88.0,
                "bad_behavior": 21.0,
            },
        ),
    ]:
        await repo.upsert_score(
            shop_id="1001",
            metric_date=metric_date,
            total_score=values["total"],
            product_score=values["product"],
            logistics_score=values["logistics"],
            service_score=values["service"],
            bad_behavior_score=values["bad_behavior"],
            source="seed",
        )

    await repo.replace_violations(
        shop_id="1001",
        metric_date=date(2026, 3, 3),
        violations=[
            {
                "violation_id": "issue_1",
                "violation_type": "product",
                "description": "product defect complaints",
                "score": 18,
                "source": "seed",
            }
        ],
    )
    await repo.replace_violations(
        shop_id="1001",
        metric_date=date(2026, 3, 2),
        violations=[
            {
                "violation_id": "issue_2",
                "violation_type": "risk",
                "description": "policy violation warning",
                "score": 11,
                "source": "seed",
            }
        ],
    )
    await repo.upsert_cold_metrics(
        shop_id="1001",
        metric_date=date(2026, 3, 1),
        reason="cold reason fallback",
        violations_detail=[],
        arbitration_detail=[],
        dsr_trend=[],
        source="seed",
    )


async def test_get_overview_returns_weighted_score_and_alerts(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        await _seed_materials(repo)
        await session.commit()

        service = ExperienceQueryService(repo=repo)
        overview = await service.get_overview(shop_id=1001, date_range="30d")

        assert overview.shop_id == 1001
        assert len(overview.dimensions) == 4
        assert overview.overall_score == 89.9
        assert overview.alerts.total == 3
        assert overview.alerts.critical == 1
        assert overview.alerts.warning == 1
        assert overview.alerts.info == 1
        assert overview.alerts.unread == 3


async def test_get_metric_detail_risk_contains_penalty_fields(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        await _seed_materials(repo)
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
        assert len(detail.trend) == 3
        risk_item = detail.sub_metrics[0]
        assert risk_item.deduct_points is not None
        assert risk_item.impact_score is not None
        assert risk_item.status == "pending"


async def test_get_dashboard_kpis_contains_trend_and_change(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        await _seed_materials(repo)
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
        repo = ShopDashboardRepository(session)
        await _seed_materials(repo)
        await session.commit()

        cache = LocalCache()
        service = ExperienceQueryService(repo=repo, cache=cache)

        original_list_display_materials = repo.list_display_materials
        list_display_materials_call_count = 0

        async def counted_list_display_materials(*args, **kwargs):
            nonlocal list_display_materials_call_count
            list_display_materials_call_count += 1
            return await original_list_display_materials(*args, **kwargs)

        repo.list_display_materials = counted_list_display_materials  # type: ignore[method-assign]

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

        assert list_display_materials_call_count == 1
        assert first.model_dump() == second.model_dump()
        await cache.close()


async def test_invalidate_shop_date_should_refresh_cached_dashboard_data(test_db):
    async with test_db() as session:
        repo = ShopDashboardRepository(session)
        await _seed_materials(repo)
        await session.commit()

        cache = LocalCache()
        service = ExperienceQueryService(repo=repo, cache=cache)

        first = await service.get_dashboard_overview(shop_id=1001, date_range="30d")

        await repo.upsert_score(
            shop_id="1001",
            metric_date=date(2026, 3, 3),
            total_score=62.0,
            product_score=62.0,
            logistics_score=62.0,
            service_score=62.0,
            bad_behavior_score=50.0,
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
        repo = ShopDashboardRepository(session)
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
