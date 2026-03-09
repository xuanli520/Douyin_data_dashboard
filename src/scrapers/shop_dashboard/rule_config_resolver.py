from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from src.domains.data_source.models import DataSource, ScrapingRule

DEFAULT_GROUPS_BY_TARGET: dict[str, list[str]] = {
    "SHOP_OVERVIEW": [
        "overview",
        "analysis",
        "diagnosis",
        "graphql",
        "cash_info",
        "score_node",
        "ticket_count",
        "enum_config",
        "waiting_list",
        "top_rule",
        "high_frequency",
    ],
    "CUSTOMER": ["statistics", "comment_list", "unreply", "tags", "products"],
    "AFTERSALE_REFUND": [
        "cash_info",
        "score_node",
        "ticket_count",
        "enum_config",
        "waiting_list",
        "top_rule",
        "high_frequency",
    ],
}

METRIC_TO_GROUP: dict[str, str] = {
    "overview": "overview",
    "analysis": "analysis",
    "diagnosis": "diagnosis",
    "graphql": "graphql",
    "statistics": "statistics",
    "commentlist": "comment_list",
    "comment_list": "comment_list",
    "unreply": "unreply",
    "tags": "tags",
    "products": "products",
    "cash_info": "cash_info",
    "score_node": "score_node",
    "ticket": "ticket_count",
    "ticket_count": "ticket_count",
    "enum": "enum_config",
    "enum_config": "enum_config",
    "waiting": "waiting_list",
    "waiting_list": "waiting_list",
    "top_rule": "top_rule",
    "high_frequency": "high_frequency",
}

VALID_GRANULARITY = {"HOUR", "DAY", "WEEK", "MONTH"}
VALID_INCREMENTAL_MODE = {"BY_DATE", "BY_CURSOR"}


@dataclass(slots=True)
class ResolvedRuleConfig:
    rule_id: int
    execution_id: str
    target_type: str
    granularity: str
    timezone: str
    time_range: dict[str, Any] | None
    schedule: dict[str, Any] | None
    incremental_mode: str
    backfill_last_n_days: int
    data_latency: str
    proxy: str | None
    timeout: int
    retry_count: int
    filters: dict[str, Any]
    dimensions: list[str]
    metrics: list[str]
    dedupe_key: str | None
    rate_limit: int | dict[str, Any] | None
    top_n: int | None
    sort_by: str | None
    include_long_tail: bool
    session_level: bool
    extra_config: dict[str, Any]
    shop_id: str
    shop_ids: list[str]
    api_groups: list[str]
    rate_limit_policy: int | dict[str, Any] | None
    fallback_chain: tuple[str, ...]
    graphql_query: str | None
    common_query: dict[str, Any]
    token_keys: list[str]
    account_id: str
    cookies: dict[str, str]
    storage_state: dict[str, Any] | None
    cursor: str | None


