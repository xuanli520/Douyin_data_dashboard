from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.cache import resolve_sync_redis_client
from src.domains.data_source.enums import DataSourceStatus
from src.domains.data_source.enums import ScrapingRuleStatus
from src.domains.data_source.repository import DataSourceRepository
from src.domains.scraping_rule.repository import ScrapingRuleRepository
from src.domains.task.exceptions import ScrapingFailedException
from src.domains.task.exceptions import ShopDashboardNoTargetShopsException
from src.application.collection.account_shop_catalog_service import (
    AccountShopCatalogService,
)
from src.scrapers.shop_dashboard.contracts import DataSourceContract
from src.scrapers.shop_dashboard.contracts import ScrapingRuleContract
from src.scrapers.shop_dashboard.account_shop_resolver import AccountShopResolver
from src.scrapers.shop_dashboard.runtime import ShopDashboardRuntimeConfig
from src.scrapers.shop_dashboard.runtime import build_runtime_config
from src.shared.shop_ids import normalize_shop_ids


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
        account_shop_catalog_service: AccountShopCatalogService | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self.account_shop_resolver = account_shop_resolver or AccountShopResolver()
        self.account_shop_catalog_service = (
            account_shop_catalog_service
            or AccountShopCatalogService(
                account_shop_resolver=self.account_shop_resolver,
                redis_client=resolve_sync_redis_client(redis_client),
            )
        )

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
        runtime = self._validate_target_shops(
            runtime=runtime,
            data_source_id=data_source_id,
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
            "shop_mode": runtime.shop_mode,
            "resolved_shop_ids": list(runtime.resolved_shop_ids),
            "catalog_stale": bool(runtime.catalog_stale),
            "shop_resolve_source": runtime.shop_resolve_source,
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
        _ = data_source
        if runtime.shop_mode != "ALL":
            return runtime
        catalog_result = await self.account_shop_catalog_service.get_shop_catalog(
            account_id=runtime.account_id,
            cookies=runtime.cookies,
            common_query=runtime.common_query,
            extra_config=runtime.extra_config,
            force_refresh=False,
        )
        resolved_shop_ids = list(catalog_result.shop_ids)
        filters = dict(runtime.filters or {})
        filters["all"] = True
        filters["shop_id"] = list(resolved_shop_ids)
        filters["catalog_stale"] = bool(catalog_result.catalog_stale)
        filters["shop_resolve_source"] = catalog_result.resolve_source
        return replace(
            runtime,
            shop_id=resolved_shop_ids[0] if resolved_shop_ids else "",
            resolved_shop_ids=list(resolved_shop_ids),
            catalog_stale=bool(catalog_result.catalog_stale),
            shop_resolve_source=catalog_result.resolve_source,
            filters=filters,
        )

    def _validate_target_shops(
        self,
        *,
        runtime: ShopDashboardRuntimeConfig,
        data_source_id: int,
    ) -> ShopDashboardRuntimeConfig:
        resolved_shop_ids = normalize_shop_ids(runtime.resolved_shop_ids, dedupe=False)
        if runtime.shop_mode == "ALL" and not resolved_shop_ids:
            raise ShopDashboardNoTargetShopsException(
                "No target shops resolved",
                error_data={
                    "data_source_id": data_source_id,
                    "rule_id": runtime.rule_id,
                    "execution_id": runtime.execution_id,
                    "reason": "empty_target_shops",
                    "shop_mode": runtime.shop_mode,
                },
            )
        if runtime.shop_mode != "ALL":
            if not resolved_shop_ids:
                explicit_shop_id = str(runtime.shop_id or "").strip()
                if explicit_shop_id:
                    resolved_shop_ids = [explicit_shop_id]
            if not resolved_shop_ids:
                raise ShopDashboardNoTargetShopsException(
                    "No target shops resolved",
                    error_data={
                        "data_source_id": data_source_id,
                        "rule_id": runtime.rule_id,
                        "execution_id": runtime.execution_id,
                        "reason": "empty_target_shops",
                        "shop_mode": runtime.shop_mode,
                    },
                )
        return replace(
            runtime,
            resolved_shop_ids=list(resolved_shop_ids),
            shop_id=resolved_shop_ids[0],
        )


def _as_enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value
