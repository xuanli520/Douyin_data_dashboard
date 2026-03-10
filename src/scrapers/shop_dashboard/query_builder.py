from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EndpointQueryContext:
    params: dict[str, Any]
    json_body: dict[str, Any]
    graphql_variables: dict[str, Any]
    warnings: tuple[str, ...] = ()


def build_endpoint_query_context(
    config: Any,
    plan_unit: Any | None = None,
    *,
    metric_date: str | None = None,
    group_name: str | None = None,
) -> EndpointQueryContext:
    filters = _resolve_filters(config)
    dimensions = _normalize_string_list(getattr(config, "dimensions", []))
    metrics = _normalize_string_list(getattr(config, "metrics", []))
    top_n = _resolve_optional_int(getattr(config, "top_n", None))
    sort_by = _resolve_text(getattr(config, "sort_by", None))
    include_long_tail = bool(getattr(config, "include_long_tail", False))
    session_level = bool(getattr(config, "session_level", False))
    granularity = _resolve_text(getattr(config, "granularity", None)) or "DAY"
    shop_id = _resolve_shop_id(config, plan_unit)
    resolved_metric_date = (
        metric_date
        or _resolve_text(getattr(plan_unit, "metric_date", None))
        or datetime.utcnow().date().isoformat()
    )

    cursor = _resolve_cursor(config=config, plan_unit=plan_unit, filters=filters)
    unknown_filters = tuple(_resolve_unknown_filter_keys(filters))

    params: dict[str, Any] = {
        "shop_id": shop_id,
        "date": resolved_metric_date,
        "granularity": granularity,
        "filters": dict(filters),
        "dimensions": list(dimensions),
        "metrics": list(metrics),
        "include_long_tail": include_long_tail,
        "session_level": session_level,
    }
    if top_n is not None:
        params["top_n"] = top_n
    if sort_by is not None:
        params["sort_by"] = sort_by
    if cursor is not None:
        params["cursor"] = cursor
    if group_name:
        params["group"] = group_name

    json_body: dict[str, Any] = {
        "filters": dict(filters),
        "dimensions": list(dimensions),
        "metrics": list(metrics),
        "include_long_tail": include_long_tail,
        "session_level": session_level,
    }
    if top_n is not None:
        json_body["top_n"] = top_n
    if sort_by is not None:
        json_body["sort_by"] = sort_by
    if cursor is not None:
        json_body["cursor"] = cursor
    if plan_unit is not None:
        window_start = getattr(plan_unit, "window_start", None)
        window_end = getattr(plan_unit, "window_end", None)
        if isinstance(window_start, datetime):
            json_body["window_start"] = window_start.isoformat()
        if isinstance(window_end, datetime):
            json_body["window_end"] = window_end.isoformat()

    graphql_variables = {
        "shopId": shop_id,
        "date": resolved_metric_date,
        "filters": dict(filters),
        "dimensions": list(dimensions),
        "metrics": list(metrics),
        "includeLongTail": include_long_tail,
        "sessionLevel": session_level,
    }
    if top_n is not None:
        graphql_variables["topN"] = top_n
    if sort_by is not None:
        graphql_variables["sortBy"] = sort_by
    if cursor is not None:
        graphql_variables["cursor"] = cursor

    warnings = tuple(f"unknown_filter:{key}" for key in unknown_filters)
    return EndpointQueryContext(
        params=params,
        json_body=json_body,
        graphql_variables=graphql_variables,
        warnings=warnings,
    )


def _resolve_filters(config: Any) -> dict[str, Any]:
    raw_filters = getattr(config, "filters", None)
    if not isinstance(raw_filters, dict):
        return {}
    return {str(k): v for k, v in raw_filters.items() if k is not None}


def _resolve_shop_id(config: Any, plan_unit: Any | None) -> str:
    if plan_unit is not None:
        value = _resolve_text(getattr(plan_unit, "shop_id", None))
        if value:
            return value
    value = _resolve_text(getattr(config, "shop_id", None))
    if value:
        return value
    filters = _resolve_filters(config)
    filter_shop_id = filters.get("shop_id")
    if isinstance(filter_shop_id, list) and filter_shop_id:
        parsed = _resolve_text(filter_shop_id[0])
        if parsed:
            return parsed
    if isinstance(filter_shop_id, str):
        parsed = _resolve_text(filter_shop_id.split(",")[0])
        if parsed:
            return parsed
    return ""


def _resolve_cursor(
    *,
    config: Any,
    plan_unit: Any | None,
    filters: dict[str, Any],
) -> str | None:
    plan_cursor = _resolve_text(getattr(plan_unit, "cursor", None))
    if plan_cursor:
        return plan_cursor
    filter_cursor = _resolve_text(filters.get("cursor"))
    if filter_cursor:
        return filter_cursor
    extra_config = getattr(config, "extra_config", None)
    if isinstance(extra_config, dict):
        extra_cursor = _resolve_text(extra_config.get("cursor"))
        if extra_cursor:
            return extra_cursor
    return None


def _resolve_unknown_filter_keys(filters: dict[str, Any]) -> list[str]:
    known_filter_keys = {
        "shop_id",
        "cursor",
        "date",
        "region",
        "product_id",
        "category_id",
        "brand_id",
        "keyword",
        "status",
        "source",
    }
    unknown = [key for key in filters if key not in known_filter_keys]
    unknown.sort()
    return unknown


def _normalize_string_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        parsed = [values]
    elif isinstance(values, list | tuple | set):
        parsed = list(values)
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in parsed:
        text = _resolve_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _resolve_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
