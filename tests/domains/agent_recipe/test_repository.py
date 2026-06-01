from src.domains.agent_recipe.models import (
    AGENT_RECIPE_STATUS_ACTIVE,
    AGENT_RECIPE_STATUS_DEGRADED,
    AGENT_RECIPE_STATUS_DISABLED,
    AGENT_RECIPE_STABILITY_CANDIDATE,
    AGENT_RECIPE_STABILITY_STABLE,
)
from src.domains.agent_recipe.repository import AgentRecipeRepository


def _recipe_payload() -> dict:
    return {
        "entrypoint": {"url": "https://example.com"},
        "steps": [{"action": "goto", "target": "dashboard"}],
        "observations": {"shop_name": {"locator": "#shop-name"}},
        "assertions": [{"type": "exists", "observation": "shop_name"}],
        "recovery_policy": {"max_attempts": 1},
        "security_policy": {"allowed_domains": ["example.com"]},
    }


class TestAgentRecipeRepositoryIntegration:
    async def test_create_and_get_active(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            created = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    **_recipe_payload(),
                }
            )

            active = await repo.get_active("shop_dashboard", "overview")

            assert created.id is not None
            assert active is not None
            assert active.id == created.id
            assert active.status == AGENT_RECIPE_STATUS_ACTIVE
            assert active.stability == AGENT_RECIPE_STABILITY_CANDIDATE

    async def test_get_active_returns_highest_active_version(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 1,
                    "status": AGENT_RECIPE_STATUS_DISABLED,
                    **_recipe_payload(),
                }
            )
            await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 2,
                    "status": AGENT_RECIPE_STATUS_ACTIVE,
                    **_recipe_payload(),
                }
            )
            await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 3,
                    "status": AGENT_RECIPE_STATUS_ACTIVE,
                    **_recipe_payload(),
                }
            )

            active = await repo.get_active("shop_dashboard", "overview")
            stable = await repo.get_stable_active("shop_dashboard", "overview")

            assert active is not None
            assert active.version == 3
            assert stable is None

    async def test_get_active_version_requires_requested_active_version(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 1,
                    "status": AGENT_RECIPE_STATUS_DISABLED,
                    **_recipe_payload(),
                }
            )
            await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 2,
                    "status": AGENT_RECIPE_STATUS_ACTIVE,
                    **_recipe_payload(),
                }
            )

            disabled = await repo.get_active_version("shop_dashboard", "overview", 1)
            active = await repo.get_active_version("shop_dashboard", "overview", 2)

            assert disabled is None
            assert active is not None
            assert active.version == 2

    async def test_get_stable_active_returns_highest_stable_version(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 1,
                    "stability": AGENT_RECIPE_STABILITY_STABLE,
                    **_recipe_payload(),
                }
            )
            await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 2,
                    **_recipe_payload(),
                }
            )

            stable = await repo.get_stable_active("shop_dashboard", "overview")

            assert stable is not None
            assert stable.version == 1
            assert stable.stability == AGENT_RECIPE_STABILITY_STABLE

    async def test_create_next_candidate_keeps_current_active(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            created = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    **_recipe_payload(),
                }
            )

            current = await repo.get_active_for_update("shop_dashboard", "overview")
            next_recipe = await repo.create_next_version(
                current_recipe=current,
                data={
                    "entrypoint": {"url": "https://example.com/next"},
                    "steps": [{"action": "goto", "target": "trend"}],
                    "observations": {"gmv": {"locator": "#gmv"}},
                    "assertions": [{"type": "exists", "observation": "gmv"}],
                    "recovery_policy": {"max_attempts": 2},
                    "security_policy": {"allowed_domains": ["example.com"]},
                },
            )
            await session.commit()

            previous = await repo.get_by_id(created.id if created.id is not None else 0)
            active = await repo.get_active("shop_dashboard", "overview")
            versions = await repo.list_versions("shop_dashboard", "overview")

            assert next_recipe.version == 2
            assert next_recipe.stability == AGENT_RECIPE_STABILITY_CANDIDATE
            assert previous is not None
            assert previous.status == AGENT_RECIPE_STATUS_ACTIVE
            assert active is not None
            assert active.id == next_recipe.id
            assert [item.version for item in versions] == [2, 1]

    async def test_create_next_stable_keeps_current_active_for_pinned_versions(
        self,
        test_db,
    ):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            created = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    **_recipe_payload(),
                }
            )

            current = await repo.get_active_for_update("shop_dashboard", "overview")
            next_recipe = await repo.create_next_version(
                current_recipe=current,
                data={
                    "entrypoint": {"url": "https://example.com/next"},
                    "steps": [{"action": "goto", "target": "trend"}],
                    "observations": {"gmv": {"locator": "#gmv"}},
                    "assertions": [{"type": "exists", "observation": "gmv"}],
                    "recovery_policy": {"max_attempts": 2},
                    "security_policy": {"allowed_domains": ["example.com"]},
                    "stability": AGENT_RECIPE_STABILITY_STABLE,
                },
            )
            await session.commit()

            previous = await repo.get_by_id(created.id if created.id is not None else 0)

            assert next_recipe.version == 2
            assert next_recipe.stability == AGENT_RECIPE_STABILITY_STABLE
            assert previous is not None
            assert previous.status == AGENT_RECIPE_STATUS_ACTIVE

    async def test_mark_degraded_updates_only_current_active_version(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            current = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    **_recipe_payload(),
                }
            )

            updated = await repo.mark_degraded(
                recipe_id=current.id if current.id is not None else 0,
                expected_version=1,
                reason="replay_failed",
            )
            await session.commit()

            stored = await repo.get_by_id(current.id if current.id is not None else 0)
            active = await repo.get_active("shop_dashboard", "overview")

            assert updated is True
            assert stored is not None
            assert stored.status == AGENT_RECIPE_STATUS_DEGRADED
            assert stored.stability == AGENT_RECIPE_STABILITY_CANDIDATE
            assert active is None

    async def test_mark_stable_updates_current_active_version(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            current = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    **_recipe_payload(),
                }
            )

            updated = await repo.mark_stable(
                recipe_id=current.id if current.id is not None else 0,
                expected_version=1,
            )
            await session.commit()

            stable = await repo.get_stable_active("shop_dashboard", "overview")

            assert updated is True
            assert stable is not None
            assert stable.id == current.id
            assert stable.stability == AGENT_RECIPE_STABILITY_STABLE
