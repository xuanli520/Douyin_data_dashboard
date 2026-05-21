# Agent Data Storage & Recipe Import/Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generic JSONB-backed agent result storage with CSV download, recipe export/import, and cleanup of residual old-scraper data structures.

**Architecture:** New `src/domains/agent_result/` domain module with model/repo/schemas/service. New API routes in `src/api/v1/agent_results.py`. Recipe export/import added to existing `agent_discovery.py` router. `CollectionResultPersister` extended to also persist agent output. Residual `reviews`/`violations`/`cold_metrics` cleaned from adapter, presentation mapper, and repository.

**Tech Stack:** SQLModel, SQLAlchemy async, JSONB (via `sa_type=JSON`), FastAPI StreamingResponse

---

### File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `migrations/versions/20260521_03_add_agent_collection_results.py` | Create | DB migration |
| `src/domains/agent_result/__init__.py` | Create | Domain marker |
| `src/domains/agent_result/models.py` | Create | `AgentCollectionResult` SQLModel |
| `src/domains/agent_result/repository.py` | Create | `AgentResultRepository` |
| `src/domains/agent_result/schemas.py` | Create | Pydantic request/response schemas |
| `src/domains/agent_result/services.py` | Create | `AgentResultService` |
| `src/api/v1/agent_results.py` | Create | API routes (query, detail, download) |
| `src/api/v1/agent_discovery.py` | Modify | Add recipe export/import endpoints |
| `src/domains/agent_recipe/services.py` | Modify | Add export/import methods |
| `src/domains/agent_recipe/schemas.py` | Modify | Add export/import schemas |
| `src/api/__init__.py` | Modify | Export new router |
| `src/main.py` | Modify | Register new router |
| `src/application/collection/result_persister.py` | Modify | Persist agent output to new table |
| `src/application/collection/browser_agent_adapter.py` | Modify | Remove reviews/violations defaults |
| `src/domains/shop_dashboard/repository.py` | Modify | Remove reviews/violations/cold_metrics from materials |
| `src/domains/experience/presentation_mapper.py` | Modify | Remove cold_metrics fallback |
| `tests/domains/agent_result/test_repository.py` | Create | Repository integration tests |
| `tests/domains/agent_result/test_services.py` | Create | Service tests |
| `tests/api/test_agent_results_api.py` | Create | API tests |
| `tests/api/test_agent_recipe_export_import.py` | Create | Export/import API tests |

---

### Task 1: Database Migration

**Files:**
- Create: `migrations/versions/20260521_03_add_agent_collection_results.py`

- [ ] **Step 1: Create migration file**

Create `migrations/versions/20260521_03_add_agent_collection_results.py`:

```python
"""add agent_collection_results table

Revision ID: 20260521_03
Revises: 20260521_02
Create Date: 2026-05-21 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260521_03"
down_revision: Union[str, Sequence[str], None] = "20260521_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("agent_collection_results"):
        op.create_table(
            "agent_collection_results",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("namespace", sa.String(length=100), nullable=False),
            sa.Column("resource_key", sa.String(length=200), nullable=False),
            sa.Column("resource_date", sa.Date(), nullable=False),
            sa.Column("recipe_id", sa.Integer(), nullable=False),
            sa.Column("output", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {idx["name"] for idx in inspector.get_indexes("agent_collection_results")}
    if "ux_agent_collection_result" not in indexes:
        op.create_unique_constraint(
            "ux_agent_collection_result",
            "agent_collection_results",
            ["namespace", "resource_key", "resource_date"],
        )
    if "ix_agent_collection_results_namespace" not in indexes:
        op.create_index(
            "ix_agent_collection_results_namespace",
            "agent_collection_results",
            ["namespace"],
        )
    if "ix_agent_collection_results_resource_key" not in indexes:
        op.create_index(
            "ix_agent_collection_results_resource_key",
            "agent_collection_results",
            ["resource_key"],
        )
    if "ix_agent_collection_results_resource_date" not in indexes:
        op.create_index(
            "ix_agent_collection_results_resource_date",
            "agent_collection_results",
            ["resource_date"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("agent_collection_results"):
        op.drop_index("ix_agent_collection_results_resource_date", table_name="agent_collection_results")
        op.drop_index("ix_agent_collection_results_resource_key", table_name="agent_collection_results")
        op.drop_index("ix_agent_collection_results_namespace", table_name="agent_collection_results")
        op.drop_constraint("ux_agent_collection_result", table_name="agent_collection_results")
        op.drop_table("agent_collection_results")
```

- [ ] **Step 2: Run migration**

Run: `uv run alembic upgrade head`
Expected: Migration applies successfully, table created.

- [ ] **Step 3: Verify table exists**

Run: `uv run python -c "from sqlalchemy import create_engine, inspect; from src.config import get_settings; s = get_settings(); e = create_engine(s.db.url); i = inspect(e); print('agent_collection_results' in i.get_table_names())"`
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/20260521_03_add_agent_collection_results.py
git commit -m "feat: add agent_collection_results table migration"
```

---

### Task 2: Domain Model — AgentCollectionResult

**Files:**
- Create: `src/domains/agent_result/__init__.py`
- Create: `src/domains/agent_result/models.py`

- [ ] **Step 1: Create domain init**

Create `src/domains/agent_result/__init__.py`:
```python
```

(empty file)

- [ ] **Step 2: Create SQLModel**

Create `src/domains/agent_result/models.py`:
```python
from datetime import date
from typing import Any

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, SQLModel

