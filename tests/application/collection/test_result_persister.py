from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.application.collection.result_persister import CollectionResultPersister
from src.cache.local import LocalCache
from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_result.models import AgentCollectionResult
from src.domains.shop_dashboard.models import ShopDashboardScore


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
                    "shop_name": "demo-shop",
                    "source": "browser_agent",
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


async def test_persist_should_raise_when_cache_invalidation_raises(
    test_db,
    monkeypatch,
):
    import src.application.collection.result_persister as persister_module
    from src.domains.experience.services import ExperienceQueryService

    cache = LocalCache()
    persister_module.cache_module.cache = cache
    original_invalidate_shop_date = ExperienceQueryService.invalidate_shop_date

    async def fail_invalidate_shop_date(self, *, shop_id, metric_date):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        ExperienceQueryService,
        "invalidate_shop_date",
        fail_invalidate_shop_date,
    )

    try:
        async with test_db() as session:
            persister = CollectionResultPersister()
            with pytest.raises(RuntimeError, match="redis unavailable"):
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
                        "shop_name": "demo-shop",
                        "source": "browser_agent",
                        "reviews": {"items": []},
                        "violations": {"waiting_list": []},
                        "raw": {},
                    },
                )
            score = (
                await session.execute(
                    select(ShopDashboardScore).where(
                        ShopDashboardScore.shop_id == "1001",
                        ShopDashboardScore.metric_date == date(2026, 3, 3),
                    )
                )
            ).scalar_one_or_none()
    finally:
        ExperienceQueryService.invalidate_shop_date = original_invalidate_shop_date
        persister_module.cache_module.cache = None
        await cache.close()

    assert score is not None
    assert float(score.total_score) == 80.0
    assert score.shop_name == "demo-shop"


async def test_persist_should_store_agent_result_before_commit(test_db):
    async with test_db() as session:
        recipe = await AgentRecipeRepository(session).create(
            {
                "namespace": "shop_dashboard",
                "key": "overview",
                "entrypoint": {"url": "https://example.com"},
                "steps": [],
                "observations": {},
                "assertions": [],
                "recovery_policy": {},
                "security_policy": {},
            }
        )
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
                "source": "browser_agent",
                "custom_table": [{"metric": "total", "score": 80}],
                "raw": {
                    "agent": {
                        "status": "recovered",
                        "recipe": {
                            "id": recipe.id,
                            "namespace": "shop_dashboard",
                            "key": "overview",
                            "version": 1,
                        },
                    }
                },
            },
        )

        row = (
            await session.execute(
                select(AgentCollectionResult).where(
                    AgentCollectionResult.resource_key == "1001"
                )
            )
        ).scalar_one()

        assert row.recipe_id == recipe.id
        assert row.status == "recovered"
        assert row.output == {"custom_table": [{"metric": "total", "score": 80}]}


async def test_persist_agent_result_only_skips_dashboard_score(test_db):
    async with test_db() as session:
        recipe = await AgentRecipeRepository(session).create(
            {
                "namespace": "douyin_shop_dashboard",
                "key": "experience_score_product_detail",
                "entrypoint": {"url": "https://example.com"},
                "steps": [],
                "observations": {},
                "assertions": [],
                "recovery_policy": {},
                "security_policy": {},
            }
        )
        await CollectionResultPersister().persist(
            session=session,
            runtime=SimpleNamespace(
                shop_id="1001",
                extra_config={
                    "agent_result_only": True,
                    "agent_recipe_inline": {
                        "id": recipe.id,
                        "namespace": "douyin_shop_dashboard",
                        "key": "experience_score_product_detail",
                        "version": 1,
                    },
                },
            ),
            metric_date="2026-03-03",
            payload={
                "shop_id": "1001",
                "target_shop_id": "1001",
                "actual_shop_id": "1001",
                "source": "browser_agent",
                "score_table": {
                    "headers": ["metric", "score"],
                    "rows": [["product", "100"]],
                },
            },
        )

        score = (
            await session.execute(
                select(ShopDashboardScore).where(ShopDashboardScore.shop_id == "1001")
            )
        ).scalar_one_or_none()
        result = (
            await session.execute(
                select(AgentCollectionResult).where(
                    AgentCollectionResult.resource_key == "1001"
                )
            )
        ).scalar_one()

        assert score is None
        assert result.recipe_id == recipe.id
        assert result.output["score_table"]["rows"] == [["product", "100"]]


async def test_persist_should_store_failed_agent_result_from_runtime_recipe(
    monkeypatch,
):
    import src.application.collection.result_persister as persister_module

    upserts = []

    class _ShopDashboardRepository:
        async def upsert_score(self, **_kwargs):
            return object()

    class _AgentResultRepository:
        async def upsert(self, **kwargs):
            upserts.append(kwargs)
            return object()

    class _Session:
        async def commit(self):
            return None

    monkeypatch.setattr(
        persister_module,
        "ShopDashboardRepository",
        lambda _session: _ShopDashboardRepository(),
    )
    monkeypatch.setattr(
        persister_module,
        "AgentResultRepository",
        lambda _session: _AgentResultRepository(),
    )
    monkeypatch.setattr(
        persister_module,
        "sa_inspect",
        lambda _score: SimpleNamespace(info={}),
    )
    monkeypatch.setattr(
        persister_module,
        "observe_shop_dashboard_score_upsert",
        lambda **_kwargs: None,
    )
    persister_module.cache_module.cache = None

    await CollectionResultPersister().persist(
        session=_Session(),
        runtime=SimpleNamespace(
            shop_id="1001",
            extra_config={
                "agent_recipe_inline": {
                    "id": 7,
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 1,
                }
            },
        ),
        metric_date="2026-03-03",
        payload={
            "shop_id": "1001",
            "target_shop_id": "1001",
            "actual_shop_id": "1001",
            "status": "failed",
            "source": "browser_agent",
            "reason": "data_incomplete",
            "error_code": "timeout",
            "total_score": None,
            "product_score": None,
            "logistics_score": None,
            "service_score": None,
            "bad_behavior_score": None,
            "agent_trace": [
                {
                    "stage": "browser_agent",
                    "status": "failed",
                    "error": "timeout",
                }
            ],
        },
    )

    assert upserts[0]["recipe_id"] == 7
    assert upserts[0]["status"] == "failed"
    assert upserts[0]["error_message"] == "data_incomplete"
    assert upserts[0]["output"]["agent_trace"] == [
        {
            "stage": "browser_agent",
            "status": "failed",
            "error": "timeout",
        }
    ]
