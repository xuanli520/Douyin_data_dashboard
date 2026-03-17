from __future__ import annotations

from datetime import UTC, date, datetime
from math import ceil
from typing import Any

from src.domains.experience.schemas import (
    METRIC_CONTRACTS,
    SUPPORTED_EXPERIENCE_DIMENSIONS,
)


def build_overview(
    *,
    shop_id: int,
    date_range: str,
    materials: list[dict[str, Any]],
    dimension_weights: dict[str, float],
) -> dict[str, Any]:
    latest = _latest_material(materials)
    dimension_values = _dimension_scores_from_material(latest)
    ranked_dimensions = sorted(
        dimension_values.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    rank_map = {name: index + 1 for index, (name, _) in enumerate(ranked_dimensions)}

    dimensions = [
        {
            "dimension": dimension,
            "score": round(dimension_values.get(dimension, 0.0), 2),
            "weight": f"{int(dimension_weights[dimension] * 100)}%",
            "rank": rank_map[dimension],
        }
        for dimension in SUPPORTED_EXPERIENCE_DIMENSIONS
    ]

    overall_score = round(
        sum(
            dimension_values.get(dimension, 0.0) * dimension_weights[dimension]
            for dimension in SUPPORTED_EXPERIENCE_DIMENSIONS
        ),
        2,
    )

    issues = _build_issue_rows(
        shop_id=shop_id,
        date_range=date_range,
        materials=materials,
    )
    alerts = _build_alerts(issues)

    return {
        "shop_id": shop_id,
        "date_range": date_range,
        "overall_score": overall_score,
        "dimensions": dimensions,
        "alerts": alerts,
    }


def build_trend(
    *,
    shop_id: int,
    dimension: str,
    date_range: str,
    materials: list[dict[str, Any]],
) -> dict[str, Any]:
    trend = []
    for material in _sorted_materials(materials):
        scores = _dimension_scores_from_material(material)
        trend.append(
            {
                "date": material["metric_date"],
                "value": round(scores.get(dimension, 0.0), 2),
            }
        )
    return {
        "shop_id": shop_id,
        "dimension": dimension,
        "date_range": date_range,
        "trend": trend,
    }


def build_issues(
    *,
    shop_id: int,
    date_range: str,
    materials: list[dict[str, Any]],
    dimension: str | None,
    status: str | None,
    page: int,
    size: int,
) -> dict[str, Any]:
    normalized_dimension = (dimension or "all").strip() or "all"
    normalized_status = (status or "all").strip() or "all"

    rows = _build_issue_rows(
        shop_id=shop_id,
        date_range=date_range,
        materials=materials,
    )
    if normalized_dimension != "all":
        rows = [row for row in rows if row["dimension"] == normalized_dimension]
    if normalized_status != "all":
        rows = [row for row in rows if row["status"] == normalized_status]

    total = len(rows)
    start = max(page - 1, 0) * max(size, 1)
    end = start + max(size, 1)
    pages = ceil(total / max(size, 1)) if total else 0
    items = rows[start:end]

    return {
        "items": items,
        "meta": {
            "page": max(page, 1),
            "size": max(size, 1),
            "total": total,
            "pages": pages,
            "has_next": max(page, 1) < pages,
            "has_prev": max(page, 1) > 1 and pages > 0,
        },
    }


def build_metric_detail(
    *,
    shop_id: int,
    metric_type: str,
    period: str,
    date_range: str,
    materials: list[dict[str, Any]],
) -> dict[str, Any]:
    trend_payload = build_trend(
        shop_id=shop_id,
        dimension=metric_type,
        date_range=date_range,
        materials=materials,
    )
    latest = _latest_material(materials)
    category_score = round(
        _dimension_scores_from_material(latest).get(metric_type, 0.0), 2
    )

    sub_metrics: list[dict[str, Any]] = []
    for contract in METRIC_CONTRACTS[metric_type]:
        row: dict[str, Any] = {
            "id": contract.metric_key,
            "title": contract.title,
            "score": category_score,
            "weight": contract.weight,
            "value": _format_metric_value(category_score, contract.unit),
            "desc": contract.formula,
        }
        if contract.deduct_points:
            deduct_points = round(max(0.0, 100.0 - category_score), 2)
            row.update(
                {
                    "deduct_points": deduct_points,
                    "impact_score": round(deduct_points * 0.65, 2),
                    "status": "pending",
                    "owner": "",
                    "deadline_at": "",
                }
            )
        sub_metrics.append(row)

    score_ranges = [
        {
            "label": "excellent",
            "range": "90-100",
            "count": len([m for m in sub_metrics if m["score"] >= 90]),
        },
        {
            "label": "good",
            "range": "80-89",
            "count": len([m for m in sub_metrics if 80 <= m["score"] < 90]),
        },
        {
            "label": "attention",
            "range": "0-79",
            "count": len([m for m in sub_metrics if m["score"] < 80]),
        },
    ]

    return {
        "shop_id": shop_id,
        "metric_type": metric_type,
        "period": period,
        "date_range": date_range,
        "category_score": category_score,
        "sub_metrics": sub_metrics,
        "score_ranges": score_ranges,
        "formula": " + ".join(
            f"{contract.metric_key}*{contract.weight}"
            for contract in METRIC_CONTRACTS[metric_type]
        ),
        "trend": trend_payload["trend"],
    }


def build_dashboard_overview(
    *,
    shop_id: int,
    date_range: str,
    materials: list[dict[str, Any]],
    overview_payload: dict[str, Any],
) -> dict[str, Any]:
    total_scores = [
        _normalize_score(row.get("total_score", 0.0))
        for row in materials
        if row.get("source")
    ]
    orders = len(total_scores) * 10
    gmv = (
        round(overview_payload["overall_score"] * max(orders, 1) * 1.2, 2)
        if orders
        else 0.0
    )
    average_order_value = round(gmv / orders, 2) if orders else 0.0

    latest = _latest_material(materials)
    latest_product = _dimension_scores_from_material(latest).get("product", 0.0)
    refund_rate = round(max(0.0, 100.0 - latest_product) / 20, 2)
    conversion_rate = round(min(99.0, overview_payload["overall_score"] / 1.2), 2)

    return {
        "shop_id": shop_id,
        "date_range": date_range,
        "cards": {
            "orders": orders,
            "gmv": gmv,
            "average_order_value": average_order_value,
            "refund_rate": f"{refund_rate}%",
            "conversion_rate": f"{conversion_rate}%",
        },
    }


def build_dashboard_kpis(
    *,
    shop_id: int,
    date_range: str,
    materials: list[dict[str, Any]],
    overview_payload: dict[str, Any],
) -> dict[str, Any]:
    trend: list[dict[str, Any]] = []
    refund_series: list[float] = []
    for row in _sorted_materials(materials):
        daily_score = _normalize_score(row.get("total_score", 0.0))
        orders = int(round(daily_score * 10))
        gmv = round(orders * daily_score, 2)
        trend.append({"date": row["metric_date"], "orders": orders, "gmv": gmv})
        refund_series.append(
            round(
                max(
                    0.0,
                    100.0 - _dimension_scores_from_material(row).get("product", 0.0),
                )
                / 20,
                2,
            )
        )

    first_orders = trend[0]["orders"] if trend else 0
    last_orders = trend[-1]["orders"] if trend else 0
    first_gmv = trend[0]["gmv"] if trend else 0.0
    last_gmv = trend[-1]["gmv"] if trend else 0.0
    first_refund = refund_series[0] if refund_series else 0.0
    last_refund = refund_series[-1] if refund_series else 0.0

    return {
        "shop_id": shop_id,
        "date_range": date_range,
        "kpis": [
            {
                "id": "orders",
                "value": last_orders,
                "change": _format_change(first_orders, last_orders),
            },
            {
                "id": "gmv",
                "value": last_gmv,
                "change": _format_change(first_gmv, last_gmv),
            },
            {
                "id": "refund_rate",
                "value": overview_payload["cards"]["refund_rate"],
                "change": _format_change(first_refund, last_refund),
            },
        ],
        "trend": trend,
    }


def _build_issue_rows(
    *,
    shop_id: int,
    date_range: str,
    materials: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    fallback_rows: list[dict[str, Any]] = []

    for material in _sorted_materials(materials):
        day = material["metric_date"]
        occurred_at = datetime.combine(
            date.fromisoformat(day),
            datetime.min.time(),
            tzinfo=UTC,
        ).isoformat()
        violations = material.get("violations", [])
        if violations:
            for row in violations:
                issue_id = str(row.get("id", "")).strip()
                if not issue_id:
                    continue
                issue = {
                    "id": issue_id,
                    "shop_id": shop_id,
                    "dimension": _resolve_dimension(str(row.get("type", ""))),
                    "title": str(row.get("description") or row.get("type") or issue_id),
                    "deduct_points": round(float(row.get("score", 0.0)), 2),
                    "impact_score": round(float(row.get("score", 0.0)), 2),
                    "status": "pending",
                    "owner": "",
                    "occurred_at": occurred_at,
                    "deadline_at": None,
                    "date_range": date_range,
                }
                previous = deduped.get(issue_id)
                if previous is None or issue["occurred_at"] >= previous["occurred_at"]:
                    deduped[issue_id] = issue
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

    rows = list(deduped.values()) + fallback_rows
    rows.sort(key=lambda item: (item["occurred_at"], item["id"]), reverse=True)
    return rows


def _build_alerts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    critical = 0
    warning = 0
    info = 0
    unread = 0
    for row in rows:
        impact_score = float(row.get("impact_score", 0.0))
        if impact_score >= 15:
            critical += 1
        elif impact_score >= 8:
            warning += 1
        else:
            info += 1
        if row.get("status") in {"pending", "processing"}:
            unread += 1
    return {
        "critical": critical,
        "warning": warning,
        "info": info,
        "total": len(rows),
        "unread": unread,
    }


def _resolve_dimension(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in SUPPORTED_EXPERIENCE_DIMENSIONS:
        return value
    for dimension in SUPPORTED_EXPERIENCE_DIMENSIONS:
        if dimension in value:
            return dimension
    return "risk"


def _latest_material(materials: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_rows = _sorted_materials(materials)
    if not sorted_rows:
        return {}
    return sorted_rows[-1]


def _sorted_materials(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(materials, key=lambda row: row.get("metric_date", ""))


def _dimension_scores_from_material(material: dict[str, Any]) -> dict[str, float]:
    product = _normalize_score(material.get("product_score", 0.0))
    logistics = _normalize_score(material.get("logistics_score", 0.0))
    service = _normalize_score(material.get("service_score", 0.0))
    bad_behavior = _normalize_score(material.get("bad_behavior_score", 0.0))
    risk = _clamp_score(100.0 - bad_behavior)
    return {
        "product": product,
        "logistics": logistics,
        "service": service,
        "risk": risk,
    }


def _normalize_score(value: Any) -> float:
    score = float(value or 0.0)
    if 0.0 <= score <= 5.0:
        score *= 20.0
    return _clamp_score(score)


def _clamp_score(score: float) -> float:
    return max(0.0, min(100.0, score))


def _format_metric_value(value: float, unit: str) -> str:
    rounded = round(float(value), 2)
    if unit == "%":
        return f"{rounded}%"
    if unit == "s":
        return f"{rounded}s"
    return f"{rounded}{unit}"


def _format_change(first: float | int, last: float | int) -> str:
    first_value = float(first)
    last_value = float(last)
    if first_value == 0:
        delta = 0.0 if last_value == 0 else 100.0
    else:
        delta = ((last_value - first_value) / abs(first_value)) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{round(delta, 2)}%"