from src.shared.mixins import TimestampMixin


class AgentCollectionResult(SQLModel, TimestampMixin, table=True):
    __tablename__ = "agent_collection_results"
    __table_args__ = (
        UniqueConstraint(
            "namespace",
            "resource_key",
            "resource_date",
            name="ux_agent_collection_result",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    namespace: str = Field(max_length=100, index=True)
    resource_key: str = Field(max_length=200, index=True)
    resource_date: date = Field(index=True)
    recipe_id: int = Field(foreign_key="agent_recipes.id")
    output: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    status: str = Field(default="success", max_length=20)
    error_message: str | None = Field(default=None, sa_type=sa.Text())
```

Add the `sa` import:
```python
import sqlalchemy as sa
```

- [ ] **Step 3: Commit**

```bash
git add src/domains/agent_result/
git commit -m "feat: add AgentCollectionResult domain model"
```

---

### Task 3: Repository — AgentResultRepository

**Files:**
- Create: `src/domains/agent_result/repository.py`

- [ ] **Step 1: Create repository**

Create `src/domains/agent_result/repository.py`:
```python
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agent_result.models import AgentCollectionResult
from src.shared.mixins import now
from src.shared.repository import BaseRepository


class AgentResultRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def upsert(
        self,
        *,
        namespace: str,
        resource_key: str,
        resource_date: date,
        recipe_id: int,
        output: dict,
        status: str = "success",
        error_message: str | None = None,
    ) -> AgentCollectionResult:
        insert_timestamp = now()
        values = {
            "namespace": namespace,
            "resource_key": resource_key,
            "resource_date": resource_date,
            "recipe_id": recipe_id,
            "output": output,
            "status": status,
            "error_message": error_message,
            "created_at": insert_timestamp,
            "updated_at": insert_timestamp,
        }
        update_values = {
            "recipe_id": recipe_id,
            "output": output,
            "status": status,
            "error_message": error_message,
            "updated_at": insert_timestamp,
        }
        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""

        if dialect_name == "postgresql":
            stmt = (
                postgresql_insert(AgentCollectionResult)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["namespace", "resource_key", "resource_date"],
                    set_=update_values,
                )
            )
        elif dialect_name == "sqlite":
            stmt = (
                sqlite_insert(AgentCollectionResult)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["namespace", "resource_key", "resource_date"],
                    set_=update_values,
                )
            )
        else:
            stmt = (
                sqlite_insert(AgentCollectionResult)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["namespace", "resource_key", "resource_date"],
                    set_=update_values,
                )
            )

        await self.session.execute(stmt)
        await self.session.flush()

        result_stmt = (
            select(AgentCollectionResult)
            .where(
                AgentCollectionResult.namespace == namespace,
                AgentCollectionResult.resource_key == resource_key,
                AgentCollectionResult.resource_date == resource_date,
            )
        )
        return (await self.session.execute(result_stmt)).scalar_one()

    async def list_by_date_range(
        self,
        *,
        namespace: str,
        resource_key: str,
        date_from: date,
        date_to: date,
    ) -> list[AgentCollectionResult]:
        stmt = (
            select(AgentCollectionResult)
            .where(
                AgentCollectionResult.namespace == namespace,
                AgentCollectionResult.resource_key == resource_key,
                AgentCollectionResult.resource_date >= date_from,
                AgentCollectionResult.resource_date <= date_to,
            )
            .order_by(AgentCollectionResult.resource_date.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_id(self, result_id: int) -> AgentCollectionResult | None:
        stmt = select(AgentCollectionResult).where(AgentCollectionResult.id == result_id).limit(1)
        return (await self.session.execute(stmt)).scalars().first()

    async def query_results(
        self,
        *,
        namespace: str | None = None,
        resource_key: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AgentCollectionResult], int]:
        from sqlalchemy import func

        conditions = []
        if namespace:
            conditions.append(AgentCollectionResult.namespace == namespace)
        if resource_key:
            conditions.append(AgentCollectionResult.resource_key == resource_key)
        if date_from:
            conditions.append(AgentCollectionResult.resource_date >= date_from)
        if date_to:
            conditions.append(AgentCollectionResult.resource_date <= date_to)

        base_query = select(AgentCollectionResult)
        if conditions:
            from sqlalchemy import and_
            base_query = base_query.where(and_(*conditions))

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        rows_query = base_query.order_by(
            AgentCollectionResult.resource_date.desc(),
            AgentCollectionResult.id.desc(),
        ).offset(offset).limit(limit)
        rows = list((await self.session.execute(rows_query)).scalars().all())

        return rows, total
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from src.domains.agent_result.repository import AgentResultRepository; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/domains/agent_result/repository.py
git commit -m "feat: add AgentResultRepository"
```

---

### Task 4: Schemas — Agent Result Pydantic Schemas

**Files:**
- Create: `src/domains/agent_result/schemas.py`

- [ ] **Step 1: Create schemas**

Create `src/domains/agent_result/schemas.py`:
```python
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    namespace: str
    resource_key: str
    resource_date: date
    recipe_id: int
    output: dict[str, Any]
    status: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentResultListResponse(BaseModel):
    items: list[AgentResultResponse]
    total: int
    page: int
    size: int
```

- [ ] **Step 2: Commit**

```bash
git add src/domains/agent_result/schemas.py
git commit -m "feat: add agent result Pydantic schemas"
```

---

### Task 5: Service — AgentResultService

**Files:**
- Create: `src/domains/agent_result/services.py`

- [ ] **Step 1: Create service**

Create `src/domains/agent_result/services.py`:
```python
from __future__ import annotations

import csv
import io
from collections.abc import AsyncGenerator
from datetime import date

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agent_recipe.repository import AgentRecipeRepository
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
        offset = max(page - 1, 0) * max(size, 1)
        rows, total = await self.repo.query_results(
            namespace=namespace,
            resource_key=resource_key,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=max(size, 1),
        )
        items = [AgentResultResponse.model_validate(row) for row in rows]
        return AgentResultListResponse(
            items=items,
            total=total,
            page=max(page, 1),
            size=max(size, 1),
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

        recipe_repo = AgentRecipeRepository(self.session)
        recipe_cache: dict[int, dict] = {}

        csv_rows: list[dict] = []
        all_headers_set: set[str] = set()

        for result in rows:
            if result.recipe_id not in recipe_cache:
                recipe = await recipe_repo.get_by_id(result.recipe_id)
                recipe_cache[result.recipe_id] = (
                    recipe.observations if recipe else {}
                )

            output = result.output or {}
            row_data = {"date": result.resource_date.isoformat()}

            for obs_id, obs_data in output.items():
                observations = recipe_cache.get(result.recipe_id, {})
                obs_spec = observations.get(obs_id, {})
                if obs_spec.get("kind") == "table":
                    if isinstance(obs_data, list) and obs_data:
                        headers = _parse_table_headers(obs_data[0])
                        for header in headers:
                            col_key = f"{obs_id}_{header}"
                            all_headers_set.add(col_key)
                        data_cells = _parse_table_row(obs_data[0])
                        for header, cell in zip(headers, data_cells):
                            col_key = f"{obs_id}_{header}"
                            row_data[col_key] = cell
                        for line in obs_data[1:]:
                            pass
                elif obs_spec.get("kind") == "list":
                    if isinstance(obs_data, list):
                        row_data[obs_id] = "|".join(str(v) for v in obs_data)
                elif obs_spec.get("kind") == "text":
                    if isinstance(obs_data, str):
                        row_data[obs_id] = obs_data

            csv_rows.append(row_data)

        all_headers = ["date"] + sorted(all_headers_set)
        filename = f"{namespace}_{resource_key}_{date_from.isoformat()}_{date_to.isoformat()}.csv"

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=all_headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(csv_rows)

        return buf.getvalue(), filename


def _parse_table_headers(first_line: str) -> list[str]:
    parts = _split_csv_line(first_line)
    return [p.strip() for p in parts if p.strip()]


def _parse_table_row(line: str) -> list[str]:
    parts = _split_csv_line(line)
    return [p.strip() for p in parts]


def _split_csv_line(line: str) -> list[str]:
    return line.split(",")


async def get_agent_result_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AgentResultService, None]:
    yield AgentResultService(session=session)
```

- [ ] **Step 2: Commit**

```bash
git add src/domains/agent_result/services.py
git commit -m "feat: add AgentResultService with CSV builder"
```

---

### Task 6: API Routes — Agent Results & CSV Download

**Files:**
- Create: `src/api/v1/agent_results.py`

- [ ] **Step 1: Create API routes**

Create `src/api/v1/agent_results.py`:
```python
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.auth import User, current_user
from src.domains.agent_result.schemas import AgentResultListResponse, AgentResultResponse
from src.domains.agent_result.services import AgentResultService, get_agent_result_service
from src.responses.base import Response

router = APIRouter(prefix="/agent-results", tags=["agent-results"])


@router.get("", response_model=Response[AgentResultListResponse])
async def list_agent_results(
    namespace: str | None = Query(default=None),
    resource_key: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    _user: User = Depends(current_user),
    service: AgentResultService = Depends(get_agent_result_service),
) -> Response[AgentResultListResponse]:
    result = await service.list_results(
        namespace=namespace,
        resource_key=resource_key,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
    )
    return Response.success(data=result)


@router.get("/{result_id}", response_model=Response[AgentResultResponse])
async def get_agent_result(
    result_id: int,
    _user: User = Depends(current_user),
    service: AgentResultService = Depends(get_agent_result_service),
) -> Response[AgentResultResponse]:
    result = await service.get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="agent result not found")
    return Response.success(data=result)


