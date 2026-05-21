from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_recipe.schemas import (
    AgentRecipeCreate,
    AgentRecipeMarkDegraded,
    AgentRecipeMarkStable,
    AgentRecipeVersionCreate,
)
from src.domains.agent_recipe.services import AgentRecipeService


def _recipe_payload() -> dict:
    return {
        "entrypoint": {"url": "https://example.com"},
        "steps": [{"action": "goto", "target": "dashboard"}],
        "observations": {"shop_name": {"locator": "#shop-name"}},
        "assertions": [{"type": "exists", "observation": "shop_name"}],
        "recovery_policy": {"max_attempts": 1},
        "security_policy": {"allowed_domains": ["example.com"]},
    }


async def test_agent_recipe_versioning_flow(test_db):
    async with test_db() as session:
        service = AgentRecipeService(session=session)
        created = await service.create(
            AgentRecipeCreate(
                namespace="shop_dashboard",
                key="overview",
                **_recipe_payload(),
            )
        )

        upgraded = await service.create_next_version(
            AgentRecipeVersionCreate(
                namespace="shop_dashboard",
                key="overview",
                expected_version=created.version,
                entrypoint={"url": "https://example.com/v2"},
                steps=[{"action": "goto", "target": "trend"}],
                observations={"trend": {"locator": "#trend"}},
                assertions=[{"type": "exists", "observation": "trend"}],
                recovery_policy={"max_attempts": 2},
                security_policy={"allowed_domains": ["example.com"]},
            )
        )

        repo = AgentRecipeRepository(session)
        active = await repo.get_active("shop_dashboard", "overview")
        versions = await repo.list_versions("shop_dashboard", "overview")

        assert upgraded is not None
        assert upgraded.version == 2
        assert upgraded.stability == "candidate"
        assert active is not None
        assert active.id == upgraded.id
        assert [item.version for item in versions] == [2, 1]


async def test_agent_recipe_mark_degraded_keeps_prior_versions(test_db):
    async with test_db() as session:
        service = AgentRecipeService(session=session)
        created = await service.create(
            AgentRecipeCreate(
                namespace="shop_dashboard",
                key="overview",
                **_recipe_payload(),
            )
        )

        degraded = await service.mark_degraded(
            AgentRecipeMarkDegraded(
                recipe_id=created.id,
                expected_version=created.version,
                reason="locator_not_found",
            )
        )

        repo = AgentRecipeRepository(session)
        active = await repo.get_active("shop_dashboard", "overview")
        versions = await repo.list_versions("shop_dashboard", "overview")

        assert degraded is True
        assert active is None
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].stability == "candidate"


async def test_agent_recipe_mark_stable_allows_stable_lookup(test_db):
    async with test_db() as session:
        service = AgentRecipeService(session=session)
        created = await service.create(
            AgentRecipeCreate(
                namespace="shop_dashboard",
                key="overview",
                **_recipe_payload(),
            )
        )

        updated = await service.mark_stable(
            AgentRecipeMarkStable(
                recipe_id=created.id,
                expected_version=created.version,
            )
        )

        repo = AgentRecipeRepository(session)
        stable = await repo.get_stable_active("shop_dashboard", "overview")

        assert updated is True
        assert stable is not None
        assert stable.id == created.id
        assert stable.stability == "stable"
