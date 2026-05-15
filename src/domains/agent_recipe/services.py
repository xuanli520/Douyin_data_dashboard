from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_recipe.schemas import (
    AgentRecipeCreate,
    AgentRecipeMarkDegraded,
    AgentRecipeResponse,
    AgentRecipeVersionCreate,
)
from src.session import get_session


class AgentRecipeService:
    def __init__(
        self,
        session: AsyncSession,
        recipe_repo: AgentRecipeRepository | None = None,
    ):
        self.session = session
        self.recipe_repo = recipe_repo or AgentRecipeRepository(session=session)

    async def create(self, data: AgentRecipeCreate) -> AgentRecipeResponse:
        recipe = await self.recipe_repo.create(data.model_dump())
        await self._commit()
        return AgentRecipeResponse.model_validate(recipe)

    async def get_active(
        self,
        namespace: str,
        key: str,
    ) -> AgentRecipeResponse | None:
        recipe = await self.recipe_repo.get_active(namespace, key)
        if recipe is None:
            if self.session.in_transaction():
                await self.session.rollback()
            return None
        return AgentRecipeResponse.model_validate(recipe)

    async def list_versions(
        self,
        namespace: str,
        key: str,
    ) -> list[AgentRecipeResponse]:
        recipes = await self.recipe_repo.list_versions(namespace, key)
        if not recipes and self.session.in_transaction():
            await self.session.rollback()
        return [AgentRecipeResponse.model_validate(item) for item in recipes]

    async def create_next_version(
        self,
        data: AgentRecipeVersionCreate,
    ) -> AgentRecipeResponse | None:
        current_recipe = await self.recipe_repo.get_active_for_update(
            data.namespace,
            data.key,
        )
        if (
            current_recipe is None
            or current_recipe.version != data.expected_version
        ):
            if self.session.in_transaction():
                await self.session.rollback()
            return None

        recipe = await self.recipe_repo.create_next_version(
            current_recipe=current_recipe,
            data=data.model_dump(
                exclude={
                    "namespace",
                    "key",
                    "expected_version",
                }
            ),
        )
        await self._commit()
        return AgentRecipeResponse.model_validate(recipe)

    async def mark_degraded(self, data: AgentRecipeMarkDegraded) -> bool:
        updated = await self.recipe_repo.mark_degraded(
            recipe_id=data.recipe_id,
            expected_version=data.expected_version,
            reason=data.reason,
        )
        if not updated:
            if self.session.in_transaction():
                await self.session.rollback()
            return False
        await self._commit()
        return True

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise


async def get_agent_recipe_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AgentRecipeService, None]:
    yield AgentRecipeService(session=session)