def resolve_rule_config(
    *,
    data_source: DataSource,
    rule: ScrapingRule,
    execution_id: str,
    overrides: dict[str, Any] | None = None,
) -> ResolvedRuleConfig:
    ds_extra = _as_dict(data_source.extra_config)
    rule_extra = _as_dict(rule.extra_config)
    payload = _as_dict(overrides)
    payload_extra = _as_dict(payload.get("extra_config"))

    def pick(
        key: str,
        *,
        rule_value: Any = None,
        ds_value: Any = None,
        default: Any = None,
    ) -> Any:
        if key in payload and payload[key] is not None:
            return payload[key]
        if key in payload_extra and payload_extra[key] is not None:
            return payload_extra[key]
        if rule_value is not None:
            return rule_value
        if key in rule_extra and rule_extra[key] is not None:
            return rule_extra[key]
        if key in ds_extra and ds_extra[key] is not None:
            return ds_extra[key]
        if ds_value is not None:
            return ds_value
        return default

    rule_id = int(rule.id or 0)

    target_type = _normalize_text(
        pick(
            "target_type",
            rule_value=_enum_value(rule.target_type),
            default="SHOP_OVERVIEW",
        ),
        field="target_type",
        rule_id=rule_id,
        fallback="SHOP_OVERVIEW",
    ).upper()
    granularity = _normalize_granularity(
        pick(
            "granularity",
            rule_value=_enum_value(rule.granularity),
            default="DAY",
        ),
        rule_id=rule_id,
    )
    timezone = _normalize_text(
        pick(
            "timezone",
            rule_value=rule.timezone,
            default="Asia/Shanghai",
        ),
        field="timezone",
        rule_id=rule_id,
        fallback="Asia/Shanghai",
    )
    schedule = _normalize_optional_dict(
        pick("schedule", rule_value=rule.schedule, default=None),
        field="schedule",
        rule_id=rule_id,
    )
    time_range = _normalize_optional_dict(
        pick("time_range", rule_value=rule.time_range, default=None),
        field="time_range",
        rule_id=rule_id,
    )
    incremental_mode = _normalize_incremental_mode(
        pick(
            "incremental_mode",
            rule_value=_enum_value(rule.incremental_mode),
            default="BY_DATE",
        ),
        rule_id=rule_id,
    )
    backfill_last_n_days = _normalize_non_negative_int(
        pick(
            "backfill_last_n_days",
            rule_value=rule.backfill_last_n_days,
            default=3,
        ),
        field="backfill_last_n_days",
        rule_id=rule_id,
    )
    data_latency = _normalize_data_latency(
        pick(
            "data_latency",
            rule_value=_enum_value(rule.data_latency),
            default="T+1",
        ),
        rule_id=rule_id,
    )
    proxy = _normalize_nullable_text(pick("proxy", default=None))
    timeout = _normalize_non_negative_int(
        pick("timeout", ds_value=data_source.timeout, default=30),
        field="timeout",
        rule_id=rule_id,
    )
    retry_count = _normalize_non_negative_int(
        pick("retry_count", ds_value=data_source.retry_count, default=3),
        field="retry_count",
        rule_id=rule_id,
    )

    filters = (
        _normalize_optional_dict(
            pick("filters", rule_value=rule.filters, default={}),
            field="filters",
            rule_id=rule_id,
        )
        or {}
    )
    dimensions = _normalize_string_list(
        pick("dimensions", rule_value=rule.dimensions, default=[]),
        field="dimensions",
        rule_id=rule_id,
    )
    metrics = _normalize_string_list(
        pick("metrics", rule_value=rule.metrics, default=[]),
        field="metrics",
        rule_id=rule_id,
    )

    dedupe_key = _normalize_nullable_text(
        pick("dedupe_key", rule_value=rule.dedupe_key, default=None)
    )
    rate_limit = _normalize_rate_limit(
        pick(
            "rate_limit",
            rule_value=rule.rate_limit,
            ds_value=data_source.rate_limit,
            default=100,
        ),
        rule_id=rule_id,
    )
    top_n = _normalize_optional_int(
        pick("top_n", rule_value=rule.top_n, default=None),
        field="top_n",
        rule_id=rule_id,
    )
    sort_by = _normalize_nullable_text(
        pick("sort_by", rule_value=rule.sort_by, default=None)
    )
    include_long_tail = _normalize_bool(
        pick("include_long_tail", rule_value=rule.include_long_tail, default=False),
        field="include_long_tail",
        rule_id=rule_id,
    )
    session_level = _normalize_bool(
        pick("session_level", rule_value=rule.session_level, default=False),
        field="session_level",
        rule_id=rule_id,
    )

    explicit_shop_id = _normalize_nullable_text(
        pick("shop_id", ds_value=data_source.shop_id, default=None)
    )
    raw_shop_ids = pick("shop_ids", default=None)
    if raw_shop_ids is None:
        raw_shop_ids = filters.get("shop_id")
    shop_ids = _normalize_shop_ids(raw_shop_ids, rule_id=rule_id)
    if not shop_ids and explicit_shop_id:
        shop_ids = [explicit_shop_id]
    shop_id = explicit_shop_id or (shop_ids[0] if shop_ids else "")
    if shop_ids:
        filters["shop_id"] = list(shop_ids)
    elif "shop_id" in filters:
        filters["shop_id"] = []

    merged_extra = dict(ds_extra)
    merged_extra.update(rule_extra)
    merged_extra.update(payload_extra)

    raw_login_state = merged_extra.get("shop_dashboard_login_state")
    login_state = raw_login_state if isinstance(raw_login_state, dict) else {}
    raw_login_state_meta = merged_extra.get("shop_dashboard_login_state_meta")
    login_state_meta = (
        raw_login_state_meta if isinstance(raw_login_state_meta, dict) else {}
    )
    storage_state = _parse_storage_state(login_state.get("storage_state"))
    storage_state_cookies = _parse_storage_state_cookie_mapping(storage_state)
    cookies = storage_state_cookies or _parse_cookie_mapping(
        pick("cookies", default={})
    )

    account_id = (
        _normalize_nullable_text(pick("account_id", default=""))
        or _normalize_nullable_text(login_state_meta.get("account_id"))
        or _normalize_nullable_text(pick("user_phone", default=""))
        or f"shop_{shop_id}"
    )

    explicit_groups = pick("api_groups", default=None)
    api_groups = _resolve_api_groups(
        target_type=target_type,
        metrics=metrics,
        explicit_groups=explicit_groups,
    )
    api_groups = _normalize_string_list(
        api_groups,
        field="api_groups",
        rule_id=rule_id,
    )

    fallback = pick("fallback_chain", default="http->browser->llm")
    fallback_chain = _normalize_fallback_chain(fallback)
    graphql_query = _normalize_nullable_text(pick("graphql_query", default=None))

    common_query = _as_dict(ds_extra.get("common_query"))
    common_query.update(_as_dict(rule_extra.get("common_query")))
    common_query.update(_as_dict(payload_extra.get("common_query")))
    common_query.update(_as_dict(payload.get("common_query")))

    token_keys = _normalize_string_list(
        pick("token_keys", default=[]),
        field="token_keys",
        rule_id=rule_id,
    )

    cursor = _normalize_nullable_text(filters.get("cursor"))
    if cursor is None:
        cursor = _normalize_nullable_text(merged_extra.get("cursor"))

    return ResolvedRuleConfig(
        rule_id=rule_id,
        execution_id=execution_id,
        target_type=target_type,
        granularity=granularity,
        timezone=timezone,
        time_range=time_range,
        schedule=schedule,
        incremental_mode=incremental_mode,
        backfill_last_n_days=backfill_last_n_days,
        data_latency=data_latency,
        proxy=proxy,
        timeout=max(timeout, 1),
        retry_count=max(retry_count, 0),
        filters=filters,
        dimensions=dimensions,
        metrics=metrics,
        dedupe_key=dedupe_key,
        rate_limit=rate_limit,
        top_n=top_n,
        sort_by=sort_by,
        include_long_tail=include_long_tail,
        session_level=session_level,
        extra_config=merged_extra,
        shop_id=shop_id,
        shop_ids=shop_ids,
        api_groups=api_groups,
        rate_limit_policy=rate_limit,
        fallback_chain=fallback_chain,
        graphql_query=graphql_query,
        common_query=common_query,
        token_keys=token_keys,
        account_id=account_id,
        cookies=cookies,
        storage_state=storage_state,
        cursor=cursor,
    )


