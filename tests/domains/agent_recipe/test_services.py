from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_recipe.schemas import (
    AgentRecipeCreate,
    AgentRecipeMarkDegraded,
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


class TestAgentRecipeServiceIntegration:
    async def test_create_and_get_active(self, test_db):
        async with test_db() as session:
            service = AgentRecipeService(session=session)
            created = await service.create(
                AgentRecipeCreate(
                    namespace="shop_dashboard",
                    key="overview",
                    **_recipe_payload(),
                )
            )

            active = await service.get_active("shop_dashboard", "overview")

            assert created.id > 0
            assert active is not None
            assert active.id == created.id
            assert active.version == 1

    async def test_create_next_version_returns_none_on_stale_expected_version(
        self,
        test_db,
    ):
        async with test_db() as session:
            service = AgentRecipeService(session=session)
            await service.create(
                AgentRecipeCreate(
                    namespace="shop_dashboard",
                    key="overview",
                    **_recipe_payload(),
                )
            )

            created = await service.create_next_version(
                AgentRecipeVersionCreate(
                    namespace="shop_dashboard",
                    key="overview",
                    expected_version=1,
                    entrypoint={"url": "https://example.com/v2"},
                    steps=[{"action": "goto", "target": "metrics"}],
                    observations={"gmv": {"locator": "#gmv"}},
                    assertions=[{"type": "exists", "observation": "gmv"}],
                    recovery_policy={"max_attempts": 2},
                    security_policy={"allowed_domains": ["example.com"]},
                )
            )
            stale = await service.create_next_version(
                AgentRecipeVersionCreate(
                    namespace="shop_dashboard",
                    key="overview",
                    expected_version=1,
                    entrypoint={"url": "https://example.com/v3"},
                    steps=[{"action": "goto", "target": "orders"}],
                    observations={"orders": {"locator": "#orders"}},
                    assertions=[{"type": "exists", "observation": "orders"}],
                    recovery_policy={"max_attempts": 3},
                    security_policy={"allowed_domains": ["example.com"]},
                )
            )

            repo = AgentRecipeRepository(session)
            active = await repo.get_active("shop_dashboard", "overview")

            assert created is not None
            assert created.version == 2
            assert stale is None
            assert active is not None
            assert active.version == 2

    async def test_mark_degraded_updates_active_version(self, test_db):
        async with test_db() as session:
            service = AgentRecipeService(session=session)
            created = await service.create(
                AgentRecipeCreate(
                    namespace="shop_dashboard",
                    key="overview",
                    **_recipe_payload(),
                )
            )

            updated = await service.mark_degraded(
                AgentRecipeMarkDegraded(
                    recipe_id=created.id,
                    expected_version=1,
                    reason="assertion_failed",
                )
            )
            active = await service.get_active("shop_dashboard", "overview")

            assert updated is True
            assert active is None
