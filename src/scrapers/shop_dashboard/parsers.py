from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.scrapers.shop_dashboard.exceptions import LoginExpiredError
from src.scrapers.shop_dashboard.exceptions import ShopDashboardScraperError

LOGIN_EXPIRED_CODE = "10008"


def ensure_payload_success(payload: Mapping[str, Any]) -> None:
    code = payload.get("code")
    if code is None:
        code = payload.get("status_code")
    if code is None:
        code = payload.get("errno")
    if code is None:
        return
    code_str = str(code)
    if code_str in {"0", "200"}:
        return
    message = str(payload.get("message", payload.get("msg", "scraping failed")))
    if code_str == LOGIN_EXPIRED_CODE:
        raise LoginExpiredError(
            "Login session expired",
            error_data={"code": code_str, "message": message},
        )
    raise ShopDashboardScraperError(
        message,
        error_data={"code": code_str, "message": message},
    )


def parse_core_scores(payload: Mapping[str, Any]) -> dict[str, float]:
    ensure_payload_success(payload)
    data = _extract_data(payload)
    return {
        "total_score": _first_float(
            data,
            ("experience_score", "value"),
            ("experience_score",),
            ("total_score", "value"),
            ("total_score",),
        ),
        "product_score": _first_float(
            data,
            ("goods_score", "value"),
            ("goods_score",),
            ("product_score", "value"),
            ("product_score",),
        ),
        "logistics_score": _first_float(
            data,
            ("logistics_score", "value"),
            ("logistics_score",),
        ),
        "service_score": _first_float(
            data,
            ("service_score", "value"),
            ("service_score",),
        ),
        "bad_behavior_score": _first_float(
            data,
            ("bad_behavior_deduct_score", "value"),
            ("bad_behavior_deduct_score",),
            ("bad_behavior_score", "value"),
            ("bad_behavior_score",),
        ),
    }


def parse_comment_summary(
    statistics_payload: Mapping[str, Any],
    unreply_payload: Mapping[str, Any],
    tags_payload: Mapping[str, Any],
    product_payload: Mapping[str, Any],
) -> dict[str, Any]:
    ensure_payload_success(statistics_payload)
    ensure_payload_success(unreply_payload)
    ensure_payload_success(tags_payload)
    ensure_payload_success(product_payload)

    statistics_data = _extract_data(statistics_payload)
    unreply_data = _extract_data(unreply_payload)
    tags_data = _extract_data(tags_payload)
    product_data = _extract_data(product_payload)

    return {
        "negative_comment_count": _first_int(
            statistics_data,
            ("negative_comment_count",),
            ("negative_count",),
            ("bad_comment_count",),
            default=0,
        ),
        "unreply_negative_comment_count": _first_int(
            unreply_data,
            ("count",),
            ("total_count",),
            ("total",),
            default=0,
        ),
        "negative_tags": _extract_list(tags_data),
        "negative_products": _extract_list(product_data),
    }


def parse_comment_details(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    ensure_payload_success(payload)
    items = _extract_list(_extract_data(payload))
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        result.append(
            {
                "id": item.get("id"),
                "product_id": item.get("product_id"),
                "order_id": item.get("order_id"),
                "content": item.get("content"),
                "shop_reply": item.get("shop_reply", item.get("reply_content")),
                "comment_time": item.get("comment_time"),
                "sku": item.get("sku"),
            }
        )
    return result


def parse_violation_summary(
    cash_payload: Mapping[str, Any],
    score_node_payload: Mapping[str, Any],
    ticket_count_payload: Mapping[str, Any],
) -> dict[str, Any]:
    cash_data = _safe_extract_data(cash_payload)
    score_data = _safe_extract_data(score_node_payload)
    ticket_data = _safe_extract_data(ticket_count_payload)

    return {
        "cash_deduct_amount": _first_float(
            cash_data,
            ("cash", "deduct_amount"),
            ("deduct_amount",),
            ("cash_deduct_amount",),
            default=0.0,
        ),
        "a_level_point": _first_int(
            score_data,
            ("score", "a_level_point"),
            ("a_level_point",),
            ("a_point",),
            default=0,
        ),
        "b_level_point": _first_int(
            score_data,
            ("score", "b_level_point"),
            ("b_level_point",),
            ("b_point",),
            default=0,
        ),
        "ticket_count": _first_int(
            ticket_data,
            ("total_count",),
            ("count",),
            ("ticket_count",),
            default=0,
        ),
    }


def parse_violation_details(
    waiting_payload: Mapping[str, Any],
    top_rule_payload: Mapping[str, Any],
    high_frequency_payload: Mapping[str, Any],
) -> dict[str, list[Any]]:
    return {
        "waiting_list": _extract_list(_safe_extract_data(waiting_payload)),
        "top_rules": _extract_list(_safe_extract_data(top_rule_payload)),
        "high_frequency_penalties": _extract_list(
            _safe_extract_data(high_frequency_payload)
        ),
    }


def _extract_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data", {})
    if isinstance(data, Mapping):
        return data
    if isinstance(data, list):
        return {"list": data}
    return {}


def _safe_extract_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        ensure_payload_success(payload)
    except ShopDashboardScraperError:
        return {}
    return _extract_data(payload)


def _extract_list(data: Mapping[str, Any]) -> list[Any]:
    for key in ("list", "items", "records", "data", "tags", "products"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _first_float(
    data: Mapping[str, Any], *paths: tuple[str, ...], default: float = 0.0
) -> float:
    for path in paths:
        value = _get_path(data, path)
        parsed = _to_float(value)
        if parsed is not None:
            return parsed
    return default


def _first_int(
    data: Mapping[str, Any], *paths: tuple[str, ...], default: int = 0
) -> int:
    for path in paths:
        value = _get_path(data, path)
        parsed = _to_int(value)
        if parsed is not None:
            return parsed
    return default


def _get_path(data: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
