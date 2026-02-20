from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from src.api.v1.mock_schemas import build_pagination_meta

ExperienceDimension = Literal["product", "logistics", "service", "risk", "all"]

SUPPORTED_EXPERIENCE_DIMENSIONS: tuple[ExperienceDimension, ...] = (
    "product",
    "logistics",
    "service",
    "risk",
)

_DIMENSION_WEIGHTS: dict[ExperienceDimension, float] = {
    "product": 0.35,
    "logistics": 0.3,
    "service": 0.25,
    "risk": 0.1,
}

_DIMENSION_BASE_SCORES: dict[ExperienceDimension, int] = {
    "product": 92,
    "logistics": 90,
    "service": 88,
    "risk": 83,
}

_METRIC_LIBRARY: dict[ExperienceDimension, list[dict[str, str]]] = {
    "product": [
        {
            "id": "product_quality_score",
            "title": "product_quality_score",
            "weight": "45%",
            "value_suffix": "pt",
            "description": "weighted_quality_feedback",
        },
        {
            "id": "product_return_rate",
            "title": "product_return_rate",
            "weight": "30%",
            "value_suffix": "%",
            "description": "quality_return_ratio",
        },
        {
            "id": "product_negative_review_rate",
            "title": "product_negative_review_rate",
            "weight": "25%",
            "value_suffix": "%",
            "description": "negative_feedback_ratio",
        },
    ],
    "logistics": [
        {
            "id": "pickup_sla",
            "title": "pickup_sla",
            "weight": "30%",
            "value_suffix": "%",
            "description": "pickup_in_24h_ratio",
        },
        {
            "id": "delivery_sla",
            "title": "delivery_sla",
            "weight": "50%",
            "value_suffix": "%",
            "description": "delivery_in_72h_ratio",
        },
        {
            "id": "logistics_return_rate",
            "title": "logistics_return_rate",
            "weight": "20%",
            "value_suffix": "%",
            "description": "logistics_damage_return_ratio",
        },
    ],
    "service": [
        {
            "id": "response_latency",
            "title": "response_latency",
            "weight": "40%",
            "value_suffix": "s",
            "description": "average_first_response_seconds",
        },
        {
            "id": "after_sales_resolution_rate",
            "title": "after_sales_resolution_rate",
            "weight": "35%",
            "value_suffix": "%",
            "description": "resolved_after_sales_ratio",
        },
        {
            "id": "service_satisfaction",
            "title": "service_satisfaction",
            "weight": "25%",
            "value_suffix": "%",
            "description": "customer_service_satisfaction",
        },
    ],
    "risk": [
        {
            "id": "fake_transaction",
            "title": "fake_transaction",
            "weight": "40%",
            "value_suffix": "pt",
            "description": "deduction_for_fake_transactions",
        },
        {
            "id": "policy_violation",
            "title": "policy_violation",
            "weight": "35%",
            "value_suffix": "pt",
            "description": "deduction_for_policy_violations",
        },
        {
            "id": "customer_complaint_penalty",
            "title": "customer_complaint_penalty",
            "weight": "25%",
            "value_suffix": "pt",
            "description": "deduction_for_customer_complaints",
        },
    ],
}


def normalize_dimension(dimension: str | None) -> ExperienceDimension:
    if dimension in SUPPORTED_EXPERIENCE_DIMENSIONS:
        return dimension
    if dimension == "all":
        return "all"
    if dimension is None:
        return "product"
    raise ValueError(f"Unsupported dimension: {dimension}")