def _resolve_api_groups(
    *,
    target_type: str,
    metrics: list[str],
    explicit_groups: Any,
) -> list[str]:
    if isinstance(explicit_groups, list):
        normalized = [
            str(item).strip() for item in explicit_groups if str(item).strip()
        ]
        if normalized:
            return normalized
    defaults = list(DEFAULT_GROUPS_BY_TARGET.get(target_type, []))
    if not metrics:
        return defaults
    metric_groups = []
    for metric in metrics:
        key = str(metric).strip().lower()
        group = METRIC_TO_GROUP.get(key, key)
        metric_groups.append(group)
    if not defaults:
        return list(dict.fromkeys(metric_groups))
    metric_group_set = set(metric_groups)
    return [group for group in defaults if group in metric_group_set]


def _normalize_granularity(value: Any, *, rule_id: int) -> str:
    normalized = _normalize_text(
        value,
        field="granularity",
        rule_id=rule_id,
        fallback="DAY",
    ).upper()
    if normalized not in VALID_GRANULARITY:
        _invalid_field("granularity", value, rule_id=rule_id)
    return normalized


def _normalize_incremental_mode(value: Any, *, rule_id: int) -> str:
    normalized = _normalize_text(
        value,
        field="incremental_mode",
        rule_id=rule_id,
        fallback="BY_DATE",
    ).upper()
    if normalized not in VALID_INCREMENTAL_MODE:
        _invalid_field("incremental_mode", value, rule_id=rule_id)
    return normalized


