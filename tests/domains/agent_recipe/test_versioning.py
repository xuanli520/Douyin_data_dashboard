from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_recipe.schemas import AgentRecipeCreate, AgentRecipeVersionCreate
from src.domains.agent_recipe.services import AgentRecipeService


def _recipe_payload() -> dict:
    return {
        "entrypoint": {"url": "https://example.com"},
        "steps": [{"id": "open", "action": "goto"}],
        "observations": {
            "shop_name": {
                "id": "shop_name",
                "kind": "text",
                "locator": {"kind": "css", "value": "#shop-name"},
            }
        },
        "assertions": [
            {"id": "shop_name_exists", "kind": "exists", "source": "shop_name"}
        ],
        "recovery_policy": {"max_attempts": 1},
        "security_policy": {"allowed_origins": ["https://example.com"]},
    }


async def test_agent_recipe_version_rows_are_append_only(test_db):
    async with test_db() as session:
        service = AgentRecipeService(session=session)
        created = await service.create(
            AgentRecipeCreate(
                namespace="shop_dashboard",
                key="overview",
                **_recipe_payload(),
            )
        )

        second = await service.create_next_version(
            AgentRecipeVersionCreate(
                namespace="shop_dashboard",
                key="overview",
                expected_version=1,
                entrypoint={"url": "https://example.com/v2"},
                steps=[{"id": "open", "action": "goto"}],
                observations={
                    "summary": {
                        "id": "summary",
                        "kind": "text",
                        "locator": {"kind": "css", "value": "#summary"},
                    }
                },
                assertions=[
                    {"id": "summary_exists", "kind": "exists", "source": "summary"}
                ],
                recovery_policy={"max_attempts": 2},
                security_policy={"allowed_origins": ["https://example.com"]},
            )
        )

        repo = AgentRecipeRepository(session)
        versions = await repo.list_versions("shop_dashboard", "overview")

        assert created.version == 1
        assert created.stability == "candidate"
        assert second is not None
        assert second.version == 2
        assert second.stability == "candidate"
        assert len(versions) == 2
        assert {item.version for item in versions} == {1, 2}
