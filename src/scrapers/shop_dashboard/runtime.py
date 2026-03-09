from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domains.data_source.models import DataSource, ScrapingRule
from src.scrapers.shop_dashboard.rule_config_resolver import (
    ResolvedRuleConfig,
    resolve_rule_config,
)

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


@dataclass(slots=True)
class ShopDashboardRuntimeConfig:
    shop_id: str
    cookies: dict[str, str]
    proxy: str | None
    timeout: int
    retry_count: int
    rate_limit: int | dict[str, Any] | None
    granularity: str
    time_range: dict[str, Any] | None
    incremental_mode: str
    backfill_last_n_days: int
    data_latency: str
    target_type: str
    metrics: list[str]
    dimensions: list[str]
    filters: dict[str, Any]
    top_n: int | None
    include_long_tail: bool
    session_level: bool
    dedupe_key: str | None
    rule_id: int
    execution_id: str
    fallback_chain: tuple[str, ...]
    graphql_query: str | None
    common_query: dict[str, Any]
    token_keys: list[str]
    api_groups: list[str]
    timezone: str = "Asia/Shanghai"
    schedule: dict[str, Any] | None = None
    sort_by: str | None = None
    extra_config: dict[str, Any] | None = None
    cursor: str | None = None
    account_id: str = ""
    storage_state: dict[str, Any] | None = None


def build_runtime_config(
    data_source: DataSource,
    rule: ScrapingRule,
    execution_id: str,
    overrides: dict[str, Any] | None = None,
) -> ShopDashboardRuntimeConfig:
    runtimes = build_runtime_configs(
        data_source=data_source,
        rule=rule,
        execution_id=execution_id,
        overrides=overrides,
    )
    if runtimes:
        return runtimes[0]
    return ShopDashboardRuntimeConfig(
        shop_id="",
        cookies={},
        proxy=None,
        timeout=int(data_source.timeout or 30),
        retry_count=int(data_source.retry_count or 3),
        rate_limit=data_source.rate_limit,
        granularity="DAY",
        time_range=None,
        incremental_mode="BY_DATE",
        backfill_last_n_days=0,
        data_latency="T+1",
        target_type="SHOP_OVERVIEW",
        metrics=[],
        dimensions=[],
        filters={},
        top_n=None,
        include_long_tail=False,
        session_level=False,
        dedupe_key=None,
        rule_id=int(rule.id or 0),
        execution_id=execution_id,
        fallback_chain=("http", "browser", "agent"),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=[],
    )


def build_runtime_configs(
    data_source: DataSource,
    rule: ScrapingRule,
    execution_id: str,
    overrides: dict[str, Any] | None = None,
) -> list[ShopDashboardRuntimeConfig]:
    resolved = resolve_rule_config(
        data_source=data_source,
        rule=rule,
        execution_id=execution_id,
        overrides=overrides,
    )
    shop_ids = list(resolved.shop_ids)
    if not shop_ids:
        shop_ids = [resolved.shop_id]
    if not shop_ids:
        return []
    return [_build_runtime_from_resolved(resolved, shop_id) for shop_id in shop_ids]


def _build_runtime_from_resolved(
    resolved: ResolvedRuleConfig,
    shop_id: str,
) -> ShopDashboardRuntimeConfig:
    return ShopDashboardRuntimeConfig(
        shop_id=str(shop_id).strip(),
        cookies=dict(resolved.cookies),
        proxy=resolved.proxy,
        timeout=resolved.timeout,
        retry_count=resolved.retry_count,
        rate_limit=resolved.rate_limit,
        granularity=resolved.granularity,
        time_range=dict(resolved.time_range) if resolved.time_range else None,
        incremental_mode=resolved.incremental_mode,
        backfill_last_n_days=resolved.backfill_last_n_days,
        data_latency=resolved.data_latency,
        target_type=resolved.target_type,
        timezone=resolved.timezone,
        schedule=dict(resolved.schedule) if resolved.schedule else None,
        metrics=list(resolved.metrics),
        dimensions=list(resolved.dimensions),
        filters=dict(resolved.filters),
        top_n=resolved.top_n,
        sort_by=resolved.sort_by,
        include_long_tail=resolved.include_long_tail,
        session_level=resolved.session_level,
        dedupe_key=resolved.dedupe_key,
        rule_id=resolved.rule_id,
        execution_id=resolved.execution_id,
        fallback_chain=tuple(resolved.fallback_chain),
        graphql_query=resolved.graphql_query,
        common_query=dict(resolved.common_query),
        token_keys=list(resolved.token_keys),
        api_groups=list(resolved.api_groups),
        extra_config=dict(resolved.extra_config),
        cursor=resolved.cursor,
        account_id=resolved.account_id,
        storage_state=dict(resolved.storage_state) if resolved.storage_state else None,
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
    return [group for group in defaults if group in set(metric_groups)]


def _ensure_required_api_groups(groups: list[str]) -> list[str]:
    normalized = [str(group).strip() for group in groups if str(group).strip()]
    return list(dict.fromkeys(normalized))


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
        value = cookie.get("value")
        if name is None or value is None:
            continue
        mapping[str(name)] = str(value)
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
