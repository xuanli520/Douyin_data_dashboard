from collections.abc import AsyncGenerator
import json
from typing import Any

from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_recipe.schemas import (
    AgentRecipeCreate,
    AgentRecipeDocument,
    AgentRecipeExportPayload,
    AgentRecipeImportResponse,
    AgentRecipeMarkDegraded,
    AgentRecipeMarkStable,
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

    async def get_stable_active(
        self,
        namespace: str,
        key: str,
    ) -> AgentRecipeResponse | None:
        recipe = await self.recipe_repo.get_stable_active(namespace, key)
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
        if current_recipe is None or current_recipe.version != data.expected_version:
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

    async def mark_stable(self, data: AgentRecipeMarkStable) -> bool:
        updated = await self.recipe_repo.mark_stable(
            recipe_id=data.recipe_id,
            expected_version=data.expected_version,
        )
        if not updated:
            if self.session.in_transaction():
                await self.session.rollback()
            return False
        await self._commit()
        return True

    async def export_recipe(
        self,
        recipe_id: int,
    ) -> tuple[dict[str, Any], str] | None:
        recipe = await self.recipe_repo.get_by_id(recipe_id)
        if recipe is None:
            if self.session.in_transaction():
                await self.session.rollback()
            return None
        document = AgentRecipeDocument(
            namespace=recipe.namespace,
            key=recipe.key,
            version=recipe.version,
            entrypoint=recipe.entrypoint,
            steps=recipe.steps,
            observations=recipe.observations,
            assertions=recipe.assertions,
            recovery_policy=recipe.recovery_policy,
            security_policy=recipe.security_policy,
        )
        payload = AgentRecipeExportPayload(recipe=document).model_dump(mode="json")
        filename = (
            f"{recipe.namespace}_{recipe.key}_v{recipe.version}.agent-recipe.json"
        )
        return payload, filename

    async def import_recipe(
        self, content: bytes | str
    ) -> AgentRecipeImportResponse | None:
        payload = _load_export_payload(content)
        document = payload.recipe
        existing = await self.recipe_repo.list_versions(
            document.namespace, document.key
        )
        if any(item.version == document.version for item in existing):
            if self.session.in_transaction():
                await self.session.rollback()
            return None
        recipe = await self.recipe_repo.create(
            AgentRecipeCreate(
                namespace=document.namespace,
                key=document.key,
                version=document.version,
                entrypoint=document.entrypoint,
                steps=document.steps,
                observations=document.observations,
                assertions=document.assertions,
                recovery_policy=document.recovery_policy,
                security_policy=document.security_policy,
            ).model_dump()
        )
        await self._commit()
        return AgentRecipeImportResponse(
            id=recipe.id or 0,
            namespace=recipe.namespace,
            key=recipe.key,
            version=recipe.version,
            status=recipe.status,
            stability=recipe.stability,
        )

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


def _load_export_payload(content: bytes | str) -> AgentRecipeExportPayload:
    text = content.decode("utf-8") if isinstance(content, bytes) else content
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid agent recipe json") from exc
    try:
        return AgentRecipeExportPayload.model_validate(_normalize_recipe_export(raw))
    except ValidationError as exc:
        raise ValueError("invalid agent recipe payload") from exc


def _normalize_recipe_export(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    payload = dict(raw)
    recipe = payload.get("recipe")
    if isinstance(recipe, dict):
        payload["recipe"] = _normalize_recipe_document(recipe)
    return payload


def _normalize_recipe_document(recipe: dict[str, Any]) -> dict[str, Any]:
    payload = dict(recipe)
    payload.pop("id", None)
    payload.pop("recipe_id", None)
    payload.pop("status", None)
    payload.pop("stability", None)
    payload.pop("created_at", None)
    payload.pop("updated_at", None)
    entrypoint = payload.get("entrypoint")
    if (
        isinstance(entrypoint, dict)
        and "url_template" in entrypoint
        and "url" not in entrypoint
    ):
        normalized_entrypoint = dict(entrypoint)
        normalized_entrypoint["url"] = normalized_entrypoint.pop("url_template")
        payload["entrypoint"] = normalized_entrypoint
    return payload
