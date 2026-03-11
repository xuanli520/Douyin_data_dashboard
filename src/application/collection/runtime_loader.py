from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.data_source.enums import DataSourceStatus
from src.domains.data_source.enums import ScrapingRuleStatus
from src.domains.data_source.repository import DataSourceRepository
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.task.exceptions import ScrapingFailedException
from src.scrapers.shop_dashboard.contracts import DataSourceContract
from src.scrapers.shop_dashboard.contracts import ScrapingRuleContract
from src.scrapers.shop_dashboard.account_shop_resolver import AccountShopResolver
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.runtime import build_runtime_config


@dataclass(slots=True)
class LoadedCollectionRuntime:
    runtime: ShopDashboardRuntimeConfig
    rule_version: int
    effective_config_snapshot: dict[str, Any]


class CollectionRuntimeLoader:
    def __init__(
        self,
        *,
        account_shop_resolver: AccountShopResolver | None = None,
    ) -> None:
        self.account_shop_resolver = account_shop_resolver or AccountShopResolver()

    async def load(
        self,
        *,
        session: AsyncSession,
        data_source_id: int,
        rule_id: int,
        execution_id: str,
        overrides: Mapping[str, Any] | None = None,
    ) -> LoadedCollectionRuntime:
        ds_repo = DataSourceRepository(session)
        rule_repo = ScrapingRuleRepository(session)
        data_source = await ds_repo.get_by_id(data_source_id)
        rule = await rule_repo.get_by_id(rule_id)
        if data_source is None or rule is None:
            raise ScrapingFailedException(
                "Data source or scraping rule not found",
                error_data={"data_source_id": data_source_id, "rule_id": rule_id},
            )
        if data_source.status != DataSourceStatus.ACTIVE:
            raise ScrapingFailedException(
                "Data source is inactive",
                error_data={"data_source_id": data_source_id},
            )
        if rule.status != ScrapingRuleStatus.ACTIVE:
            raise ScrapingFailedException(
                "Scraping rule is inactive",
                error_data={"rule_id": rule_id},
            )

        data_source_contract = DataSourceContract(
            id=int(data_source.id or 0),
            status=_as_enum_value(data_source.status),
            timeout=int(data_source.timeout or 30),
            retry_count=int(data_source.retry_count or 3),
            rate_limit=data_source.rate_limit,
            extra_config=dict(data_source.extra_config or {}),
        )
        rule_contract = ScrapingRuleContract(
            id=int(rule.id or 0),
            status=_as_enum_value(rule.status),
            version=int(rule.version or 1),
            target_type=_as_enum_value(rule.target_type),
            granularity=_as_enum_value(rule.granularity),
            timezone=str(rule.timezone or "Asia/Shanghai"),
            time_range=dict(rule.time_range)
            if isinstance(rule.time_range, dict)
            else None,
            incremental_mode=_as_enum_value(rule.incremental_mode),
            backfill_last_n_days=int(rule.backfill_last_n_days or 0),
            data_latency=_as_enum_value(rule.data_latency),
            filters=dict(rule.filters or {})
            if isinstance(rule.filters, dict)
            else None,
            dimensions=list(rule.dimensions or []),
            metrics=list(rule.metrics or []),
            dedupe_key=rule.dedupe_key,
            rate_limit=rule.rate_limit,
            top_n=rule.top_n,
            sort_by=rule.sort_by,
            include_long_tail=bool(rule.include_long_tail),
            session_level=bool(rule.session_level),
            extra_config=dict(rule.extra_config or {}),
        )
        runtime = build_runtime_config(
            data_source=data_source_contract,
            rule=rule_contract,
            execution_id=execution_id,
            overrides=dict(overrides or {}),
        )
        runtime = await self._resolve_all_mode_runtime(
            runtime=runtime,
            data_source=data_source_contract,
        )
        if not runtime.api_groups:
            raise ScrapingFailedException(
                "No API groups resolved for runtime",
                error_data={
                    "rule_id": rule_id,
                    "target_type": runtime.target_type,
                    "metrics": runtime.metrics,
                },
            )
        return LoadedCollectionRuntime(
            runtime=runtime,
            rule_version=rule_contract.version,
            effective_config_snapshot=self._build_effective_config_snapshot(
                runtime=runtime,
                data_source_id=data_source_id,
                rule_id=rule_id,
                rule_version=rule_contract.version,
                overrides=dict(overrides or {}),
            ),
        )

    def _build_effective_config_snapshot(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        data_source_id: int,
        rule_id: int,
        rule_version: int,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "data_source_id": data_source_id,
            "rule_id": rule_id,
            "rule_version": rule_version,
            "execution_id": runtime.execution_id,
            "shop_id": runtime.shop_id,
            "granularity": runtime.granularity,
            "timezone": runtime.timezone,
            "time_range": dict(runtime.time_range or {}),
            "incremental_mode": runtime.incremental_mode,
            "backfill_last_n_days": runtime.backfill_last_n_days,
            "data_latency": runtime.data_latency,
            "target_type": runtime.target_type,
            "metrics": list(runtime.metrics),
            "dimensions": list(runtime.dimensions),
            "filters": dict(runtime.filters),
            "api_groups": list(runtime.api_groups),
            "fallback_chain": list(runtime.fallback_chain),
            "rate_limit": runtime.rate_limit,
            "overrides": dict(overrides),
            "account_id": runtime.account_id,
        }

    async def _resolve_all_mode_runtime(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        data_source: DataSourceContract,
    ) -> ShopDashboardRuntimeConfig:
        filters = dict(runtime.filters or {})
        all_mode = bool(filters.get("all"))
        if not all_mode:
            return runtime
        requested_shop_ids = _normalize_shop_ids(filters.get("shop_id"))
        resolved_shop_ids = await self.account_shop_resolver.resolve_shop_ids(
            account_id=runtime.account_id,
            cookies=runtime.cookies,
            common_query=runtime.common_query,
            extra_config=data_source.extra_config,
        )
        if requested_shop_ids:
            requested_shop_id_set = set(requested_shop_ids)
            resolved_shop_ids = [
                shop_id
                for shop_id in resolved_shop_ids
                if shop_id in requested_shop_id_set
            ]
        filters["all"] = True
        filters["shop_id"] = list(resolved_shop_ids)
        return replace(
            runtime,
            shop_id=resolved_shop_ids[0] if resolved_shop_ids else "",
            filters=filters,
        )


def _as_enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _normalize_shop_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [item for chunk in value.split(",") for item in chunk.split("|")]
    elif isinstance(value, list | tuple | set):
        parts = list(value)
    else:
        return []
    normalized: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text:
            normalized.append(text)
    return normalized