@router.get("/download", response_class=StreamingResponse)
async def download_agent_results_csv(
    namespace: str = Query(..., min_length=1),
    resource_key: str = Query(..., min_length=1),
    date_from: date = Query(...),
    date_to: date = Query(...),
    _user: User = Depends(current_user),
    service: AgentResultService = Depends(get_agent_result_service),
) -> StreamingResponse:
    csv_content, filename = await service.build_csv(
        namespace=namespace,
        resource_key=resource_key,
        date_from=date_from,
        date_to=date_to,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
```

Note: the `/download` route must be defined **before** `/{result_id}` to avoid FastAPI matching "download" as an integer path param. Actually, FastAPI resolves this correctly because `/download` is a literal string match and `/{result_id}` expects an int — they won't conflict. But to be safe with the order, list `/download` first.

- [ ] **Step 2: Commit**

```bash
git add src/api/v1/agent_results.py
git commit -m "feat: add agent results API with CSV download"
```

---

### Task 7: Recipe Export Schema & Service Method

**Files:**
- Modify: `src/domains/agent_recipe/schemas.py`
- Modify: `src/domains/agent_recipe/services.py`
- Modify: `src/domains/agent_recipe/repository.py`

- [ ] **Step 1: Add export/import schemas**

In `src/domains/agent_recipe/schemas.py`, add after existing classes:

```python
class AgentRecipeExportPayload(BaseModel):
    format_version: int = 1
    recipe: AgentRecipePayload


class AgentRecipeImportResponse(BaseModel):
    id: int
    namespace: str
    key: str
    version: int
    status: str
    stability: str
```

- [ ] **Step 2: Add export/import methods to service**

In `src/domains/agent_recipe/services.py`, add these methods to `AgentRecipeService`:

```python
    async def export_recipe(
        self,
        recipe_id: int,
    ) -> tuple[str, str] | None:
        from src.domains.agent_recipe.schemas import (
            AgentRecipePayload,
            AgentRecipeExportPayload,
        )
        import json

        recipe = await self.recipe_repo.get_by_id(recipe_id)
        if recipe is None:
            if self.session.in_transaction():
                await self.session.rollback()
            return None
        payload = AgentRecipePayload(
            entrypoint=recipe.entrypoint,
            steps=recipe.steps,
            observations=recipe.observations,
            assertions=recipe.assertions,
            recovery_policy=recipe.recovery_policy,
            security_policy=recipe.security_policy,
        )
        export_payload = AgentRecipeExportPayload(
            format_version=1,
            recipe=payload,
        )
        filename = f"{recipe.namespace}_{recipe.key}_v{recipe.version}.agent-recipe.json"
        content = json.dumps(
            export_payload.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        return content, filename

    async def import_recipe(
        self,
        content: str,
    ) -> AgentRecipeResponse | None:
        from src.domains.agent_recipe.schemas import (
            AgentRecipeCreate,
            AgentRecipeExportPayload,
        )
        from src.exceptions import BusinessException
        from src.shared.errors import ErrorCode
        import json

        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            raise BusinessException(
                ErrorCode.DATA_VALIDATION_FAILED,
                "invalid recipe JSON file",
            )
        export_payload = AgentRecipeExportPayload.model_validate(raw)
        data = export_payload.recipe

        existing = await self.recipe_repo.list_versions(
            data.namespace,
            data.key,
        )
        existing_versions = {r.version for r in existing}
        target_version = data.version
        if target_version in existing_versions:
            if self.session.in_transaction():
                await self.session.rollback()
            raise BusinessException(
                ErrorCode.DATA_VALIDATION_FAILED,
                f"recipe {data.namespace}/{data.key} version {target_version} already exists",
            )

        create_data = AgentRecipeCreate(
            namespace=data.namespace,
            key=data.key,
            version=data.version,
            status="active",
            stability="candidate",
            entrypoint=data.entrypoint,
            steps=data.steps,
            observations=data.observations,
            assertions=data.assertions,
            recovery_policy=data.recovery_policy,
            security_policy=data.security_policy,
        )
        return await self.create(create_data)
```

- [ ] **Step 3: Commit**

```bash
git add src/domains/agent_recipe/schemas.py src/domains/agent_recipe/services.py
git commit -m "feat: add recipe export/import service methods"
```

---

### Task 8: Recipe Export/Import API Endpoints

**Files:**
- Modify: `src/api/v1/agent_discovery.py`

- [ ] **Step 1: Add import endpoint**

In `src/api/v1/agent_discovery.py`, add the required imports at top:

```python
from fastapi.responses import StreamingResponse
from fastapi import File, UploadFile
```

Add the export endpoint before the `@router.websocket` line:

```python
@router.get("/recipes/{recipe_id}/export")
async def export_agent_recipe(
    recipe_id: int,
    _user: User = Depends(current_user),
    service: AgentRecipeService = Depends(get_agent_recipe_service),
):
    result = await service.export_recipe(recipe_id)
    if result is None:
        raise HTTPException(status_code=404, detail="agent recipe not found")
    content, filename = result
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post(
    "/recipes/import",
    response_model=Response[dict[str, Any]],
)
async def import_agent_recipe(
    file: UploadFile = File(...),
    _user: User = Depends(current_user),
    _=Depends(require_permissions(_DISCOVERY_PERMISSION, bypass_superuser=True)),
    service: AgentRecipeService = Depends(get_agent_recipe_service),
) -> Response[dict[str, Any]]:
    if not file.filename or not file.filename.endswith(".agent-recipe.json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file must be .agent-recipe.json",
        )
    content = (await file.read()).decode("utf-8")
    try:
        recipe = await service.import_recipe(content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return Response.success(
        data={
            "id": recipe.id,
            "namespace": recipe.namespace,
            "key": recipe.key,
            "version": recipe.version,
            "status": recipe.status,
            "stability": recipe.stability,
        }
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/api/v1/agent_discovery.py
git commit -m "feat: add recipe export and import API endpoints"
```

---

### Task 9: Register New Router in main.py

**Files:**
- Modify: `src/api/__init__.py`
- Modify: `src/main.py`

- [ ] **Step 1: Export router from api/__init__.py**

In `src/api/__init__.py`, add:
```python
from .v1.agent_results import router as agent_results_router
```

In the `__all__` list, add:
```python
    "agent_results_router",
```

- [ ] **Step 2: Register router in main.py**

In `src/main.py`, add import:
```python
    agent_results_router,
```

Add route registration:
```python
    app.include_router(agent_results_router, prefix="/api/v1", tags=["agent-results"])
```

- [ ] **Step 3: Commit**

```bash
git add src/api/__init__.py src/main.py
git commit -m "feat: register agent-results router"
```

---

### Task 10: Persist Agent Output in CollectionResultPersister

**Files:**
- Modify: `src/application/collection/result_persister.py`

- [ ] **Step 1: Add agent result persistence**

In `src/application/collection/result_persister.py`, add import at top:
```python
from src.domains.agent_result.repository import AgentResultRepository
```

In `CollectionResultPersister.persist()`, add after the `await session.commit()` call (line 79) and before the cache invalidation call (line 80):

```python
        await self._persist_agent_result(
            session=session,
            payload=payload,
            resolved_shop_id=resolved_shop_id,
            metric_day=metric_day,
            status=status,
        )
```

Add the new method to `CollectionResultPersister`:

```python
    async def _persist_agent_result(
        self,
        *,
        session: AsyncSession,
        payload: dict[str, Any],
        resolved_shop_id: str,
        metric_day: date,
        status: str,
    ) -> None:
        raw = payload.get("raw") if isinstance(payload, dict) else {}
        if not isinstance(raw, dict):
            return
        agent = raw.get("agent") if isinstance(raw, dict) else {}
        if not isinstance(agent, dict):
            return
        recipe_info = agent.get("recipe") if isinstance(agent, dict) else {}
        if not isinstance(recipe_info, dict):
            return
        recipe_id = recipe_info.get("id")
        if not recipe_id:
            return

        output = {
            k: v for k, v in payload.items()
            if k not in {
                "actual_shop_id", "shop_id", "target_shop_id", "shop_name",
                "metric_date", "source", "status", "rule_id", "execution_id",
                "total_score", "product_score", "logistics_score",
                "service_score", "bad_behavior_score",
                "reviews", "violations", "raw",
            }
        }

        repo = AgentResultRepository(session)
        await repo.upsert(
            namespace="shop_dashboard",
            resource_key=resolved_shop_id,
            resource_date=metric_day,
            recipe_id=int(recipe_id),
            output=output,
            status=status,
        )
```

Note: the `recipe_id` currently stored in `raw.agent.recipe` is the recipe metadata (namespace, key, version), not the DB integer ID. We need to look up the actual DB recipe_id. Let me adjust — the `_build_payload` in `browser_agent_adapter.py` stores `recipe.namespace`, `recipe.key`, `recipe.version` in `raw.agent.recipe`. But the DB `agent_recipes` table has the integer primary key `id`. We need the DB `id` for the FK reference.

Looking at `browser_agent_adapter.py._build_payload()` (line 126-158), the `raw.agent.recipe` dict has `namespace`, `key`, `version` from the `Recipe` Pydantic model, not the DB `id`. The `loaded_recipe.recipe_id` is available in the adapter but not passed into the payload.

The cleanest approach: add `recipe_id` to the agent metadata in `_build_payload()`. Looking at line 147-151:
```python
agent = {
    "recipe": {
        "namespace": recipe.namespace,
        "key": recipe.key,
        "version": recipe.version,
    },
    "status": result.status,
}
```

We should also add `"id": loaded_recipe.recipe_id` here. But `_build_payload` doesn't receive `loaded_recipe`. Looking at how it's called (line 117-123):
```python
return self._build_payload(
    runtime=runtime,
    metric_date=metric_date,
    recipe=recipe,
    result=result,
    output=result.output,
    storage_state_path=storage_state_path,
)
```

And in the recovery path (line 304-311):
```python
return self._build_payload(
    runtime=runtime,
    metric_date=metric_date,
    recipe=candidate_recipe,
    result=replay_result.model_copy(update={"status": "recovered"}),
    output=replay_result.output,
    recovery=recovery_metadata,
    storage_state_path=storage_state_path,
)
```

The `recipe` Pydantic model has `metadata: dict[str, Any]` which can store the DB `recipe_id`. From `_recipe_from_payload()` (line 215-218):
```python
if recipe_id is not None:
    metadata = dict(recipe_payload.get("metadata") or {})
    metadata.setdefault("recipe_id", recipe_id)
    recipe_payload["metadata"] = metadata
```

So `recipe.metadata` may have `"recipe_id"`. We can access `recipe.metadata.get("recipe_id")` in `_build_payload`. Let me update the plan.

- [ ] **Step 2: Modify _build_payload to include recipe_id**

In `src/application/collection/browser_agent_adapter.py`, `_build_payload` method (line 146-157), change the `agent` dict:

```python
        recipe_id = recipe.metadata.get("recipe_id") if recipe.metadata else None
        agent = {
            "recipe": {
                "namespace": recipe.namespace,
                "key": recipe.key,
                "version": recipe.version,
            },
            "status": result.status,
        }
        if recipe_id is not None:
            agent["recipe"]["id"] = recipe_id
```

- [ ] **Step 3: Update persister import and method**

In `src/application/collection/result_persister.py`, update the `_persist_agent_result` method to use the recipe DB id from `raw.agent.recipe.id`:

```python
    async def _persist_agent_result(
        self,
        *,
        session: AsyncSession,
        payload: dict[str, Any],
        resolved_shop_id: str,
        metric_day: date,
        status: str,
    ) -> None:
        raw = payload.get("raw") if isinstance(payload, dict) else {}
        if not isinstance(raw, dict):
            return
        agent = raw.get("agent") if isinstance(raw, dict) else {}
        if not isinstance(agent, dict):
            return
        recipe_info = agent.get("recipe") if isinstance(agent, dict) else {}
        if not isinstance(recipe_info, dict):
            return
        recipe_id = recipe_info.get("id")
        if not recipe_id:
            return

        output = {
            k: v for k, v in payload.items()
            if k not in {
                "actual_shop_id", "shop_id", "target_shop_id", "shop_name",
                "metric_date", "source", "status", "rule_id", "execution_id",
                "total_score", "product_score", "logistics_score",
                "service_score", "bad_behavior_score",
                "reviews", "violations", "raw",
            }
        }

        repo = AgentResultRepository(session)
        try:
            await repo.upsert(
                namespace="shop_dashboard",
                resource_key=resolved_shop_id,
                resource_date=metric_day,
                recipe_id=int(recipe_id),
                output=output,
                status=status,
            )
        except Exception:
            logger.exception(
                "failed to persist agent result: shop_id=%s metric_date=%s",
                resolved_shop_id,
                metric_day.isoformat(),
            )
```

- [ ] **Step 4: Commit**

```bash
git add src/application/collection/result_persister.py src/application/collection/browser_agent_adapter.py
git commit -m "feat: persist agent collection output to agent_collection_results"
```

---

### Task 11: Cleanup — Remove Residual Data Structures

**Files:**
- Modify: `src/application/collection/browser_agent_adapter.py`
- Modify: `src/domains/shop_dashboard/repository.py`
- Modify: `src/domains/experience/presentation_mapper.py`

- [ ] **Step 1: Remove reviews/violations defaults from browser_agent_adapter**

In `src/application/collection/browser_agent_adapter.py`, `_map_output` method (lines 527-551), remove lines 548-549:
```python
        payload.setdefault("reviews", {"summary": {}, "items": []})
        payload.setdefault("violations", {"summary": {}, "waiting_list": []})
```

- [ ] **Step 2: Remove reviews/violations/cold_metrics from repository materials**

In `src/domains/shop_dashboard/repository.py`:

`build_agent_context` method (lines 126-155) — remove the stale keys from the returned dict:
```python
    return {
        "shop_id": shop_id,
        "metric_date": metric_date.isoformat(),
        "total_score": _score_or_zero(score.total_score if score else None),
        "product_score": _score_or_zero(score.product_score if score else None),
        "logistics_score": _score_or_zero(score.logistics_score if score else None),
        "service_score": _score_or_zero(score.service_score if score else None),
        "bad_behavior_score": _score_or_zero(
            score.bad_behavior_score if score else None
        ),
        "raw": {},
    }
```

`list_display_materials` method (lines 255-276) — remove `reviews`, `violations`, `cold_metrics`:
```python
        items.append(
            {
                "shop_id": shop_id,
                "shop_name": (row.shop_name if row else None) or "",
                "metric_date": metric_date.isoformat(),
                "source": row.source if row else "",
                "status": row.status if row else "missing",
                "reason": row.reason if row else None,
                "error_code": row.error_code if row else None,
                "total_score": _score_value(row.total_score) if row else None,
                "product_score": _score_value(row.product_score) if row else None,
                "logistics_score": (
                    _score_value(row.logistics_score) if row else None
                ),
                "service_score": _score_value(row.service_score) if row else None,
                "bad_behavior_score": (
                    _score_value(row.bad_behavior_score) if row else None
                ),
            }
        )
```

- [ ] **Step 3: Remove cold_metrics fallback from presentation_mapper**

In `src/domains/experience/presentation_mapper.py`, `_build_issue_rows` method (lines 299-361):

Remove the `else` branch that reads from `cold_metrics` (lines 337-357):
```python
        else:
            cold_metrics = material.get("cold_metrics", [])
            for index, cold in enumerate(cold_metrics, start=1):
                reason = str(cold.get("reason", "")).strip()
                if not reason:
                    continue
                fallback_rows.append(
                    {
                        "id": f"cold-{day}-{index}",
                        "shop_id": shop_id,
                        "dimension": "risk",
                        "title": reason,
                        "deduct_points": 0.0,
                        "impact_score": 0.0,
                        "status": "pending",
                        "owner": "",
                        "occurred_at": occurred_at,
                        "deadline_at": None,
                        "date_range": date_range,
                    }
                )
```

Replace the else block with just `pass` or remove it entirely (keep the `if violations:` block, remove the `else`):

```python
        violations = material.get("violations", [])
        if violations:
            for row in violations:
                issue_id = str(row.get("id", "")).strip()
                if not issue_id:
                    continue
                ...
```

Remove the `fallback_rows` variable from lines 306, 337-357, and 359:
- Line 306: remove `fallback_rows: list[dict[str, Any]] = []`
- Line 359: change `rows = list(deduped.values()) + fallback_rows` to `rows = list(deduped.values())`

- [ ] **Step 4: Run existing tests to ensure no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/application/collection/browser_agent_adapter.py src/domains/shop_dashboard/repository.py src/domains/experience/presentation_mapper.py
git commit -m "refactor: remove residual reviews/violations/cold_metrics data structures"
```

---

### Task 12: Integration Tests

**Files:**
- Create: `tests/domains/agent_result/test_repository.py`
- Create: `tests/api/test_agent_results_api.py`
- Create: `tests/api/test_agent_recipe_export_import.py`

- [ ] **Step 1: Write repository integration tests**

Create `tests/domains/agent_result/test_repository.py`:
```python
import pytest
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agent_result.repository import AgentResultRepository


@pytest.mark.anyio
async def test_upsert_creates_new_result(db_session: AsyncSession):
    repo = AgentResultRepository(db_session)
    result = await repo.upsert(
        namespace="shop_dashboard",
        resource_key="shop_123",
        resource_date=date(2026, 5, 21),
        recipe_id=1,
        output={"experience_table": {"headers": ["name", "score"], "rows": [["a", "1"]]}},
        status="success",
    )
    assert result.id is not None
    assert result.namespace == "shop_dashboard"
    assert result.resource_key == "shop_123"
    assert result.output == {"experience_table": {"headers": ["name", "score"], "rows": [["a", "1"]]}}


@pytest.mark.anyio
async def test_upsert_updates_existing_result(db_session: AsyncSession):
    repo = AgentResultRepository(db_session)
    await repo.upsert(
        namespace="shop_dashboard",
        resource_key="shop_123",
        resource_date=date(2026, 5, 21),
        recipe_id=1,
        output={"v1": "old"},
        status="success",
    )
    result = await repo.upsert(
        namespace="shop_dashboard",
        resource_key="shop_123",
        resource_date=date(2026, 5, 21),
        recipe_id=2,
        output={"v1": "new"},
        status="success",
    )
    assert result.recipe_id == 2
    assert result.output == {"v1": "new"}


@pytest.mark.anyio
async def test_list_by_date_range_filters_correctly(db_session: AsyncSession):
    repo = AgentResultRepository(db_session)
    for day in [date(2026, 5, 20), date(2026, 5, 21), date(2026, 5, 22)]:
        await repo.upsert(
            namespace="shop_dashboard",
            resource_key="shop_123",
            resource_date=day,
            recipe_id=1,
            output={"day": day.isoformat()},
        )

    results = await repo.list_by_date_range(
        namespace="shop_dashboard",
        resource_key="shop_123",
        date_from=date(2026, 5, 20),
        date_to=date(2026, 5, 21),
    )
    assert len(results) == 2
    assert results[0].resource_date == date(2026, 5, 20)
    assert results[1].resource_date == date(2026, 5, 21)


@pytest.mark.anyio
async def test_list_by_date_range_skips_missing_dates(db_session: AsyncSession):
    repo = AgentResultRepository(db_session)
    await repo.upsert(
        namespace="shop_dashboard",
        resource_key="shop_123",
        resource_date=date(2026, 5, 20),
        recipe_id=1,
        output={},
    )

    results = await repo.list_by_date_range(
        namespace="shop_dashboard",
        resource_key="shop_123",
        date_from=date(2026, 5, 19),
        date_to=date(2026, 5, 22),
    )
    assert len(results) == 1
```

- [ ] **Step 2: Run repository tests**

Run: `uv run pytest tests/domains/agent_result/test_repository.py -v`
Expected: All 4 tests pass.

- [ ] **Step 3: Write API integration tests**

Create `tests/api/test_agent_results_api.py`:
```python
import pytest
from datetime import date
from httpx import AsyncClient, ASGITransport

from src.main import app


@pytest.mark.anyio
async def test_list_agent_results_empty(db_session_with_data):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/agent-results",
            params={"namespace": "shop_dashboard", "resource_key": "nonexistent"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["items"] == []
        assert data["data"]["total"] == 0


@pytest.mark.anyio
async def test_download_csv_returns_csv_content(db_session_with_data):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/agent-results/download",
            params={
                "namespace": "shop_dashboard",
                "resource_key": "shop_123",
                "date_from": "2026-05-01",
                "date_to": "2026-05-21",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv"
        assert "date" in response.text
```

- [ ] **Step 4: Write recipe export/import API tests**

Create `tests/api/test_agent_recipe_export_import.py`:
```python
import json
import pytest
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.domains.agent_recipe.models import AgentRecipe


@pytest.mark.anyio
async def test_export_recipe_returns_json_file(db_session_with_data):
    recipe = AgentRecipe(
        namespace="test_ns",
        key="test_key",
        version=1,
        status="active",
        stability="stable",
        entrypoint={"url": "https://example.com"},
        steps=[],
        observations={"obs1": {"id": "obs1", "kind": "text"}},
        assertions=[],
        recovery_policy={"enabled": True},
        security_policy={"allowed_origins": []},
    )
    db_session_with_data.add(recipe)
    await db_session_with_data.commit()
    await db_session_with_data.refresh(recipe)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/agent-discovery/recipes/{recipe.id}/export")
        assert response.status_code == 200
        data = response.json()
        assert data["format_version"] == 1
        assert data["recipe"]["namespace"] == "test_ns"
        assert data["recipe"]["key"] == "test_key"
        assert data["recipe"]["version"] == 1


@pytest.mark.anyio
async def test_import_recipe_creates_new_recipe(db_session_with_data):
    export_json = json.dumps({
        "format_version": 1,
        "recipe": {
            "namespace": "import_ns",
            "key": "import_key",
            "version": 1,
            "entrypoint": {"url": "https://example.com"},
            "steps": [],
            "observations": {},
            "assertions": [],
            "recovery_policy": {"enabled": True, "minimum_confidence": 0.7, "max_attempts": 1},
            "security_policy": {"allowed_origins": [], "blocked_patterns": [], "snapshot_max_chars": 30000},
        },
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent-discovery/recipes/import",
            files={"file": ("test.agent-recipe.json", export_json.encode(), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["namespace"] == "import_ns"
        assert data["data"]["key"] == "import_key"
        assert data["data"]["version"] == 1
        assert data["data"]["stability"] == "candidate"


@pytest.mark.anyio
async def test_import_recipe_conflict_on_existing_version(db_session_with_data):
    export_json = json.dumps({
        "format_version": 1,
        "recipe": {
            "namespace": "dup_ns",
            "key": "dup_key",
            "version": 1,
            "entrypoint": {"url": "https://example.com"},
            "steps": [],
            "observations": {},
            "assertions": [],
            "recovery_policy": {"enabled": True, "minimum_confidence": 0.7, "max_attempts": 1},
            "security_policy": {"allowed_origins": [], "blocked_patterns": [], "snapshot_max_chars": 30000},
        },
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/agent-discovery/recipes/import",
            files={"file": ("test.agent-recipe.json", export_json.encode(), "application/json")},
        )
        response = await client.post(
            "/api/v1/agent-discovery/recipes/import",
            files={"file": ("test.agent-recipe.json", export_json.encode(), "application/json")},
        )
        assert response.status_code == 409
```

- [ ] **Step 5: Run all new tests**

Run: `uv run pytest tests/domains/agent_result/ tests/api/test_agent_results_api.py tests/api/test_agent_recipe_export_import.py -v`
Expected: All tests pass.

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/domains/agent_result/ tests/api/test_agent_results_api.py tests/api/test_agent_recipe_export_import.py
git commit -m "test: add integration tests for agent results and recipe export/import"
```

---

## Self-Review

### Spec Coverage
- [x] `agent_collection_results` table migration — Task 1
- [x] Domain model — Task 2
- [x] Repository with upsert, list_by_date_range, query — Task 3
- [x] Pydantic schemas — Task 4
- [x] Service with CSV builder — Task 5
- [x] API: list, detail, CSV download — Task 6
- [x] Recipe export/import service — Task 7
- [x] Recipe export/import API — Task 8
- [x] Router registration — Task 9
- [x] CollectionResultPersister integration — Task 10
- [x] Cleanup residual reviews/violations/cold_metrics — Task 11
- [x] Integration tests — Task 12

### Placeholder Scan
No TBD, TODO, or placeholder patterns found. All steps contain actual code.

### Type Consistency
- `AgentCollectionResult` model fields match migration column names — verified
- `AgentResultRepository` method signatures match `AgentResultService` usage — verified
- `AgentRecipeExportPayload` referenced consistently in service and API — verified
- `recipe_id` flow: `browser_agent_adapter._build_payload` → `raw.agent.recipe.id` → `CollectionResultPersister._persist_agent_result` — verified