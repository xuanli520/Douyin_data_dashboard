import pytest

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
            assert active.stability == "candidate"

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
                    steps=[{"id": "open", "action": "goto"}],
                    observations={
                        "gmv": {
                            "id": "gmv",
                            "kind": "text",
                            "locator": {"kind": "css", "value": "#gmv"},
                        }
                    },
                    assertions=[
                        {"id": "gmv_exists", "kind": "exists", "source": "gmv"}
                    ],
                    recovery_policy={"max_attempts": 2},
                    security_policy={"allowed_origins": ["https://example.com"]},
                )
            )
            stale = await service.create_next_version(
                AgentRecipeVersionCreate(
                    namespace="shop_dashboard",
                    key="overview",
                    expected_version=1,
                    entrypoint={"url": "https://example.com/v3"},
                    steps=[{"id": "open", "action": "goto"}],
                    observations={
                        "orders": {
                            "id": "orders",
                            "kind": "text",
                            "locator": {"kind": "css", "value": "#orders"},
                        }
                    },
                    assertions=[
                        {"id": "orders_exists", "kind": "exists", "source": "orders"}
                    ],
                    recovery_policy={"max_attempts": 3},
                    security_policy={"allowed_origins": ["https://example.com"]},
                )
            )

            repo = AgentRecipeRepository(session)
            active = await repo.get_active("shop_dashboard", "overview")

            assert created is not None
            assert created.version == 2
            assert created.stability == "candidate"
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

    async def test_mark_stable_promotes_active_version(self, test_db):
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
            stable = await service.get_stable_active("shop_dashboard", "overview")

            assert updated is True
            assert stable is not None
            assert stable.id == created.id
            assert stable.stability == "stable"

    async def test_get_stable_active_skips_invalid_stable_versions(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            valid = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 1,
                    "status": "active",
                    "stability": "stable",
                    **_recipe_payload(),
                }
            )
            await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "version": 2,
                    "status": "active",
                    "stability": "stable",
                    "entrypoint": {"url": "https://example.com"},
                    "steps": [{"id": "open", "action": "goto"}],
                    "observations": {},
                    "assertions": [],
                    "recovery_policy": {},
                    "security_policy": {"allowed_origins": ["https://example.com"]},
                }
            )
            await session.commit()
            service = AgentRecipeService(session=session)

            stable = await service.get_stable_active("shop_dashboard", "overview")

            assert stable is not None
            assert stable.id == valid.id
            assert stable.version == 1

    async def test_mark_stable_rejects_invalid_existing_recipe(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            invalid = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "entrypoint": {"url": "https://example.com"},
                    "steps": [{"action": "goto"}],
                    "observations": {},
                    "assertions": [],
                    "recovery_policy": {},
                    "security_policy": {"allowed_origins": ["https://example.com"]},
                }
            )
            await session.commit()
            service = AgentRecipeService(session=session)

            with pytest.raises(ValueError):
                await service.mark_stable(
                    AgentRecipeMarkStable(
                        recipe_id=invalid.id,
                        expected_version=invalid.version,
                    )
                )

    async def test_mark_stable_rejects_recipe_without_observations(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            invalid = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "entrypoint": {"url": "https://example.com"},
                    "steps": [{"id": "open", "action": "goto"}],
                    "observations": {},
                    "assertions": [],
                    "recovery_policy": {},
                    "security_policy": {"allowed_origins": ["https://example.com"]},
                }
            )
            await session.commit()
            service = AgentRecipeService(session=session)

            with pytest.raises(ValueError):
                await service.mark_stable(
                    AgentRecipeMarkStable(
                        recipe_id=invalid.id,
                        expected_version=invalid.version,
                    )
                )

    async def test_mark_stable_rejects_shop_score_without_number_parser(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            payload = _shop_score_payload()
            payload["observations"]["total_score"]["parser"] = "text"
            invalid = await repo.create(payload)
            await session.commit()
            service = AgentRecipeService(session=session)

            with pytest.raises(
                ValueError,
                match="agent recipe score observations must use number parser",
            ):
                await service.mark_stable(
                    AgentRecipeMarkStable(
                        recipe_id=invalid.id,
                        expected_version=invalid.version,
                    )
                )

    async def test_list_recipes_reports_invalid_stable_recipe(self, test_db):
        async with test_db() as session:
            repo = AgentRecipeRepository(session)
            invalid = await repo.create(
                {
                    "namespace": "shop_dashboard",
                    "key": "overview",
                    "status": "active",
                    "stability": "stable",
                    "entrypoint": {"url": "https://example.com"},
                    "steps": [{"id": "open", "action": "goto"}],
                    "observations": {},
                    "assertions": [],
                    "recovery_policy": {},
                    "security_policy": {"allowed_origins": ["https://example.com"]},
                }
            )
            await session.commit()
            service = AgentRecipeService(session=session)

            recipes = await service.list_recipes()

            item = next(item for item in recipes["items"] if item["id"] == invalid.id)
            assert item["validation_error"] == (
                "agent recipe observations are required before stable"
            )


def _shop_score_payload() -> dict:
    fields = (
        "total_score",
        "product_score",
        "logistics_score",
        "service_score",
        "bad_behavior_score",
    )
    return {
        "namespace": "douyin_shop_dashboard",
        "key": "experience_score_single_page",
        "entrypoint": {"url": "https://fxg.jinritemai.com/tps/score/home"},
        "steps": [{"id": "open", "action": "goto"}],
        "observations": {
            field: {
                "id": field,
                "kind": "text",
                "locator": {"kind": "css", "value": f"#{field}"},
                "parser": "number",
                "required": True,
            }
            for field in fields
        },
        "assertions": [
            {"id": f"{field}_required", "kind": "not_empty", "source": field}
            for field in fields
        ],
        "recovery_policy": {"max_attempts": 1},
        "security_policy": {"allowed_origins": ["https://fxg.jinritemai.com"]},
    }
