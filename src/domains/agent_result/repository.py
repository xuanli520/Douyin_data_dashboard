from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agent_recipe.models import AgentRecipe
from src.domains.agent_result.models import AgentCollectionResult
from src.exceptions import BusinessException
from src.shared.errors import ErrorCode
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
        timestamp = now()
        values = {
            "namespace": namespace,
            "resource_key": resource_key,
            "resource_date": resource_date,
            "recipe_id": recipe_id,
            "output": output,
            "status": status,
            "error_message": error_message,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        update_values = {
            "recipe_id": recipe_id,
            "output": output,
            "status": status,
            "error_message": error_message,
            "updated_at": timestamp,
        }
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name == "postgresql":
            stmt = (
                postgresql_insert(AgentCollectionResult)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[
                        "namespace",
                        "resource_key",
                        "resource_date",
                        "recipe_id",
                    ],
                    set_=update_values,
                )
            )
        elif dialect_name == "sqlite":
            stmt = (
                sqlite_insert(AgentCollectionResult)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[
                        "namespace",
                        "resource_key",
                        "resource_date",
                        "recipe_id",
                    ],
                    set_=update_values,
                )
            )
        else:
            raise BusinessException(
                ErrorCode.SHOP_DASHBOARD_UNSUPPORTED_DIALECT,
                f"unsupported database dialect for upsert: {dialect_name}",
                data={"dialect": dialect_name},
            )

        await self.session.execute(stmt)
        await self.session.flush()
        result_stmt = (
            select(AgentCollectionResult)
            .where(
                AgentCollectionResult.namespace == namespace,
                AgentCollectionResult.resource_key == resource_key,
                AgentCollectionResult.resource_date == resource_date,
                AgentCollectionResult.recipe_id == recipe_id,
            )
            .execution_options(populate_existing=True)
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

    async def list_by_recipe_key(
        self,
        *,
        namespace: str,
        resource_key: str,
        recipe_key: str,
        date_from: date,
        date_to: date,
    ) -> list[AgentCollectionResult]:
        stmt = (
            select(AgentCollectionResult)
            .join(AgentRecipe, AgentRecipe.id == AgentCollectionResult.recipe_id)
            .where(
                AgentCollectionResult.namespace == namespace,
                AgentCollectionResult.resource_key == resource_key,
                AgentCollectionResult.resource_date >= date_from,
                AgentCollectionResult.resource_date <= date_to,
                AgentRecipe.key == recipe_key,
            )
            .order_by(
                AgentCollectionResult.resource_date.asc(),
                AgentCollectionResult.id.asc(),
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_id(self, result_id: int) -> AgentCollectionResult | None:
        stmt = select(AgentCollectionResult).where(
            AgentCollectionResult.id == result_id
        )
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
        conditions = []
        if namespace:
            conditions.append(AgentCollectionResult.namespace == namespace)
        if resource_key:
            conditions.append(AgentCollectionResult.resource_key == resource_key)
        if date_from:
            conditions.append(AgentCollectionResult.resource_date >= date_from)
        if date_to:
            conditions.append(AgentCollectionResult.resource_date <= date_to)

        base_stmt = select(AgentCollectionResult)
        if conditions:
            base_stmt = base_stmt.where(and_(*conditions))

        total = (
            await self.session.execute(
                select(func.count()).select_from(base_stmt.subquery())
            )
        ).scalar_one()
        rows_stmt = (
            base_stmt.order_by(
                AgentCollectionResult.resource_date.desc(),
                AgentCollectionResult.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        rows = list((await self.session.execute(rows_stmt)).scalars().all())
        return rows, total
