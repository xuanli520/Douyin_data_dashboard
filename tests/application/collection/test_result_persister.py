from datetime import date
from types import SimpleNamespace

from src.application.collection.result_persister import CollectionResultPersister
from src.cache.local import LocalCache


async def test_persist_should_invalidate_experience_cache_after_commit(
    test_db,
    monkeypatch,
):
    import src.application.collection.result_persister as persister_module
    from src.domains.experience.services import ExperienceQueryService

    cache = LocalCache()
    persister_module.cache_module.cache = cache
    calls: list[tuple[str | int, date]] = []
    original_invalidate_shop_date = ExperienceQueryService.invalidate_shop_date

    async def capture_invalidate_shop_date(self, *, shop_id, metric_date):
        calls.append((shop_id, metric_date))
        return 1

    monkeypatch.setattr(
        ExperienceQueryService,
        "invalidate_shop_date",
        capture_invalidate_shop_date,
    )

    try:
        async with test_db() as session:
            persister = CollectionResultPersister()
            await persister.persist(
                session=session,
                runtime=SimpleNamespace(shop_id="1001"),
                metric_date="2026-03-03",
                payload={
                    "shop_id": "1001",
                    "target_shop_id": "1001",
                    "actual_shop_id": "1001",
                    "total_score": 80.0,
                    "product_score": 82.0,
                    "logistics_score": 78.0,
                    "service_score": 81.0,
                    "bad_behavior_score": 0.0,
                    "source": "script",
                    "reviews": {"items": []},
                    "violations": {"waiting_list": []},
                    "raw": {},
                },
            )
    finally:
        ExperienceQueryService.invalidate_shop_date = original_invalidate_shop_date
        persister_module.cache_module.cache = None
        await cache.close()

    assert calls == [("1001", date(2026, 3, 3))]
