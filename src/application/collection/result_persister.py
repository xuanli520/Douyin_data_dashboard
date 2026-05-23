from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

import src.cache as cache_module
from src.domains.agent_result.repository import AgentResultRepository
from src.domains.experience.services import ExperienceQueryService
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.middleware.monitor import observe_shop_dashboard_score_upsert
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig

logger = logging.getLogger(__name__)


class CollectionResultPersister:
    async def persist(
        self,
        *,
        session: AsyncSession,
        runtime: ShopDashboardRuntimeConfig,
        metric_date: str,
        payload: dict[str, Any],
    ) -> None:
        repo = ShopDashboardRepository(session)
        metric_day = date.fromisoformat(metric_date)
        metric_day_text = metric_day.isoformat()
        runtime_shop_id = _normalize_shop_id(runtime.shop_id)
        actual_shop_id = _normalize_shop_id(
            payload.get("actual_shop_id") or payload.get("shop_id") or runtime_shop_id
        )
        target_shop_id = _normalize_shop_id(
            payload.get("target_shop_id") or runtime_shop_id
        )
        resolved_shop_id = actual_shop_id or runtime_shop_id
        if not resolved_shop_id or not target_shop_id:
            logger.warning(
                "skip dashboard persistence due to empty shop key: target_shop_id=%s actual_shop_id=%s resolved_shop_id=%s metric_date=%s",
                target_shop_id,
                actual_shop_id,
                resolved_shop_id,
                metric_day_text,
            )
            return
        if actual_shop_id != target_shop_id:
            logger.warning(
                "skip dashboard persistence due to shop mismatch: target_shop_id=%s actual_shop_id=%s resolved_shop_id=%s metric_date=%s",
                target_shop_id,
                actual_shop_id,
                resolved_shop_id,
                metric_day_text,
            )
            return
        source = str(payload.get("source", "browser_agent"))
        status = str(payload.get("status") or "success").strip() or "success"
        score = await repo.upsert_score(
            shop_id=resolved_shop_id,
            metric_date=metric_day,
            total_score=_to_float_or_none(payload.get("total_score")),
            product_score=_to_float_or_none(payload.get("product_score")),
            logistics_score=_to_float_or_none(payload.get("logistics_score")),
            service_score=_to_float_or_none(payload.get("service_score")),
            bad_behavior_score=_to_float_or_none(payload.get("bad_behavior_score")),
            shop_name=str(payload.get("shop_name", "")).strip() or None,
            source=source,
            status=status,
            reason=payload.get("reason"),
            error_code=payload.get("error_code"),
        )
        insert_or_update = sa_inspect(score).info.get("insert_or_update", "update")
        observe_shop_dashboard_score_upsert(
            insert_or_update=str(insert_or_update),
            shop_id=resolved_shop_id,
            metric_date=metric_day_text,
        )
        await self._persist_agent_result(
            session=session,
            payload=payload,
            resolved_shop_id=resolved_shop_id,
            metric_day=metric_day,
            fallback_status=status,
        )
        await session.commit()
        try:
            await self._invalidate_experience_cache(
                session=session,
                shop_id=resolved_shop_id,
                metric_day=metric_day,
            )
        except Exception:
            logger.exception(
                "experience cache invalidation failed after persistence: shop_id=%s metric_day=%s",
                resolved_shop_id,
                metric_day_text,
            )
            raise

    async def _invalidate_experience_cache(
        self,
        *,
        session: AsyncSession,
        shop_id: str,
        metric_day: date,
    ) -> None:
        cache = cache_module.cache
        if cache is None:
            return
        service = ExperienceQueryService(
            repo=ShopDashboardRepository(session=session),
            cache=cache,
        )
        await service.invalidate_shop_date(
            shop_id=shop_id,
            metric_date=metric_day,
        )

    async def _persist_agent_result(
        self,
        *,
        session: AsyncSession,
        payload: dict[str, Any],
        resolved_shop_id: str,
        metric_day: date,
        fallback_status: str,
    ) -> None:
        raw = payload.get("raw")
        if not isinstance(raw, dict):
            return
        agent = raw.get("agent")
        if not isinstance(agent, dict):
            return
        recipe = agent.get("recipe")
        if not isinstance(recipe, dict):
            return
        recipe_id = _to_int_or_none(recipe.get("id") or recipe.get("recipe_id"))
        if recipe_id is None:
            return
        namespace = str(recipe.get("namespace") or "").strip() or "shop_dashboard"
        status = str(agent.get("status") or fallback_status).strip() or fallback_status
        await AgentResultRepository(session).upsert(
            namespace=namespace,
            resource_key=resolved_shop_id,
            resource_date=metric_day,
            recipe_id=recipe_id,
            output=_agent_result_output(payload),
            status=status,
            error_message=_text_or_none(
                payload.get("reason") or payload.get("error_code")
            ),
        )


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_shop_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if normalized.isdigit():
        return str(int(normalized))
    return normalized


def _agent_result_output(payload: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "actual_shop_id",
        "shop_id",
        "target_shop_id",
        "shop_name",
        "metric_date",
        "source",
        "status",
        "rule_id",
        "execution_id",
        "total_score",
        "product_score",
        "logistics_score",
        "service_score",
        "bad_behavior_score",
        "reason",
        "error_code",
        "raw",
    }
    return {key: value for key, value in payload.items() if key not in excluded}


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
