from __future__ import annotations

import logging
from datetime import UTC, date as date_type, datetime
from typing import Any

from src.agents import LLMDashboardAgent
from src.cache import resolve_sync_redis_client
from src.config import get_settings
from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src import session
from src.tasks.base import TaskStatusMixin
from src.tasks.funboost_compat import boost, fct
from src.tasks.idempotency import FunboostIdempotencyHelper
from src.tasks.params import CollectionTaskParams
from src.tasks.status_store import write_started_task_status

logger = logging.getLogger(__name__)


def _write_started_status(task_func, task_name: str, triggered_by: int | None) -> None:
    try:
        task_id = str(getattr(fct, "task_id", "unknown"))
        write_started_task_status(
            owner=task_func,
            task_id=task_id,
            task_name=task_name,
            triggered_by=triggered_by,
        )
    except Exception:
        logger.exception("failed to write started task status: %s", task_name)


@boost(
    CollectionTaskParams(
        queue_name="collection_shop_dashboard_agent",
        consumer_override_cls=TaskStatusMixin,
        is_push_to_dlx_queue_when_retry_max_times=True,
    )
)
def sync_shop_dashboard_agent(
    shop_id: str,
    date: str | None = None,
    reason: str = "agent_backfill",
    triggered_by: int | None = None,
) -> dict[str, Any]:
    _write_started_status(
        sync_shop_dashboard_agent,
        "sync_shop_dashboard_agent",
        triggered_by,
    )
    redis_client = resolve_sync_redis_client()
    helper = FunboostIdempotencyHelper(
        redis_client=redis_client,
        task_name="sync_shop_dashboard_agent",
    )
    metric_date = date or datetime.now(UTC).date().isoformat()
    business_key = f"{shop_id}:{metric_date}:{reason}"

    cached = helper.get_cached_result(business_key)
    if cached:
        return cached

    token = helper.acquire_lock(
        business_key,
        ttl=get_settings().shop_dashboard.lock_ttl_seconds,
    )
    if not token:
        return {
            "status": "skipped",
            "reason": "running",
            "shop_id": shop_id,
            "metric_date": metric_date,
            "source": "llm",
        }

    try:
        base_result = _run_async(_load_agent_context(shop_id, metric_date, reason))
        agent = LLMDashboardAgent()
        try:
            patch = agent.supplement_cold_data(
                base_result,
                shop_id,
                metric_date,
                reason=reason,
            )
        finally:
            close = getattr(agent, "close", None)
            if callable(close):
                close()
        _run_async(_persist_agent_patch(shop_id, metric_date, reason, patch))
        result: dict[str, Any] = {
            "status": "success",
            "shop_id": shop_id,
            "metric_date": metric_date,
            "reason": reason,
            "source": "llm",
        }
        for key, value in patch.items():
            if key in {"status", "source", "shop_id", "metric_date", "reason"}:
                continue
            result[key] = value

        helper.cache_result(business_key, result)
        return result
    finally:
        helper.release_lock(business_key, token)


@boost(
    CollectionTaskParams(
        queue_name="collection_shop_dashboard_agent_dlx",
        consumer_override_cls=TaskStatusMixin,
    )
)
def handle_collection_shop_dashboard_agent_dead_letter(**payload) -> dict[str, Any]:
    return {
        "status": "recorded",
        "queue": "collection_shop_dashboard_agent_dlx",
        "payload": payload,
    }


async def _load_agent_context(
    shop_id: str,
    metric_date: str,
    reason: str,
) -> dict[str, Any]:
    fallback: dict[str, Any] = {
        "shop_id": shop_id,
        "metric_date": metric_date,
        "raw": {},
    }
    session_factory = session.async_session_factory
    if session_factory is None:
        return fallback
    try:
        metric_day = date_type.fromisoformat(metric_date)
    except ValueError:
        return fallback

    async with session_factory() as db_session:
        repo = ShopDashboardRepository(db_session)
        return await repo.build_agent_context(
            shop_id=shop_id,
            metric_date=metric_day,
            reason=reason,
        )


async def _persist_agent_patch(
    shop_id: str,
    metric_date: str,
    reason: str,
    patch: dict[str, Any],
) -> None:
    session_factory = session.async_session_factory
    if session_factory is None:
        return
    try:
        metric_day = date_type.fromisoformat(metric_date)
    except ValueError:
        return

    raw = patch.get("raw")
    llm_patch = raw.get("llm_patch") if isinstance(raw, dict) else None
    if isinstance(llm_patch, dict) and llm_patch.get("status") == "failed":
        return

    async with session_factory() as db_session:
        repo = ShopDashboardRepository(db_session)
        await repo.upsert_cold_metrics(
            shop_id=shop_id,
            metric_date=metric_day,
            reason=reason,
            violations_detail=_ensure_list_of_dicts(patch.get("violations_detail")),
            arbitration_detail=_ensure_list_of_dicts(patch.get("arbitration_detail")),
            dsr_trend=_ensure_list_of_dicts(patch.get("dsr_trend")),
            source="llm",
        )
        await db_session.commit()


def _ensure_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _run_async(coro):
    return session.run_coro(coro)
