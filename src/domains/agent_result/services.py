from __future__ import annotations

import csv
import io
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agent_recipe.repository import AgentRecipeRepository
from src.domains.agent_result.models import AgentCollectionResult
from src.domains.agent_result.repository import AgentResultRepository
from src.domains.agent_result.schemas import (
    AgentResultListResponse,
    AgentResultResponse,
)
from src.session import get_session


class AgentResultService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentResultRepository(session)

    async def list_results(
        self,
        *,
        namespace: str | None = None,
        resource_key: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        size: int = 50,
    ) -> AgentResultListResponse:
        normalized_page = max(page, 1)
        normalized_size = max(size, 1)
        rows, total = await self.repo.query_results(
            namespace=namespace,
            resource_key=resource_key,
            date_from=date_from,
            date_to=date_to,
            offset=(normalized_page - 1) * normalized_size,
            limit=normalized_size,
        )
        return AgentResultListResponse(
            items=[AgentResultResponse.model_validate(row) for row in rows],
            total=total,
            page=normalized_page,
            size=normalized_size,
        )

    async def get_result(self, result_id: int) -> AgentResultResponse | None:
        row = await self.repo.get_by_id(result_id)
        if row is None:
            return None
        return AgentResultResponse.model_validate(row)

    async def build_csv(
        self,
        *,
        namespace: str,
        resource_key: str,
        date_from: date,
        date_to: date,
    ) -> tuple[str, str]:
        rows = await self.repo.list_by_date_range(
            namespace=namespace,
            resource_key=resource_key,
            date_from=date_from,
            date_to=date_to,
        )
        csv_content = await self._build_csv_from_rows(rows)
        filename = (
            f"{namespace}_{resource_key}_{date_from.isoformat()}_"
            f"{date_to.isoformat()}.csv"
        )
        return csv_content, filename

    async def build_csv_by_recipe_key(
        self,
        *,
        namespace: str,
        resource_key: str,
        recipe_key: str,
        date_from: date,
        date_to: date,
    ) -> tuple[str, str]:
        rows = await self.repo.list_by_recipe_key(
            namespace=namespace,
            resource_key=resource_key,
            recipe_key=recipe_key,
            date_from=date_from,
            date_to=date_to,
        )
        csv_content = await self._build_csv_from_rows(rows)
        filename = (
            f"{namespace}_{resource_key}_{recipe_key}_{date_from.isoformat()}_"
            f"{date_to.isoformat()}.csv"
        )
        return csv_content, filename

    async def _build_csv_from_rows(
        self,
        rows: list[AgentCollectionResult],
    ) -> str:
        recipe_repo = AgentRecipeRepository(self.session)
        recipe_cache: dict[int, dict[str, Any]] = {}
        csv_rows: list[dict[str, Any]] = []
        headers = ["date"]

        for result in rows:
            if result.recipe_id not in recipe_cache:
                recipe = await recipe_repo.get_by_id(result.recipe_id)
                recipe_cache[result.recipe_id] = dict(
                    recipe.observations if recipe else {}
                )
            observation_id = _first_table_observation(
                observations=recipe_cache[result.recipe_id],
                output=result.output,
            )
            if observation_id is None:
                continue
            for row in _table_rows(result.output.get(observation_id)):
                csv_row = {"date": result.resource_date.isoformat(), **row}
                for key in csv_row:
                    if key not in headers:
                        headers.append(key)
                csv_rows.append(csv_row)

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)
        return buffer.getvalue()


async def get_agent_result_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AgentResultService, None]:
    yield AgentResultService(session=session)


def _first_table_observation(
    *,
    observations: dict[str, Any],
    output: dict[str, Any],
) -> str | None:
    for observation_id, spec in observations.items():
        spec_data = spec.model_dump() if hasattr(spec, "model_dump") else spec
        if isinstance(spec_data, dict) and spec_data.get("kind") == "table":
            if observation_id in output:
                return observation_id
    for observation_id, value in output.items():
        if _table_rows(value):
            return observation_id
    return None


def _table_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return _structured_table_rows(value)
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            return [dict(item) for item in value]
        if all(isinstance(item, list | tuple) for item in value):
            rows = [list(item) for item in value]
            if not rows:
                return []
            headers = [str(item).strip() for item in rows[0]]
            return [_row_from_cells(headers, row) for row in rows[1:]]
        if all(isinstance(item, str) for item in value):
            return _csv_line_rows(value)
    return []


def _structured_table_rows(value: dict[str, Any]) -> list[dict[str, Any]]:
    headers = [str(item).strip() for item in value.get("headers") or []]
    rows = value.get("rows") or []
    parsed_rows = []
    for row in rows:
        if isinstance(row, dict):
            parsed_rows.append(dict(row))
        elif isinstance(row, list | tuple):
            parsed_rows.append(_row_from_cells(headers, row))
    return parsed_rows


def _csv_line_rows(lines: list[str]) -> list[dict[str, Any]]:
    if not lines:
        return []
    parsed = list(csv.reader(lines))
    if not parsed:
        return []
    headers = [cell.strip() for cell in parsed[0]]
    return [_row_from_cells(headers, row) for row in parsed[1:]]


def _row_from_cells(
    headers: list[str], cells: list[Any] | tuple[Any, ...]
) -> dict[str, Any]:
    return {
        header: "" if cell is None else str(cell)
        for header, cell in zip(headers, cells, strict=False)
        if header
    }
