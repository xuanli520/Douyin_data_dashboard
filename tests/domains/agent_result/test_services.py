from datetime import date

from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_result.repository import AgentResultRepository
from src.domains.agent_result.services import AgentResultService


async def test_agent_result_service_builds_csv_from_table_observation(test_db):
    async with test_db() as session:
        recipe = await _create_recipe(session)
        repo = AgentResultRepository(session)
        await repo.upsert(
            namespace="shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 20),
            recipe_id=recipe.id,
            output={
                "score_table": [
                    "metric,score",
                    "total,90",
                    "service,88",
                ],
                "summary": "ok",
            },
        )
        await repo.upsert(
            namespace="shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 21),
            recipe_id=recipe.id,
            output={"score_table": ["metric,score", "total,91"]},
        )

        csv_content, filename = await AgentResultService(session).build_csv(
            namespace="shop_dashboard",
            resource_key="1001",
            date_from=date(2026, 5, 20),
            date_to=date(2026, 5, 21),
        )

        assert filename == "shop_dashboard_1001_2026-05-20_2026-05-21.csv"
        assert csv_content.splitlines() == [
            "date,metric,score",
            "2026-05-20,total,90",
            "2026-05-20,service,88",
            "2026-05-21,total,91",
        ]


async def test_agent_result_service_builds_csv_from_structured_table(test_db):
    async with test_db() as session:
        recipe = await _create_recipe(session)
        repo = AgentResultRepository(session)
        await repo.upsert(
            namespace="shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 20),
            recipe_id=recipe.id,
            output={
                "score_table": {
                    "headers": ["metric", "score"],
                    "rows": [["total", 90], {"metric": "service", "score": 88}],
                },
            },
        )

        csv_content, _ = await AgentResultService(session).build_csv(
            namespace="shop_dashboard",
            resource_key="1001",
            date_from=date(2026, 5, 20),
            date_to=date(2026, 5, 20),
        )

        assert csv_content.splitlines() == [
            "date,metric,score",
            "2026-05-20,total,90",
            "2026-05-20,service,88",
        ]


async def test_agent_result_service_builds_csv_by_recipe_key(test_db):
    async with test_db() as session:
        product_recipe = await _create_recipe(
            session,
            namespace="douyin_shop_dashboard",
            key="experience_score_product_detail",
        )
        logistics_recipe = await _create_recipe(
            session,
            namespace="douyin_shop_dashboard",
            key="experience_score_logistics_detail",
        )
        repo = AgentResultRepository(session)
        await repo.upsert(
            namespace="douyin_shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 20),
            recipe_id=product_recipe.id,
            output={
                "score_table": {
                    "headers": ["metric", "score"],
                    "rows": [["product", 100]],
                },
            },
        )
        await repo.upsert(
            namespace="douyin_shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 20),
            recipe_id=logistics_recipe.id,
            output={
                "score_table": {
                    "headers": ["metric", "score"],
                    "rows": [["logistics", 99]],
                },
            },
        )

        csv_content, filename = await AgentResultService(
            session
        ).build_csv_by_recipe_key(
            namespace="douyin_shop_dashboard",
            resource_key="1001",
            recipe_key="experience_score_product_detail",
            date_from=date(2026, 5, 20),
            date_to=date(2026, 5, 20),
        )

        assert filename == (
            "douyin_shop_dashboard_1001_experience_score_product_detail_"
            "2026-05-20_2026-05-20.csv"
        )
        assert csv_content.splitlines() == [
            "date,metric,score",
            "2026-05-20,product,100",
        ]


async def _create_recipe(session, namespace="shop_dashboard", key="overview"):
    repo = AgentRecipeRepository(session)
    return await repo.create(
        {
            "namespace": namespace,
            "key": key,
            "entrypoint": {"url": "https://example.com"},
            "steps": [],
            "observations": {
                "score_table": {"id": "score_table", "kind": "table"},
                "summary": {"id": "summary", "kind": "text"},
            },
            "assertions": [],
            "recovery_policy": {},
            "security_policy": {},
        }
    )
