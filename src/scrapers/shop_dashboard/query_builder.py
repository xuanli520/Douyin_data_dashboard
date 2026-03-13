from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EndpointQueryContext:
    params: dict[str, Any]
    json_body: dict[str, Any]
    graphql_variables: dict[str, Any]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EndpointRequestPayload:
    params: dict[str, Any] | None
    json_body: dict[str, Any] | None
    warnings: tuple[str, ...] = ()


def build_endpoint_query_context(
    config: Any,
    plan_unit: Any | None = None,
    *,
    metric_date: str | None = None,
    group_name: str | None = None,
) -> EndpointQueryContext:
    filters = _resolve_filters(config, plan_unit)
    dimensions = _normalize_string_list(getattr(config, "dimensions", []))
    metrics = _normalize_string_list(getattr(config, "metrics", []))
    top_n = _resolve_optional_int(getattr(config, "top_n", None))
    sort_by = _resolve_text(getattr(config, "sort_by", None))
    include_long_tail = bool(getattr(config, "include_long_tail", False))
    session_level = bool(getattr(config, "session_level", False))
    granularity = _resolve_text(getattr(config, "granularity", None)) or "DAY"
    shop_id = _resolve_shop_id(config, plan_unit)
    filters = _force_target_shop_filter(filters=filters, shop_id=shop_id)
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


def build_endpoint_request_payload(
    config: Any,
    *,
    metric_date: str,
    group_name: str,
    base_params: Mapping[str, Any] | None = None,
    base_json_body: Mapping[str, Any] | None = None,
    requires_graphql_query: bool = False,
    graphql_query: str | None = None,
) -> EndpointRequestPayload:
    query_context = build_endpoint_query_context(
        config,
        metric_date=metric_date,
        group_name=group_name,
    )
    params = dict(base_params or {})
    params.update(flatten_query_context_params(query_context.params))
    resolved_params = params or None

    resolved_json_body: dict[str, Any] | None
    if requires_graphql_query:
        if not graphql_query:
            resolved_json_body = None
        else:
            resolved_json_body = {
                "operationName": "ExperienceScoreHome",
                "query": graphql_query,
                "variables": dict(query_context.graphql_variables),
            }
    else:
        resolved_json_body = dict(base_json_body or {}) if base_json_body else None
        if query_context.json_body:
            if resolved_json_body is None:
                resolved_json_body = {}
            resolved_json_body.update(query_context.json_body)
    return EndpointRequestPayload(
        params=resolved_params,
        json_body=resolved_json_body,
        warnings=query_context.warnings,
    )


def flatten_query_context_params(params: Mapping[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if key == "filters" and isinstance(value, Mapping):
            for filter_key, filter_value in value.items():
                if filter_value is None:
                    continue
                flattened[f"filter_{filter_key}"] = filter_value
            continue
        if key in {"dimensions", "metrics"} and isinstance(value, list):
            flattened[key] = ",".join(str(item) for item in value if item is not None)
            continue
        flattened[key] = value
    return flattened


def _resolve_filters(config: Any, plan_unit: Any | None) -> dict[str, Any]:
    effective_filters = _resolve_effective_filters(config=config, plan_unit=plan_unit)
    if effective_filters:
        filters: dict[str, Any] = {}
        extra_filters = effective_filters.get("extra_filters")
        if isinstance(extra_filters, dict):
            for key, value in extra_filters.items():
                resolved_key = _resolve_filter_key(key)
                if resolved_key is None:
                    continue
                filters[resolved_key] = value
        date_range = effective_filters.get("date_range")
        if isinstance(date_range, dict):
            filters["date_range"] = dict(date_range)
        return _strip_internal_filters(filters)
    raw_filters = getattr(config, "filters", None)
    if not isinstance(raw_filters, dict):
        return {}
    normalized_filters: dict[str, Any] = {}
    for key, value in raw_filters.items():
        resolved_key = _resolve_filter_key(key)
        if resolved_key is None:
            continue
        normalized_filters[resolved_key] = value
    return _strip_internal_filters(normalized_filters)


def _resolve_shop_id(config: Any, plan_unit: Any | None) -> str:
    if plan_unit is not None:
        target_shop_id = _resolve_text(getattr(plan_unit, "target_shop_id", None))
        if target_shop_id:
            return target_shop_id
        value = _resolve_text(getattr(plan_unit, "shop_id", None))
        if value:
            return value
    value = _resolve_text(getattr(config, "shop_id", None))
    if value:
        return value
    resolved_shop_ids = _normalize_string_list(getattr(config, "resolved_shop_ids", []))
    if resolved_shop_ids:
        return resolved_shop_ids[0]
    return ""


def _resolve_cursor(
    *,
    config: Any,
    plan_unit: Any | None,
    filters: dict[str, Any],
) -> str | None:
    effective_filters = _resolve_effective_filters(config=config, plan_unit=plan_unit)
    if isinstance(effective_filters, dict):
        effective_cursor = _resolve_text(effective_filters.get("cursor"))
        if effective_cursor:
            return effective_cursor
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
        "date_range",
        "region",
        "product_id",
        "category_id",
        "brand_id",
        "keyword",
        "status",
        "source",
        "all",
        "catalog_stale",
        "shop_resolve_source",
    }
    unknown: list[str] = []
    for key in filters:
        normalized_key = _normalized_filter_key_for_matching(key)
        if normalized_key in known_filter_keys:
            continue
        unknown.append(str(key))
    unknown.sort()
    return unknown


def _strip_internal_filters(filters: dict[str, Any]) -> dict[str, Any]:
    internal_filter_keys = {"all", "catalog_stale", "shop_resolve_source"}
    sanitized: dict[str, Any] = {}
    for key, value in filters.items():
        normalized_key = _normalized_filter_key_for_matching(key)
        if normalized_key in internal_filter_keys:
            continue
        sanitized[str(key)] = value
    return sanitized


def _resolve_filter_key(value: Any) -> str | None:
    text = _resolve_text(value)
    if not text:
        return None
    if text.lower().startswith("filter_"):
        stripped = text[7:].strip()
        if stripped:
            return stripped
    return text


def _normalized_filter_key_for_matching(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("filter_"):
        text = text[7:].strip()
    return text


def _force_target_shop_filter(
    *,
    filters: dict[str, Any],
    shop_id: str,
) -> dict[str, Any]:
    normalized_shop_id = str(shop_id or "").strip()
    if not normalized_shop_id:
        return dict(filters)
    forced = dict(filters)
    forced["shop_id"] = normalized_shop_id
    return forced


def _resolve_effective_filters(config: Any, plan_unit: Any | None) -> dict[str, Any]:
    if plan_unit is not None:
        value = getattr(plan_unit, "effective_filters", None)
        if isinstance(value, dict):
            return dict(value)
    value = getattr(config, "effective_filters", None)
    if isinstance(value, dict):
        return dict(value)
    return {}


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