def _normalize_data_latency(value: Any, *, rule_id: int) -> str:
    normalized = _normalize_text(
        value,
        field="data_latency",
        rule_id=rule_id,
        fallback="T+1",
    ).upper()
    if normalized == "REALTIME":
        return normalized
    if normalized.startswith("T+") and normalized[2:].isdigit():
        return normalized
    _invalid_field("data_latency", value, rule_id=rule_id)


def _normalize_rate_limit(value: Any, *, rule_id: int) -> int | dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        _invalid_field("rate_limit", value, rule_id=rule_id)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        _invalid_field("rate_limit", value, rule_id=rule_id)
    if isinstance(value, Mapping):
        return dict(value)
    _invalid_field("rate_limit", value, rule_id=rule_id)


def _normalize_non_negative_int(value: Any, *, field: str, rule_id: int) -> int:
    parsed = _normalize_optional_int(value, field=field, rule_id=rule_id)
    if parsed is None:
        return 0
    return max(parsed, 0)


def _normalize_optional_int(value: Any, *, field: str, rule_id: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        _invalid_field(field, value, rule_id=rule_id)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            _invalid_field(field, value, rule_id=rule_id)
    _invalid_field(field, value, rule_id=rule_id)


def _normalize_bool(value: Any, *, field: str, rule_id: int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off", ""}:
            return False
    _invalid_field(field, value, rule_id=rule_id)


def _normalize_optional_dict(
    value: Any,
    *,
    field: str,
    rule_id: int,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    _invalid_field(field, value, rule_id=rule_id)


def _normalize_string_list(value: Any, *, field: str, rule_id: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _normalize_string_items([value])
    if isinstance(value, Iterable) and not isinstance(value, Mapping):
        return _normalize_string_items(value)
    _invalid_field(field, value, rule_id=rule_id)


def _normalize_shop_ids(value: Any, *, rule_id: int) -> list[str]:
    if value is None:
        return []
    items: list[Any]
    if isinstance(value, str):
        cleaned = value.replace(";", ",")
        items = [part for chunk in cleaned.split(",") for part in chunk.split("|")]
    elif isinstance(value, Iterable) and not isinstance(value, Mapping):
        items = list(value)
    else:
        _invalid_field("filters.shop_id", value, rule_id=rule_id)
    return _normalize_string_items(items)


def _normalize_string_items(items: Iterable[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _normalize_fallback_chain(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = [
            part.strip().lower() for part in value.split("->") if part and part.strip()
        ]
    elif isinstance(value, (list, tuple)):
        parts = [str(part).strip().lower() for part in value if str(part).strip()]
    else:
        parts = ["http", "browser", "llm"]
    if not parts:
        parts = ["http", "browser", "llm"]
    normalized = ["agent" if part in {"agent", "llm"} else part for part in parts]
    return tuple(normalized)


def _normalize_text(
    value: Any,
    *,
    field: str,
    rule_id: int,
    fallback: str,
) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if text:
        return text
    if fallback:
        return fallback
    _invalid_field(field, value, rule_id=rule_id)


def _normalize_nullable_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _invalid_field(field: str, value: Any, *, rule_id: int) -> None:
    raise ValueError(
        f"invalid scraping rule config: rule_id={rule_id}, field={field}, value={value!r}"
    )


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _parse_storage_state(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        cookies = value.get("cookies")
        origins = value.get("origins")
        if isinstance(cookies, list) and (origins is None or isinstance(origins, list)):
            return {
                "cookies": cookies,
                "origins": origins if isinstance(origins, list) else [],
            }
        return None
    return None


def _parse_storage_state_cookie_mapping(
    storage_state: dict[str, Any] | None,
) -> dict[str, str]:
    if not storage_state:
        return {}
    cookies = storage_state.get("cookies")
    if not isinstance(cookies, list):
        return {}
    mapping: dict[str, str] = {}
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        cookie_value = cookie.get("value")
        if name is None or cookie_value is None:
            continue
        mapping[str(name)] = str(cookie_value)
    return mapping


def _parse_cookie_mapping(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items() if v is not None}
    if isinstance(value, str):
        cookie_pairs = [item.strip() for item in value.split(";") if item.strip()]
        parsed: dict[str, str] = {}
        for pair in cookie_pairs:
            if "=" not in pair:
                continue
            key, raw_value = pair.split("=", 1)
            parsed[key.strip()] = raw_value.strip()
        return parsed
    return {}
