from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domains.data_source.models import DataSource, ScrapingRule

DEFAULT_GROUPS_BY_TARGET: dict[str, list[str]] = {
    "SHOP_OVERVIEW": ["overview", "analysis", "diagnosis", "graphql"],
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
    account_id: str = ""


def build_runtime_config(
    data_source: DataSource,
    rule: ScrapingRule,
    execution_id: str,
) -> ShopDashboardRuntimeConfig:
    rule_extra = dict(rule.extra_config or {})
    ds_extra = dict(data_source.extra_config or {})

    def pick(
        key: str,
        *,
        rule_value: Any = None,
        ds_value: Any = None,
        default: Any = None,
    ) -> Any:
        if key in rule_extra and rule_extra[key] is not None:
            return rule_extra[key]
        if rule_value is not None:
            return rule_value
        if key in ds_extra and ds_extra[key] is not None:
            return ds_extra[key]
        if ds_value is not None:
            return ds_value
        return default

    target_type = str(
        rule.target_type.value
        if hasattr(rule.target_type, "value")
        else rule.target_type
    )
    metrics = list(rule.metrics or [])
    api_groups = _resolve_api_groups(
        target_type=target_type,
        metrics=metrics,
        explicit_groups=rule_extra.get("api_groups"),
    )
    shop_id = str(pick("shop_id", ds_value=data_source.shop_id, default=""))
    account_id = (
        str(pick("account_id", default="")).strip()
        or str(pick("user_phone", default="")).strip()
        or f"shop_{shop_id}"
    )
    common_query = dict(ds_extra.get("common_query") or {})
    common_query.update(dict(rule_extra.get("common_query") or {}))

    fallback = pick(key="fallback_chain", default="http->browser->llm")
    if isinstance(fallback, str):
        fallback_chain = tuple(
            part.strip().lower() for part in fallback.split("->") if part.strip()
        )
    elif isinstance(fallback, (list, tuple)):
        fallback_chain = tuple(
            str(part).strip().lower() for part in fallback if str(part).strip()
        )
    else:
        fallback_chain = ("http", "browser", "llm")
    if not fallback_chain:
        fallback_chain = ("http", "browser", "llm")

    return ShopDashboardRuntimeConfig(
        shop_id=shop_id,
        cookies=_parse_cookie_mapping(
            pick("cookies", ds_value=data_source.cookies, default={})
        ),
        proxy=pick("proxy", ds_value=data_source.proxy),
        timeout=int(pick("timeout", ds_value=data_source.timeout, default=30)),
        retry_count=int(
            pick("retry_count", ds_value=data_source.retry_count, default=3)
        ),
        rate_limit=pick(
            "rate_limit",
            rule_value=rule.rate_limit,
            ds_value=data_source.rate_limit,
            default=100,
        ),
        granularity=str(
            pick(
                "granularity",
                rule_value=rule.granularity.value
                if hasattr(rule.granularity, "value")
                else rule.granularity,
                default="DAY",
            )
        ),
        time_range=pick("time_range", rule_value=rule.time_range, default=None),
        incremental_mode=str(
            pick(
                "incremental_mode",
                rule_value=rule.incremental_mode.value
                if hasattr(rule.incremental_mode, "value")
                else rule.incremental_mode,
                default="BY_DATE",
            )
        ),
        backfill_last_n_days=int(
            pick(
                "backfill_last_n_days",
                rule_value=rule.backfill_last_n_days,
                default=3,
            )
        ),
        data_latency=str(
            pick(
                "data_latency",
                rule_value=rule.data_latency.value
                if hasattr(rule.data_latency, "value")
                else rule.data_latency,
                default="T+1",
            )
        ),
        target_type=target_type,
        metrics=metrics,
        dimensions=list(rule.dimensions or []),
        filters=dict(rule.filters or {}),
        top_n=pick("top_n", rule_value=rule.top_n, default=None),
        include_long_tail=bool(
            pick("include_long_tail", rule_value=rule.include_long_tail, default=False)
        ),
        session_level=bool(
            pick("session_level", rule_value=rule.session_level, default=False)
        ),
        dedupe_key=pick("dedupe_key", rule_value=rule.dedupe_key, default=None),
        rule_id=rule.id if rule.id is not None else 0,
        execution_id=execution_id,
        fallback_chain=fallback_chain,
        graphql_query=pick("graphql_query", default=None),
        common_query=common_query,
        token_keys=list(pick("token_keys", default=[])),
        api_groups=api_groups,
        account_id=account_id,
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
