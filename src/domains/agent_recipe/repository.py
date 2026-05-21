from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agent_recipe.models import (
    AGENT_RECIPE_STATUS_ACTIVE,
    AGENT_RECIPE_STATUS_DEGRADED,
    AGENT_RECIPE_STATUS_DISABLED,
    AGENT_RECIPE_STABILITY_CANDIDATE,
    AGENT_RECIPE_STABILITY_STABLE,
    AgentRecipe,
)
from src.shared.repository import BaseRepository


class AgentRecipeRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def create(self, data: dict) -> AgentRecipe:
        recipe = AgentRecipe(**data)
        await self._add(recipe)
        await self.session.refresh(recipe)
        return recipe

    async def get_by_id(self, recipe_id: int) -> AgentRecipe | None:
        stmt = select(AgentRecipe).where(AgentRecipe.id == recipe_id).limit(1)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_versions(self, namespace: str, key: str) -> list[AgentRecipe]:
        stmt = (
            select(AgentRecipe)
            .where(
                AgentRecipe.namespace == namespace,
                AgentRecipe.key == key,
            )
            .order_by(desc(AgentRecipe.version), desc(AgentRecipe.id))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_active(self, namespace: str, key: str) -> AgentRecipe | None:
        stmt = (
            select(AgentRecipe)
            .where(
                AgentRecipe.namespace == namespace,
                AgentRecipe.key == key,
                AgentRecipe.status == AGENT_RECIPE_STATUS_ACTIVE,
            )
            .order_by(desc(AgentRecipe.version), desc(AgentRecipe.id))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_stable_active(self, namespace: str, key: str) -> AgentRecipe | None:
        stmt = (
            select(AgentRecipe)
            .where(
                AgentRecipe.namespace == namespace,
                AgentRecipe.key == key,
                AgentRecipe.status == AGENT_RECIPE_STATUS_ACTIVE,
                AgentRecipe.stability == AGENT_RECIPE_STABILITY_STABLE,
            )
            .order_by(desc(AgentRecipe.version), desc(AgentRecipe.id))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_active_for_update(
        self,
        namespace: str,
        key: str,
    ) -> AgentRecipe | None:
        stmt = (
            select(AgentRecipe)
            .where(
                AgentRecipe.namespace == namespace,
                AgentRecipe.key == key,
                AgentRecipe.status == AGENT_RECIPE_STATUS_ACTIVE,
            )
            .order_by(desc(AgentRecipe.version), desc(AgentRecipe.id))
            .limit(1)
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def create_next_version(
        self,
        *,
        current_recipe: AgentRecipe,
        data: dict,
    ) -> AgentRecipe:
        next_recipe = AgentRecipe(
            namespace=current_recipe.namespace,
            key=current_recipe.key,
            version=(current_recipe.version or 0) + 1,
            status=AGENT_RECIPE_STATUS_ACTIVE,
            stability=AGENT_RECIPE_STABILITY_CANDIDATE,
            entrypoint=data["entrypoint"],
            steps=data["steps"],
            observations=data["observations"],
            assertions=data["assertions"],
            recovery_policy=data["recovery_policy"],
            security_policy=data["security_policy"],
        )

        async def _create():
            current_recipe.status = AGENT_RECIPE_STATUS_DISABLED
            self.session.add(next_recipe)
            return next_recipe

        await self._tx(_create)
        await self.session.refresh(next_recipe)
        return next_recipe

    async def mark_degraded(
        self,
        *,
        recipe_id: int,
        expected_version: int,
        reason: str,
    ) -> bool:
        recipe = await self.get_by_id(recipe_id)
        if (
            recipe is None
            or recipe.version != expected_version
            or recipe.status != AGENT_RECIPE_STATUS_ACTIVE
        ):
            return False

        current_active = await self.get_active_for_update(recipe.namespace, recipe.key)
        if current_active is None or current_active.id != recipe.id:
            return False

        recipe.status = AGENT_RECIPE_STATUS_DEGRADED
        recipe.stability = AGENT_RECIPE_STABILITY_CANDIDATE
        _ = reason
        await self._flush()
        return True

    async def mark_stable(
        self,
        *,
        recipe_id: int,
        expected_version: int,
    ) -> bool:
        recipe = await self.get_by_id(recipe_id)
        if (
            recipe is None
            or recipe.version != expected_version
            or recipe.status != AGENT_RECIPE_STATUS_ACTIVE
        ):
            return False

        current_active = await self.get_active_for_update(recipe.namespace, recipe.key)
        if current_active is None or current_active.id != recipe.id:
            return False

        recipe.stability = AGENT_RECIPE_STABILITY_STABLE
        await self._flush()
        return True
