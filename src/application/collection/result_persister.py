from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shop_dashboard.repository import ShopDashboardRepository
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig


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
        await repo.upsert_score(
            shop_id=runtime.shop_id,
            metric_date=metric_day,
            total_score=float(payload.get("total_score", 0.0)),
            product_score=float(payload.get("product_score", 0.0)),
            logistics_score=float(payload.get("logistics_score", 0.0)),
            service_score=float(payload.get("service_score", 0.0)),
            bad_behavior_score=float(payload.get("bad_behavior_score", 0.0)),
            source=str(payload.get("source", "script")),
        )

        reviews = payload.get("reviews", {}).get("items", [])
        review_rows = []
        for review in reviews:
            review_rows.append(
                {
                    "review_id": review.get("id") or review.get("review_id") or "",
                    "content": review.get("content") or "",
                    "is_replied": bool(review.get("shop_reply")),
                    "source": str(payload.get("source", "script")),
                }
            )
        await repo.replace_reviews(
            shop_id=runtime.shop_id,
            metric_date=metric_day,
            reviews=review_rows,
        )

        violations = _extract_violation_items(payload)
        violation_rows = []
        for item in violations:
            violation_rows.append(
                {
                    "violation_id": item.get("ticket_id")
                    or item.get("ticketId")
                    or item.get("id")
                    or item.get("rule_id")
                    or item.get("penalty_id")
                    or item.get("rule")
                    or "",
                    "violation_type": item.get("type")
                    or item.get("rule_type")
                    or item.get("violation_type")
                    or item.get("penalty_type")
                    or "unknown",
                    "description": item.get("description")
                    or item.get("reason")
                    or item.get("rule"),
                    "score": _to_int(
                        item.get("score")
                        or item.get("deduct_score")
                        or item.get("deductScore")
                        or item.get("point")
                        or item.get("points")
                        or 0
                    ),
                    "source": str(payload.get("source", "script")),
                }
            )
        await repo.replace_violations(
            shop_id=runtime.shop_id,
            metric_date=metric_day,
            violations=violation_rows,
        )
        await session.commit()


def _extract_violation_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    violations = payload.get("violations")
    if isinstance(violations, dict):
        direct = _normalize_violation_items(violations.get("waiting_list"))
        if direct:
            return direct

    raw = payload.get("raw")
    if isinstance(raw, dict):
        raw_violations = raw.get("violations")
        if isinstance(raw_violations, dict):
            extracted = _extract_list(raw_violations.get("waiting_list"))
            fallback = _normalize_violation_items(extracted)
            if fallback:
                return fallback

    return []


def _normalize_violation_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def _extract_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, Mapping):
        return []

    for key in ("list", "items", "records", "waiting_list", "rows", "result", "data"):
        nested = value.get(key)
        if isinstance(nested, list):
            return nested

    for key in ("data", "result", "records"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            extracted = _extract_list(nested)
            if extracted:
                return extracted

    return []


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