def _parse_date_range(date_range: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(tz=UTC)
    if not date_range:
        return now - timedelta(days=29), now

    clean = date_range.strip()
    if "," in clean:
        start_raw, end_raw = [part.strip() for part in clean.split(",", 1)]
        try:
            start = datetime.strptime(start_raw, "%Y-%m-%d").replace(tzinfo=UTC)
            end = datetime.strptime(end_raw, "%Y-%m-%d").replace(tzinfo=UTC)
            if start <= end:
                return start, end
        except ValueError:
            return now - timedelta(days=29), now

    if clean.endswith("d") and clean[:-1].isdigit():
        days = max(int(clean[:-1]), 1)
        return now - timedelta(days=days - 1), now

    return now - timedelta(days=29), now


def _date_seed(date_range: str | None) -> int:
    return sum(ord(ch) for ch in (date_range or "30d"))


def _score_by_dimension(
    shop_id: int,
    dimension: ExperienceDimension,
    date_range: str | None,
) -> float:
    base = _DIMENSION_BASE_SCORES[dimension]
    drift = ((shop_id * 7 + _date_seed(date_range) + len(dimension)) % 11) - 5
    if dimension == "risk":
        score = max(60.0, min(95.0, base - abs(drift) * 1.5))
    else:
        score = max(70.0, min(100.0, base + drift * 0.8))
    return round(score, 2)


def _build_trend(
    shop_id: int,
    dimension: ExperienceDimension,
    date_range: str | None,
    points: int = 7,
) -> list[dict[str, float | str]]:
    start, end = _parse_date_range(date_range)
    span = max((end - start).days, 1)
    step = max(span // max(points - 1, 1), 1)
    base = _score_by_dimension(shop_id, dimension, date_range)
    trend: list[dict[str, float | str]] = []
    for index in range(points):
        current = start + timedelta(days=min(index * step, span))
        wave = ((shop_id + index * 3 + _date_seed(date_range)) % 9) - 4
        value = max(55.0, min(100.0, base + wave * 0.45))
        trend.append({"date": current.date().isoformat(), "value": round(value, 2)})
    return trend


def build_shops_data(
    page: int,
    size: int,
    date_range: str | None,
) -> dict[str, list[dict[str, int | float | str]] | dict[str, int | bool]]:
    total = 36
    page = max(page, 1)
    size = max(size, 1)
    offset = (page - 1) * size
    categories = ["fashion", "beauty", "grocery", "digital"]

    items: list[dict[str, int | float | str]] = []
    for index in range(size):
        absolute = offset + index
        if absolute >= total:
            break
        shop_id = 1001 + absolute
        score = float(
            build_shop_score(shop_id=shop_id, date_range=date_range)["overall_score"]
        )
        gmv = round(850000 + (shop_id * 731 + _date_seed(date_range)) % 450000, 2)
        items.append(
            {
                "id": shop_id,
                "name": f"shop_{shop_id}",
                "category": categories[absolute % len(categories)],
                "status": "active" if absolute % 5 else "paused",
                "gmv": gmv,
                "score": score,
                "products_count": 140 + (shop_id % 120),
            }
        )

    return {
        "items": items,
        "meta": build_pagination_meta(page=page, size=size, total=total),
    }


def build_shop_score(shop_id: int, date_range: str | None) -> dict[str, object]:
    dimensions: list[dict[str, str | int | float]] = []
    for index, dimension in enumerate(SUPPORTED_EXPERIENCE_DIMENSIONS):
        score = _score_by_dimension(shop_id, dimension, date_range)
        dimensions.append(
            {
                "dimension": dimension,
                "score": score,
                "weight": f"{int(_DIMENSION_WEIGHTS[dimension] * 100)}%",
                "rank": 30 + (shop_id * (index + 3)) % 500,
            }
        )

    weighted = sum(
        float(item["score"]) * _DIMENSION_WEIGHTS[item["dimension"]]
        for item in dimensions
    )

    return {
        "shop_id": shop_id,
        "shop_name": f"shop_{shop_id}",
        "overall_score": round(weighted, 2),
        "dimensions": dimensions,
        "trend": _build_trend(
            shop_id=shop_id, dimension="product", date_range=date_range
        ),
        "date_range": date_range or "30d",
    }


def build_metric_detail(
    metric_type: str,
    shop_id: int,
    date_range: str | None,
    period: str,
) -> dict[str, object]:
    dimension = normalize_dimension(metric_type)
    category_score = _score_by_dimension(shop_id, dimension, date_range)
    trend = _build_trend(shop_id=shop_id, dimension=dimension, date_range=date_range)

    sub_metrics: list[dict[str, object]] = []
    for index, item in enumerate(_METRIC_LIBRARY[dimension]):
        score = max(0.0, min(100.0, category_score + ((shop_id + index) % 7) - 3))
        raw_value = round(score if item["value_suffix"] != "s" else 40 - index * 6, 2)
        metric: dict[str, object] = {
            "id": item["id"],
            "title": item["title"],
            "score": round(score, 2),
            "weight": item["weight"],
            "value": f"{raw_value}{item['value_suffix']}",
            "desc": item["description"],
        }
        if dimension == "risk":
            metric.update(
                {
                    "deduct_points": round(max(0.0, 100 - score), 2),
                    "impact_score": round(max(0.0, 100 - score) * 0.65, 2),
                    "status": ["pending", "processing", "resolved", "ignored"][
                        (shop_id + index) % 4
                    ],
                    "owner": f"owner_{(shop_id + index) % 5 + 1}",
                    "deadline_at": (datetime.now(tz=UTC) + timedelta(days=index + 1))
                    .replace(microsecond=0)
                    .isoformat(),
                }
            )
        sub_metrics.append(metric)

    score_ranges = [
        {
            "label": "excellent",
            "range": "90-100",
            "count": 25 + shop_id % 20,
        },
        {
            "label": "good",
            "range": "80-89",
            "count": 35 + (shop_id * 2) % 25,
        },
        {
            "label": "attention",
            "range": "0-79",
            "count": 10 + (shop_id * 3) % 20,
        },
    ]

    formula = " + ".join(
        f"{item['id']}*{item['weight']}" for item in _METRIC_LIBRARY[dimension]
    )

    return {
        "shop_id": shop_id,
        "metric_type": dimension,
        "period": period,
        "date_range": date_range or "30d",
        "category_score": category_score,
        "sub_metrics": sub_metrics,
        "score_ranges": score_ranges,
        "formula": formula,
        "trend": trend,
    }


def build_experience_overview(
    shop_id: int, date_range: str | None
) -> dict[str, object]:
    shop_score = build_shop_score(shop_id=shop_id, date_range=date_range)
    dimensions = shop_score["dimensions"]
    return {
        "shop_id": shop_id,
        "date_range": date_range or "30d",
        "overall_score": shop_score["overall_score"],
        "dimensions": dimensions,
        "alerts": {
            "critical": 1 + shop_id % 2,
            "warning": 2 + shop_id % 4,
            "info": 5 + shop_id % 6,
            "total": 8 + shop_id % 10,
            "unread": 3 + shop_id % 5,
        },
    }


def build_experience_trend(
    shop_id: int,
    dimension: str | None,
    date_range: str | None,
) -> dict[str, object]:
    normalized_dimension = normalize_dimension(dimension)
    return {
        "shop_id": shop_id,
        "dimension": normalized_dimension,
        "date_range": date_range or "30d",
        "trend": _build_trend(
            shop_id=shop_id,
            dimension=normalized_dimension,
            date_range=date_range,
            points=12,
        ),
    }


def build_experience_issues(
    shop_id: int,
    dimension: str | None,
    status: str | None,
    date_range: str | None,
    page: int,
    size: int,
) -> dict[str, object]:
    normalized_dimension = normalize_dimension(dimension)
    statuses = ["pending", "processing", "resolved", "ignored"]
    dimensions = list(SUPPORTED_EXPERIENCE_DIMENSIONS)
    total_rows = 42

    rows: list[dict[str, object]] = []
    for index in range(total_rows):
        row_dimension = dimensions[index % len(dimensions)]
        row_status = statuses[(shop_id + index) % len(statuses)]
        row = {
            "id": f"issue_{shop_id}_{index + 1}",
            "shop_id": shop_id,
            "dimension": row_dimension,
            "title": f"{row_dimension}_issue_{index + 1}",
            "deduct_points": round(1 + ((shop_id + index) % 13) * 0.8, 2),
            "impact_score": round(2 + ((shop_id + index * 3) % 17) * 0.7, 2),
            "status": row_status,
            "owner": f"owner_{(index % 6) + 1}",
            "occurred_at": (
                datetime.now(tz=UTC) - timedelta(days=index % 14, hours=index % 6)
            )
            .replace(microsecond=0)
            .isoformat(),
            "deadline_at": (datetime.now(tz=UTC) + timedelta(days=(index % 5) + 1))
            .replace(microsecond=0)
            .isoformat(),
            "date_range": date_range or "30d",
        }
        rows.append(row)

    filtered = [
        row
        for row in rows
        if (dimension in (None, "", "all") or row["dimension"] == normalized_dimension)
        and (status in (None, "", "all") or row["status"] == status)
    ]

    page = max(page, 1)
    size = max(size, 1)
    start = (page - 1) * size
    end = start + size

    return {
        "items": filtered[start:end],
        "meta": build_pagination_meta(page=page, size=size, total=len(filtered)),
    }


def build_experience_drilldown(
    shop_id: int,
    dimension: str,
    date_range: str | None,
    page: int,
    size: int,
) -> dict[str, object]:
    normalized_dimension = normalize_dimension(dimension)
    metric_detail = build_metric_detail(
        metric_type=normalized_dimension,
        shop_id=shop_id,
        date_range=date_range,
        period="30d",
    )
    issues = build_experience_issues(
        shop_id=shop_id,
        dimension=normalized_dimension,
        status=None,
        date_range=date_range,
        page=page,
        size=size,
    )
    return {
        "shop_id": shop_id,
        "dimension": normalized_dimension,
        "date_range": date_range or "30d",
        "category_score": metric_detail["category_score"],
        "sub_metrics": metric_detail["sub_metrics"],
        "score_ranges": metric_detail["score_ranges"],
        "formula": metric_detail["formula"],
        "trend": metric_detail["trend"],
        "issues": issues,
    }
