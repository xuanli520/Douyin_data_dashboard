from datetime import date
from typing import Any

from sqlalchemy import and_, func, inspect as sa_inspect, literal_column, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import BusinessException
from src.domains.shop_dashboard.models import ShopDashboardScore
from src.shared.errors import ErrorCode
from src.shared.mixins import now
from src.shared.repository import BaseRepository


class ShopDashboardRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def upsert_score(
        self,
        *,
        shop_id: str,
        metric_date: date,
        total_score: float | None,
        product_score: float | None,
        logistics_score: float | None,
        service_score: float | None,
        bad_behavior_score: float | None = None,
        shop_name: str | None = None,
        source: str,
        status: str = "success",
        reason: str | None = None,
        error_code: str | None = None,
    ) -> ShopDashboardScore:
        normalized_status = str(status or "success").strip() or "success"
        normalized_shop_name = str(shop_name or "").strip() or None
        insert_timestamp = now()
        update_timestamp = now()
        values = {
            "shop_id": shop_id,
            "metric_date": metric_date,
            "total_score": _score_value(total_score),
            "product_score": _score_value(product_score),
            "logistics_score": _score_value(logistics_score),
            "service_score": _score_value(service_score),
            "bad_behavior_score": _score_value(bad_behavior_score),
            "shop_name": normalized_shop_name,
            "source": source,
            "status": normalized_status,
            "reason": _text_or_none(reason),
            "error_code": _text_or_none(error_code),
            "created_at": insert_timestamp,
            "updated_at": insert_timestamp,
        }
        update_values = {
            "total_score": _score_value(total_score),
            "product_score": _score_value(product_score),
            "logistics_score": _score_value(logistics_score),
            "service_score": _score_value(service_score),
            "bad_behavior_score": _score_value(bad_behavior_score),
            "shop_name": normalized_shop_name,
            "source": source,
            "status": normalized_status,
            "reason": _text_or_none(reason),
            "error_code": _text_or_none(error_code),
            "updated_at": update_timestamp,
        }
        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""

        if dialect_name == "postgresql":
            stmt = (
                postgresql_insert(ShopDashboardScore)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["shop_id", "metric_date"],
                    set_=update_values,
                )
                .returning(
                    ShopDashboardScore,
                    literal_column("xmax = 0").label("is_insert"),
                )
            )
            row = (await self.session.execute(stmt)).one()
            operation = "insert" if bool(row[1]) else "update"
        elif dialect_name == "sqlite":
            stmt = (
                sqlite_insert(ShopDashboardScore)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["shop_id", "metric_date"],
                    set_=update_values,
                )
                .returning(ShopDashboardScore)
            )
            await self.session.execute(stmt)
            operation = "unknown"
        else:
            raise BusinessException(
                ErrorCode.SHOP_DASHBOARD_UNSUPPORTED_DIALECT,
                f"unsupported database dialect for upsert: {dialect_name}",
                data={"dialect": dialect_name},
            )

        score_stmt = (
            select(ShopDashboardScore)
            .where(
                ShopDashboardScore.shop_id == shop_id,
                ShopDashboardScore.metric_date == metric_date,
            )
            .execution_options(populate_existing=True)
        )
        score = (await self.session.execute(score_stmt)).scalar_one()
        if operation == "unknown":
            operation = (
                "insert"
                if score.created_at == insert_timestamp
                and score.updated_at == insert_timestamp
                else "update"
            )

        sa_inspect(score).info["insert_or_update"] = operation
        return score

    async def build_agent_context(
        self,
        *,
        shop_id: str,
        metric_date: date,
        reason: str,
    ) -> dict[str, Any]:
        score_stmt = select(ShopDashboardScore).where(
            ShopDashboardScore.shop_id == shop_id,
            ShopDashboardScore.metric_date == metric_date,
        )
        score = (await self.session.execute(score_stmt)).scalar_one_or_none()

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

    async def query_dashboard_results(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        return await self.list_display_materials(
            shop_id=shop_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_latest_metric_date(self, *, shop_id: str) -> date | None:
        stmt = select(func.max(ShopDashboardScore.metric_date)).where(
            ShopDashboardScore.shop_id == shop_id
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def list_shops(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        latest_metric_date_stmt = select(
            ShopDashboardScore.shop_id.label("shop_id"),
            func.max(ShopDashboardScore.metric_date).label("metric_date"),
        )
        if start_date is not None and end_date is not None:
            latest_metric_date_stmt = latest_metric_date_stmt.where(
                ShopDashboardScore.metric_date >= start_date,
                ShopDashboardScore.metric_date <= end_date,
            )
        latest_metric_date_subquery = latest_metric_date_stmt.group_by(
            ShopDashboardScore.shop_id
        ).subquery()
        stmt = (
            select(ShopDashboardScore)
            .join(
                latest_metric_date_subquery,
                and_(
                    ShopDashboardScore.shop_id == latest_metric_date_subquery.c.shop_id,
                    ShopDashboardScore.metric_date
                    == latest_metric_date_subquery.c.metric_date,
                ),
            )
            .order_by(ShopDashboardScore.shop_id.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(_score_row_item(row, include_updated_at=True))

        return items

    async def list_latest_per_shop(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        latest_metric_date_subquery = (
            select(
                ShopDashboardScore.shop_id.label("shop_id"),
                func.max(ShopDashboardScore.metric_date).label("metric_date"),
            )
            .where(
                ShopDashboardScore.metric_date >= start_date,
                ShopDashboardScore.metric_date <= end_date,
            )
            .group_by(ShopDashboardScore.shop_id)
            .subquery()
        )
        stmt = (
            select(ShopDashboardScore)
            .join(
                latest_metric_date_subquery,
                and_(
                    ShopDashboardScore.shop_id == latest_metric_date_subquery.c.shop_id,
                    ShopDashboardScore.metric_date
                    == latest_metric_date_subquery.c.metric_date,
                ),
            )
            .order_by(ShopDashboardScore.shop_id.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(_score_row_item(row))

        return items

    async def list_display_materials(
        self,
        *,
        shop_id: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        score_stmt = (
            select(ShopDashboardScore)
            .where(
                ShopDashboardScore.shop_id == shop_id,
                ShopDashboardScore.metric_date >= start_date,
                ShopDashboardScore.metric_date <= end_date,
            )
            .order_by(
                ShopDashboardScore.metric_date.asc(),
                ShopDashboardScore.updated_at.desc(),
                ShopDashboardScore.id.desc(),
            )
        )
        scores = (await self.session.execute(score_stmt)).scalars().all()

        latest_score_by_day: dict[date, ShopDashboardScore] = {}
        for row in scores:
            if row.metric_date not in latest_score_by_day:
                latest_score_by_day[row.metric_date] = row

        metric_dates = sorted(latest_score_by_day)
        if not metric_dates:
            return []

        items: list[dict[str, Any]] = []
        for metric_date in metric_dates:
            row = latest_score_by_day.get(metric_date)
            items.append(
                _score_row_item(row)
                if row is not None
                else _missing_score_item(shop_id=shop_id, metric_date=metric_date)
            )
        return items


def _score_row_item(
    row: ShopDashboardScore,
    *,
    include_updated_at: bool = False,
) -> dict[str, Any]:
    item = {
        "shop_id": row.shop_id,
        "shop_name": row.shop_name or "",
        "metric_date": row.metric_date.isoformat(),
        "source": row.source,
        "status": row.status,
        "reason": row.reason,
        "error_code": row.error_code,
        "total_score": _score_value(row.total_score),
        "product_score": _score_value(row.product_score),
        "logistics_score": _score_value(row.logistics_score),
        "service_score": _score_value(row.service_score),
        "bad_behavior_score": _score_value(row.bad_behavior_score),
    }
    if include_updated_at:
        item["updated_at"] = row.updated_at.isoformat()
    return item


def _missing_score_item(*, shop_id: str, metric_date: date) -> dict[str, Any]:
    return {
        "shop_id": shop_id,
        "shop_name": "",
        "metric_date": metric_date.isoformat(),
        "source": "",
        "status": "missing",
        "reason": None,
        "error_code": None,
        "total_score": None,
        "product_score": None,
        "logistics_score": None,
        "service_score": None,
        "bad_behavior_score": None,
    }


def _score_value(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _score_or_zero(value: Any) -> float:
    return _score_value(value) or 0.0


def _text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
