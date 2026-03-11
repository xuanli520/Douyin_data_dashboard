from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.scrapers.shop_dashboard.rule_config_resolver import (
    ResolvedRuleConfig,
    resolve_rule_config,
)


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
    sort_by: str | None = None
    extra_config: dict[str, Any] | None = None
    cursor: str | None = None
    account_id: str = ""
    storage_state: dict[str, Any] | None = None


def build_runtime_config(
    data_source: Any,
    rule: Any,
    execution_id: str,
    overrides: dict[str, Any] | None = None,
) -> ShopDashboardRuntimeConfig:
    if not str(execution_id).strip():
        raise ValueError("execution_id cannot be empty")
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
        timeout=int(_read_source_value(data_source, "timeout", 30) or 30),
        retry_count=int(_read_source_value(data_source, "retry_count", 3) or 3),
        rate_limit=_read_source_value(data_source, "rate_limit", None),
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
        rule_id=int(_read_source_value(rule, "id", 0) or 0),
        execution_id=execution_id,
        fallback_chain=("http", "browser", "agent"),
        graphql_query=None,
        common_query={},
        token_keys=[],
        api_groups=[],
    )


def build_runtime_configs(
    data_source: Any,
    rule: Any,
    execution_id: str,
    overrides: dict[str, Any] | None = None,
) -> list[ShopDashboardRuntimeConfig]:
    if not str(execution_id).strip():
        raise ValueError("execution_id cannot be empty")
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


def _read_source_value(source: Any, key: str, default: Any) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


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
