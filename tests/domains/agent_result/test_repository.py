from datetime import date

from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_result.repository import AgentResultRepository


async def test_agent_result_upsert_creates_and_updates(test_db):
    async with test_db() as session:
        recipe = await _create_recipe(session)
        repo = AgentResultRepository(session)

        created = await repo.upsert(
            namespace="shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 21),
            recipe_id=recipe.id,
            output={"summary": "old"},
        )
        updated = await repo.upsert(
            namespace="shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 21),
            recipe_id=recipe.id,
            output={"summary": "new"},
            status="recovered",
        )

        assert created.id == updated.id
        assert updated.output == {"summary": "new"}
        assert updated.status == "recovered"


async def test_agent_result_query_filters_and_counts(test_db):
    async with test_db() as session:
        recipe = await _create_recipe(session)
        repo = AgentResultRepository(session)
        await repo.upsert(
            namespace="shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 20),
            recipe_id=recipe.id,
            output={"day": "20"},
        )
        await repo.upsert(
            namespace="shop_dashboard",
            resource_key="1001",
            resource_date=date(2026, 5, 21),
            recipe_id=recipe.id,
            output={"day": "21"},
        )
        await repo.upsert(
            namespace="shop_dashboard",
            resource_key="1002",
            resource_date=date(2026, 5, 21),
            recipe_id=recipe.id,
            output={"day": "other"},
        )

        rows, total = await repo.query_results(
            namespace="shop_dashboard",
            resource_key="1001",
            date_from=date(2026, 5, 21),
            date_to=date(2026, 5, 21),
        )

        assert total == 1
        assert [row.output for row in rows] == [{"day": "21"}]


async def test_agent_result_list_by_date_range_orders_ascending(test_db):
    async with test_db() as session:
        recipe = await _create_recipe(session)
        repo = AgentResultRepository(session)
        for day in (date(2026, 5, 22), date(2026, 5, 20), date(2026, 5, 21)):
            await repo.upsert(
                namespace="shop_dashboard",
                resource_key="1001",
                resource_date=day,
                recipe_id=recipe.id,
                output={"day": day.isoformat()},
            )

        rows = await repo.list_by_date_range(
            namespace="shop_dashboard",
            resource_key="1001",
            date_from=date(2026, 5, 20),
            date_to=date(2026, 5, 21),
        )

        assert [row.resource_date for row in rows] == [
            date(2026, 5, 20),
            date(2026, 5, 21),
        ]


async def _create_recipe(session):
    repo = AgentRecipeRepository(session)
    return await repo.create(
        {
            "namespace": "shop_dashboard",
            "key": "overview",
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
